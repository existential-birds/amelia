"""ContainerDriver — DriverInterface implementation for sandboxed execution.

Delegates LLM execution to a container worker. When the provider supports a
persistent worker (e.g. Docker via ``docker exec -i``), a single long-lived
``serve`` process is spawned once per sandbox and reused across every agent
call, so the heavy LangChain/deepagents import cost is paid once rather than
on every call. Providers without a duplex stdin pipe (e.g. Daytona) fall back
to the per-call one-shot worker path.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverUsage,
    GenerateResult,
)
from amelia.sandbox.protocol import (
    WorkerRequest,
    encode_request,
    parse_frame,
)
from amelia.sandbox.provider import SandboxProvider, WorkerProcess


def _parse_worker_message(raw: str) -> AgenticMessage:
    """Validate a worker AgenticMessage JSON payload, normalizing failures.

    Args:
        raw: A JSON-encoded AgenticMessage emitted by the worker.

    Returns:
        The parsed AgenticMessage.

    Raises:
        RuntimeError: If the payload is not a valid AgenticMessage.
    """
    try:
        return AgenticMessage.model_validate_json(raw)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError(f"Failed to parse worker output: {raw[:200]}") from exc


class _PersistentWorker:
    """Owns one long-lived ``serve`` process and dispatches commands to it.

    The worker is spawned lazily on first use and reused for the sandbox's
    lifetime. Commands are serialized with a lock so frames from concurrent
    callers never interleave on the shared pipe. A crashed worker is detected
    (EOF mid-command) and reset so the next command respawns a fresh one.
    """

    def __init__(
        self,
        provider: SandboxProvider,
        cwd: str | None,
        env: dict[str, str] | None,
    ) -> None:
        self._provider = provider
        self._cwd = cwd
        self._env = env
        self._proc: WorkerProcess | None = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> WorkerProcess:
        if self._proc is None or not self._proc.alive:
            self._proc = await self._provider.spawn_worker(cwd=self._cwd, env=self._env)
        return self._proc

    async def dispatch(self, request: WorkerRequest) -> AsyncGenerator[AgenticMessage]:
        """Send one request and yield its AgenticMessages until ``done``.

        Args:
            request: The command to run.

        Yields:
            AgenticMessage objects (including USAGE).

        Raises:
            RuntimeError: If the worker reports an error or crashes mid-command.
        """
        async with self._lock:
            proc = await self._ensure()
            completed = False
            try:
                await proc.write(encode_request(request))
                error: str | None = None
                while True:
                    line = await proc.readline()
                    if not line:
                        raise RuntimeError("Sandbox worker exited unexpectedly mid-command")
                    frame = parse_frame(line)
                    if frame.frame == "done":
                        # ``done`` always terminates a command (success OR error).
                        # Surface a deferred error only after fully draining the
                        # command's frames, so the pipe is left clean for the next
                        # command (no stale trailing ``done``).
                        completed = True
                        if error is not None:
                            raise RuntimeError(f"Sandbox worker error: {error}")
                        return
                    if frame.frame == "error":
                        # Record and keep reading until ``done`` (protocol guarantees
                        # ``error`` is followed by ``done``).
                        error = frame.error
                        continue
                    # frame.frame == "msg"
                    if frame.msg is not None and error is None:
                        yield _parse_worker_message(frame.msg)
            finally:
                # Any exit before ``done`` (crash EOF, caller cancellation, or a
                # parse failure) leaves unread frames on the shared pipe. Drop
                # and close the worker so the next command respawns a clean one.
                if not completed and self._proc is proc:
                    self._proc = None
                    await asyncio.shield(proc.close())

    async def close(self) -> None:
        if self._proc is not None:
            await self._proc.close()
            self._proc = None


class ContainerDriver:
    """Driver that executes LLM operations inside a sandbox container."""

    def __init__(
        self,
        model: str,
        provider: SandboxProvider,
        env: dict[str, str] | None = None,
    ) -> None:
        self.model = model
        self._provider = provider
        self._env = env
        self._last_usage: DriverUsage | None = None
        self._worker: _PersistentWorker | None = None

    def _persistent_worker(self) -> _PersistentWorker:
        """Return the shared persistent worker, creating it on first use."""
        if self._worker is None:
            self._worker = _PersistentWorker(self._provider, cwd=None, env=self._env)
        return self._worker

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
        await self._provider.write_file(prompt_path, prompt.encode())
        return prompt_path

    async def _cleanup_prompt(self, prompt_path: str) -> None:
        """Remove the temp prompt file from the container.

        Args:
            prompt_path: Path to the temp file to remove.
        """
        async for _ in self._provider.exec_stream(["rm", "-f", prompt_path]):
            pass

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

        # Translate host path to sandbox-internal path (no-op for Docker,
        # maps to /workspace/repo for Daytona).
        sandbox_cwd = self._provider.resolve_cwd(cwd)

        if self._provider.supports_persistent_worker:
            request = WorkerRequest(
                mode="agentic",
                prompt=prompt,
                model=self.model,
                cwd=sandbox_cwd,
                instructions=instructions,
            )
            worker = self._persistent_worker()
            async with aclosing(worker.dispatch(request)) as stream:
                async for msg in stream:
                    if msg.type == AgenticMessageType.USAGE:
                        self._last_usage = msg.usage
                    else:
                        yield msg
            return

        # One-shot fallback: fresh worker process per call.
        workflow_id = kwargs.get("workflow_id")
        prompt_path = await self._write_prompt(prompt, workflow_id=workflow_id)
        try:
            cmd = [
                *self._provider.worker_cmd, "agentic",
                "--prompt-file", prompt_path,
                "--cwd", sandbox_cwd,
                "--model", self.model,
            ]
            if instructions:
                cmd.extend(["--instructions", instructions])

            async for line in self._provider.exec_stream(cmd, cwd=sandbox_cwd, env=self._env):
                msg = _parse_worker_message(line)
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

        schema_path = f"{schema.__module__}:{schema.__name__}" if schema else None
        result_content: str | None = None

        if self._provider.supports_persistent_worker:
            request = WorkerRequest(
                mode="generate",
                prompt=prompt,
                model=self.model,
                schema_path=schema_path,
            )
            worker = self._persistent_worker()
            async with aclosing(worker.dispatch(request)) as stream:
                async for msg in stream:
                    if msg.type == AgenticMessageType.USAGE:
                        self._last_usage = msg.usage
                    elif msg.type == AgenticMessageType.RESULT:
                        result_content = msg.content
        else:
            # One-shot fallback: fresh worker process per call.
            workflow_id = kwargs.get("workflow_id")
            prompt_path = await self._write_prompt(prompt, workflow_id=workflow_id)
            try:
                cmd = [
                    *self._provider.worker_cmd, "generate",
                    "--prompt-file", prompt_path,
                    "--model", self.model,
                ]
                if schema_path:
                    cmd.extend(["--schema", schema_path])

                async for line in self._provider.exec_stream(cmd, env=self._env):
                    msg = _parse_worker_message(line)
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

    def get_tool_definitions(self) -> list[dict[str, Any]] | None:
        """Return None — the container worker's tool list is not materialized here."""
        return None

    async def cleanup_session(self, session_id: str) -> bool:
        """Clean up a session. Not applicable for container driver.

        Args:
            session_id: Session identifier to clean up.

        Returns:
            Always False (container driver does not manage sessions).
        """
        return False
