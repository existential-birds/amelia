"""ContainerDriver — DriverInterface implementation for sandboxed execution.

Delegates LLM execution to a container worker via SandboxProvider.exec_stream().
The worker runs inside a Docker container and streams AgenticMessage JSON lines.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverUsage,
    GenerateResult,
)
from amelia.sandbox.provider import SandboxProvider


class ContainerDriver:
    """Driver that executes LLM operations inside a sandbox container."""

    def __init__(self, model: str, provider: SandboxProvider) -> None:
        self.model = model
        self._provider = provider
        self._last_usage: DriverUsage | None = None

    async def _write_prompt(self, prompt: str, workflow_id: str | None = None) -> str:
        """Write the prompt to a temp file inside the container.

        Args:
            prompt: The prompt text to write.
            workflow_id: Optional workflow identifier for the filename.

        Returns:
            Path to the temp file inside the container.
        """
        suffix = workflow_id or uuid4().hex[:12]
        prompt_path = f"/tmp/prompt-{suffix}.txt"
        async for _ in self._provider.exec_stream(  # type: ignore[attr-defined]
            ["tee", prompt_path],
            stdin=prompt.encode(),
        ):
            pass
        return prompt_path

    async def _cleanup_prompt(self, prompt_path: str) -> None:
        """Remove the temp prompt file from the container.

        Args:
            prompt_path: Path to the temp file to remove.
        """
        async for _ in self._provider.exec_stream(["rm", "-f", prompt_path]):  # type: ignore[attr-defined]
            pass

    def _parse_line(self, line: str) -> AgenticMessage:
        """Parse a JSON line from the worker into an AgenticMessage.

        Args:
            line: JSON-encoded line from the worker process.

        Returns:
            Parsed AgenticMessage.

        Raises:
            RuntimeError: If the line cannot be parsed.
        """
        try:
            return AgenticMessage.model_validate_json(line)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(
                f"Failed to parse worker output: {line[:200]}"
            ) from exc

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
        """Execute an agentic task inside the sandbox container.

        Writes the prompt to a temp file, invokes the worker, and streams
        back AgenticMessage objects. Usage messages are captured internally
        and not yielded.

        Args:
            prompt: The task prompt.
            cwd: Working directory inside the container.
            session_id: Optional session identifier (unused).
            instructions: Optional additional instructions for the worker.
            schema: Optional output schema (unused in agentic mode).
            allowed_tools: Optional tool allowlist (unused).
            **kwargs: Additional driver-specific options.

        Yields:
            AgenticMessage objects (excluding USAGE messages).

        Raises:
            ValueError: If prompt is empty.
            RuntimeError: If worker output cannot be parsed.
        """
        if not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        await self._provider.ensure_running()
        workflow_id = kwargs.get("workflow_id")
        prompt_path = await self._write_prompt(prompt, workflow_id=workflow_id)

        try:
            cmd = [
                "python", "-m", "amelia.sandbox.worker", "agentic",
                "--prompt-file", prompt_path,
                "--cwd", cwd,
                "--model", self.model,
            ]
            if instructions:
                cmd.extend(["--instructions", instructions])

            async for line in self._provider.exec_stream(cmd, cwd=cwd):  # type: ignore[attr-defined]
                msg = self._parse_line(line)
                if msg.type == AgenticMessageType.USAGE:
                    self._last_usage = msg.usage
                else:
                    yield msg
        finally:
            await self._cleanup_prompt(prompt_path)

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        schema: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> GenerateResult:
        """Generate a response from the LLM inside the sandbox container.

        Writes the prompt to a temp file, invokes the worker in generate mode,
        and returns the result content. If a schema is provided, validates the
        output against it.

        Args:
            prompt: The generation prompt.
            system_prompt: Optional system prompt (unused).
            schema: Optional Pydantic model to validate output against.
            **kwargs: Additional driver-specific options.

        Returns:
            Tuple of (output, session_id). Output is a string or validated
            schema instance. session_id is always None.

        Raises:
            ValueError: If prompt is empty.
            RuntimeError: If worker output cannot be parsed, no RESULT message
                is emitted, or schema validation fails.
        """
        if not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        await self._provider.ensure_running()
        workflow_id = kwargs.get("workflow_id")
        prompt_path = await self._write_prompt(prompt, workflow_id=workflow_id)

        try:
            cmd = [
                "python", "-m", "amelia.sandbox.worker", "generate",
                "--prompt-file", prompt_path,
                "--model", self.model,
            ]
            if schema:
                cmd.extend(["--schema", f"{schema.__module__}:{schema.__name__}"])

            result_content: str | None = None
            async for line in self._provider.exec_stream(cmd):  # type: ignore[attr-defined]
                msg = self._parse_line(line)
                if msg.type == AgenticMessageType.USAGE:
                    self._last_usage = msg.usage
                elif msg.type == AgenticMessageType.RESULT:
                    result_content = msg.content
        finally:
            await self._cleanup_prompt(prompt_path)

        if result_content is None:
            raise RuntimeError("Worker did not emit a RESULT message")

        if schema:
            try:
                output = schema.model_validate_json(result_content)
            except (ValidationError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"Failed to validate worker output against {schema.__name__}: "
                    f"{result_content[:200]}"
                ) from exc
            return output, None

        return result_content, None

    def get_usage(self) -> DriverUsage | None:
        """Return the last captured usage data, or None if no execution has occurred.

        Returns:
            DriverUsage from the most recent execution, or None.
        """
        return self._last_usage

    async def cleanup_session(self, session_id: str) -> bool:
        """Clean up a session. Not applicable for container driver.

        Args:
            session_id: Session identifier to clean up.

        Returns:
            Always False (container driver does not manage sessions).
        """
        return False
