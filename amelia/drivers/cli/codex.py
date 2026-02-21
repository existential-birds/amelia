"""Codex CLI driver using OpenAI's codex CLI.

This driver wraps the OpenAI Codex CLI, providing both single-turn generation
and agentic execution capabilities.
"""
import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger
from pydantic import BaseModel, ValidationError

from amelia.core.exceptions import ModelProviderError
from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverInterface,
    DriverUsage,
    GenerateResult,
)
from amelia.drivers.cli.utils import strip_markdown_fences


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

    async def _run_codex(self, prompt: str) -> str:
        """Run codex CLI command and return output.

        Args:
            prompt: The prompt to send to codex.

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

    async def _run_codex_stream(
        self, prompt: str, cwd: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Run codex CLI command and stream NDJSON events.

        Spawns an async subprocess with ``codex exec --json``
        and yields one parsed dict per newline-delimited JSON line.

        Args:
            prompt: The prompt to send to codex.
            cwd: Working directory override (falls back to self.cwd).

        Yields:
            Event dictionaries parsed from codex CLI NDJSON output.

        Raises:
            ModelProviderError: If codex CLI exits with non-zero status.
        """
        cmd = ["codex", "exec", "--json"]

        if self.model:
            cmd.extend(["--model", self.model])

        cmd.extend(["--", prompt])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd or self.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            while True:
                raw_line = await proc.stdout.readline()  # type: ignore[union-attr]
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if isinstance(event, dict):
                        yield event
                except json.JSONDecodeError as e:
                    logger.debug(
                        "Skipping malformed NDJSON line from codex CLI",
                        line=line,
                        error=str(e),
                    )
                    continue  # skip malformed lines
        except asyncio.CancelledError:
            proc.kill()
            await proc.wait()
            raise
        finally:
            await proc.wait()
            if proc.returncode and proc.returncode != 0:
                stderr_text = ""
                if proc.stderr:
                    stderr_bytes = await proc.stderr.read()
                    stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()[:1000]
                raise ModelProviderError(
                    f"Codex CLI streaming failed with exit code {proc.returncode}: {stderr_text}",
                    provider_name=self.PROVIDER_NAME,
                    original_message=stderr_text,
                )

    def _validate_schema(
        self, data: Any, schema: type[BaseModel], source_content: str
    ) -> str:
        """Validate data against a Pydantic schema and return serialized JSON.

        Args:
            data: The data to validate (dict or JSON string).
            schema: Pydantic model class to validate against.
            source_content: Original content for error messages (truncated to 500 chars).

        Returns:
            JSON string of the validated model.

        Raises:
            ModelProviderError: If validation fails.
        """
        try:
            if isinstance(data, str):
                data = json.loads(data)
            validated = schema.model_validate(data)
            return validated.model_dump_json()
        except (ValidationError, json.JSONDecodeError) as e:
            raise ModelProviderError(
                f"Schema validation failed: {e}",
                provider_name=self.PROVIDER_NAME,
                original_message=str(source_content)[:500],
            ) from e

    def _parse_json_response(self, raw_output: str) -> Any:
        """Parse JSON from codex CLI output, handling common issues.

        Args:
            raw_output: Raw output from codex CLI.

        Returns:
            Parsed JSON as a dictionary.

        Raises:
            ModelProviderError: If JSON parsing fails.
        """
        text = strip_markdown_fences(raw_output)

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            lines = [line for line in text.splitlines() if line.strip()]
            if len(lines) > 1:
                try:
                    return json.loads(lines[-1])
                except json.JSONDecodeError:
                    pass
            raise ModelProviderError(
                f"Failed to parse Codex CLI output as JSON: {e}",
                provider_name=self.PROVIDER_NAME,
                original_message=raw_output[:500],
            ) from e

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
            raw_output = await self._run_codex(full_prompt)
        except ModelProviderError:
            raise
        except Exception as e:
            raise ModelProviderError(
                f"Codex CLI error: {e}",
                provider_name=self.PROVIDER_NAME,
                original_message=str(e),
            ) from e

        parsed = self._parse_json_response(raw_output)

        # Extract data from response - keep as dict when possible to avoid
        # unnecessary JSON serialization/deserialization
        if isinstance(parsed, dict):
            if "result" in parsed:
                data = parsed["result"]
            elif "text" in parsed:
                data = parsed["text"]
            elif "content" in parsed:
                data = parsed["content"]
            else:
                data = parsed
        else:
            data = parsed

        # Validate against schema if provided
        if schema:
            try:
                # If data is a string, parse it as JSON first
                if isinstance(data, str):
                    data = json.loads(data)
                result = schema.model_validate(data)
                return (result, None)
            except (ValidationError, json.JSONDecodeError) as e:
                raise ModelProviderError(
                    f"Schema validation failed: {e}",
                    provider_name=self.PROVIDER_NAME,
                    original_message=str(data)[:500],
                ) from e

        # For non-schema case, convert to string if needed
        text = json.dumps(data) if not isinstance(data, str) else data
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

        # Intentionally unused: session_id and allowed_tools are required by the Driver
        # interface but Codex CLI handles these differently - sessions require the
        # `codex resume` subcommand, and permissions are managed via sandbox modes
        # (--full-auto, --auto-edit). These parameters are permanently unused here.
        _ = session_id, allowed_tools  # Silence linters

        # Use streaming mode - iterate asynchronously
        async for parsed in self._run_codex_stream(full_prompt, cwd=cwd):
            # Map to AgenticMessage types
            msg_type = parsed.get("type", "result")

            if msg_type in ("reasoning", "thinking"):
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
                    tool_output=(
                        parsed.get("tool_output")
                        or parsed.get("output")
                        or parsed.get("content", "")
                    ),
                    tool_name=parsed.get("tool_name") or parsed.get("name", ""),
                    tool_call_id=parsed.get("tool_call_id") or parsed.get("id"),
                )
            elif msg_type == "final":
                content = parsed.get("content", "")
                if schema and content:
                    content = self._validate_schema(content, schema, content)
                yield AgenticMessage(
                    type=AgenticMessageType.RESULT,
                    content=content,
                )
            else:
                # Default to result
                content = json.dumps(parsed)
                if schema:
                    content = self._validate_schema(parsed, schema, content)
                yield AgenticMessage(
                    type=AgenticMessageType.RESULT,
                    content=content,
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
