"""Codex CLI driver using OpenAI's codex CLI.

This driver wraps the OpenAI Codex CLI, providing both single-turn generation
and agentic execution capabilities.
"""
import asyncio
import json
import subprocess
from collections.abc import AsyncIterator, Iterator
from typing import Any

from pydantic import BaseModel, ValidationError

from amelia.core.exceptions import ModelProviderError
from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverInterface,
    DriverUsage,
    GenerateResult,
)


class CodexCliDriver(DriverInterface):
    """CLI driver wrapping OpenAI's Codex CLI tool.

    This driver provides both single-turn generation and agentic execution
    by wrapping the `codex` CLI command.
    """

    PROVIDER_NAME = "codex-cli"

    def __init__(self, model: str = "", cwd: str | None = None) -> None:
        """Initialize CodexCliDriver.

        Args:
            model: LLM model identifier.
            cwd: Working directory for command execution.
        """
        self.model = model
        self.cwd = cwd

    async def _run_codex(self, prompt: str, **kwargs: Any) -> str:
        """Run codex CLI command and return output.

        Args:
            prompt: The prompt to send to codex.
            **kwargs: Additional arguments to pass to codex exec.

        Returns:
            The raw output from codex CLI.

        Raises:
            ModelProviderError: If codex CLI fails.
        """
        cmd = ["codex", "exec", "--json"]

        if self.model:
            cmd.extend(["--model", self.model])

        cmd.extend(["--", prompt])

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
        )

        try:
            stdout, stderr = await process.communicate()
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise ModelProviderError(
                f"Codex CLI failed with exit code {process.returncode}: {error_msg}",
                provider_name=self.PROVIDER_NAME,
                original_message=error_msg,
            )

        return stdout.decode()

    def _run_codex_stream(
        self, prompt: str, cwd: str | None = None, **kwargs: Any
    ) -> Iterator[dict[str, Any]]:
        """Run codex CLI command and stream NDJSON events.

        Spawns a synchronous subprocess with ``codex exec --stream --json``
        and yields one parsed dict per newline-delimited JSON line.

        Args:
            prompt: The prompt to send to codex.
            cwd: Working directory override (falls back to self.cwd).
            **kwargs: Additional arguments (currently unused).

        Yields:
            Event dictionaries parsed from codex CLI NDJSON output.

        Raises:
            ModelProviderError: If codex CLI exits with non-zero status.
        """
        cmd = ["codex", "exec", "--stream", "--json"]

        if self.model:
            cmd.extend(["--model", self.model])

        cmd.extend(["--", prompt])

        proc = subprocess.Popen(
            cmd,
            cwd=cwd or self.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            for raw_line in proc.stdout:  # type: ignore[union-attr]
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if isinstance(event, dict):
                        yield event
                except json.JSONDecodeError:
                    continue  # skip malformed lines
        finally:
            proc.wait()
            if proc.returncode and proc.returncode != 0:
                stderr_text = ""
                if proc.stderr:
                    stderr_text = proc.stderr.read().decode("utf-8", errors="replace").strip()[:1000]
                raise ModelProviderError(
                    f"Codex CLI streaming failed with exit code {proc.returncode}: {stderr_text}",
                    provider_name=self.PROVIDER_NAME,
                    original_message=stderr_text,
                )

    def _parse_json_response(self, raw_output: str) -> Any:
        """Parse JSON from codex CLI output, handling common issues.

        Args:
            raw_output: Raw output from codex CLI.

        Returns:
            Parsed JSON as a dictionary.

        Raises:
            ModelProviderError: If JSON parsing fails.
        """
        text = raw_output.strip()

        # Handle markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            # Find the closing fence
            end_idx = -1
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end_idx = i
                    break
            if end_idx > 0:
                text = "\n".join(lines[1:end_idx])

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ModelProviderError(
                f"Failed to parse Codex CLI output as JSON: {e}",
                provider_name=self.PROVIDER_NAME,
                original_message=raw_output[:500],
            ) from None

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        schema: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> GenerateResult:
        """Generate a single-turn response.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt.
            schema: Optional Pydantic schema for structured output.
            **kwargs: Additional arguments.

        Returns:
            GenerateResult with the generated text and session ID.

        Raises:
            ModelProviderError: If codex CLI fails or returns invalid JSON.
        """
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        try:
            raw_output = await self._run_codex(full_prompt, **kwargs)
        except ModelProviderError:
            raise
        except Exception as e:
            raise ModelProviderError(
                f"Codex CLI error: {e}",
                provider_name=self.PROVIDER_NAME,
                original_message=str(e),
            ) from e

        parsed = self._parse_json_response(raw_output)

        # Extract text from response
        if isinstance(parsed, dict):
            if "result" in parsed:
                text = parsed["result"]
            elif "text" in parsed:
                text = parsed["text"]
            elif "content" in parsed:
                text = parsed["content"]
            else:
                text = json.dumps(parsed)
        else:
            text = str(parsed)

        # Validate against schema if provided
        if schema:
            try:
                # Parse the text as JSON and validate against schema
                data = json.loads(text) if isinstance(text, str) else text
                result = schema.model_validate(data)
                return (result, None)
            except (ValidationError, json.JSONDecodeError) as e:
                raise ModelProviderError(
                    f"Schema validation failed: {e}",
                    provider_name=self.PROVIDER_NAME,
                    original_message=text[:500] if isinstance(text, str) else str(text)[:500],
                ) from e

        return (text, None)

    async def execute_agentic(
        self,
        prompt: str,
        cwd: str,
        session_id: str | None = None,
        instructions: str | None = None,
        schema: type[BaseModel] | None = None,
        allowed_tools: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[AgenticMessage]:
        """Execute agentic workflow.

        Args:
            prompt: The user prompt.
            cwd: Working directory for the agent.
            session_id: Optional session ID for stateful execution.
            instructions: Optional additional instructions.
            schema: Optional Pydantic schema for structured output.
            allowed_tools: Optional list of allowed tool names.
            **kwargs: Additional arguments.

        Yields:
            AgenticMessage objects representing the execution stream.

        Raises:
            ModelProviderError: If codex CLI fails.
        """
        full_prompt = prompt
        if instructions:
            full_prompt = f"{instructions}\n\n{prompt}"

        # Build command args
        cmd_args: dict[str, Any] = {"cwd": cwd}
        if session_id:
            cmd_args["session_id"] = session_id
        if allowed_tools:
            cmd_args["allowed_tools"] = allowed_tools

        try:
            # Use streaming mode
            stream_events = self._run_codex_stream(full_prompt, **cmd_args)
        except ModelProviderError:
            raise
        except Exception as e:
            raise ModelProviderError(
                f"Codex CLI agentic error: {e}",
                provider_name=self.PROVIDER_NAME,
                original_message=str(e),
            ) from e

        # Iterate over streaming events
        for parsed in stream_events:
            # parsed is already a dict from _run_codex_stream yielding dicts

            # Map to AgenticMessage types
            if isinstance(parsed, dict):
                msg_type = parsed.get("type", "result")

                if msg_type == "reasoning" or msg_type == "thinking":
                    yield AgenticMessage(
                        type=AgenticMessageType.THINKING,
                        content=parsed.get("content", ""),
                    )
                elif msg_type == "tool_call":
                    yield AgenticMessage(
                        type=AgenticMessageType.TOOL_CALL,
                        content="",
                        tool_name=parsed.get("name", ""),
                        tool_input=parsed.get("input", {}),
                        tool_call_id=parsed.get("id"),
                    )
                elif msg_type == "tool_result":
                    yield AgenticMessage(
                        type=AgenticMessageType.TOOL_RESULT,
                        content=parsed.get("output", ""),
                        tool_name=parsed.get("name", ""),
                        tool_call_id=parsed.get("id"),
                    )
                elif msg_type == "final":
                    yield AgenticMessage(
                        type=AgenticMessageType.RESULT,
                        content=parsed.get("content", ""),
                    )
                else:
                    # Default to result
                    yield AgenticMessage(
                        type=AgenticMessageType.RESULT,
                        content=json.dumps(parsed),
                    )

    async def cleanup_session(self, session_id: str) -> bool:
        """Clean up a driver session.

        CodexCliDriver has no persistent session state to clean.

        Args:
            session_id: The session identifier to clean up.

        Returns:
            False - no session state exists to clean.
        """
        return False

    def get_usage(self) -> DriverUsage | None:
        """Get usage statistics.

        Returns:
            None - usage tracking not yet implemented for Codex CLI.
        """
        return None
