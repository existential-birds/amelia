"""Daytona cloud sandbox provider.

Implements the SandboxProvider protocol using Daytona's native APIs
for sandbox lifecycle and git operations, with session-based streaming
for real-time command output.
"""

from __future__ import annotations

import asyncio
import contextlib
import shlex
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from daytona_sdk import (
    AsyncDaytona,
    AsyncSandbox,
    CreateSandboxFromImageParams,
    DaytonaConfig,
    Image,
    Resources,
    SessionExecuteRequest,
)
from loguru import logger

from amelia.sandbox.worktree import REPO_PATH


if TYPE_CHECKING:
    from amelia.core.types import DaytonaResources


class DaytonaSandboxProvider:
    """Sandbox provider using Daytona cloud instances.

    Uses Daytona's native APIs for lifecycle management (create/delete)
    and git operations (clone), while exposing exec_stream for worker
    process execution.

    Args:
        api_key: Daytona API key.
        api_url: Daytona API endpoint URL.
        target: Daytona target region.
        repo_url: Git remote URL to clone into the sandbox.
        branch: Git branch to clone.
        resources: Optional CPU/memory/disk resource configuration.
    """

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://app.daytona.io/api",
        target: str = "us",
        repo_url: str = "",
        branch: str = "main",
        resources: DaytonaResources | None = None,
    ) -> None:
        self._client = AsyncDaytona(DaytonaConfig(
            api_key=api_key,
            api_url=api_url,
            target=target,
        ))
        self._target = target
        self._repo_url = repo_url
        self._branch = branch
        self._resources = resources
        self._sandbox: AsyncSandbox | None = None

    async def ensure_running(self) -> None:
        """Create Daytona sandbox and clone repo using native APIs.

        First call creates the sandbox and clones the repository.
        Subsequent calls are no-ops if the sandbox is healthy.
        """
        if self._sandbox is not None and await self.health_check():
            return

        logger.info("Creating Daytona sandbox", target=self._target)

        create_params = CreateSandboxFromImageParams(
            image=Image.debian_slim("3.12"),
        )
        if self._resources:
            create_params = CreateSandboxFromImageParams(
                image=Image.debian_slim("3.12"),
                resources=Resources(
                    cpu=self._resources.cpu,
                    memory=self._resources.memory,
                    disk=self._resources.disk,
                ),
            )

        self._sandbox = await self._client.create(create_params)
        logger.info("Daytona sandbox created", sandbox_id=self._sandbox.id)

        if self._repo_url:
            logger.info("Cloning repo via Daytona git API", url=self._repo_url)
            await self._sandbox.git.clone(self._repo_url, REPO_PATH)

    async def exec_stream(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> AsyncIterator[str]:
        """Execute command in sandbox, yielding stdout lines in real-time.

        Uses Daytona's session-based API with WebSocket log streaming to
        deliver output incrementally as it's produced.

        Args:
            command: Command and arguments to execute.
            cwd: Working directory inside the sandbox.
            env: Additional environment variables.
            stdin: Ignored (Daytona sessions do not support stdin).

        Yields:
            Lines of stdout output as they arrive.

        Raises:
            RuntimeError: If the sandbox is not running or command fails.
        """
        sandbox = self._sandbox
        if sandbox is None:
            raise RuntimeError("Sandbox not running — call ensure_running() first")

        if stdin:
            logger.warning("Daytona exec_stream does not support stdin, ignoring")

        # Build command string with cwd/env baked in (session API has no
        # cwd/env params).
        cmd_str = shlex.join(command)
        if env:
            exports = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items())
            cmd_str = f"export {exports} && {cmd_str}"
        if cwd:
            cmd_str = f"cd {shlex.quote(cwd)} && {cmd_str}"

        session_id = f"amelia-{uuid.uuid4().hex[:12]}"
        try:
            await sandbox.process.create_session(session_id)

            resp = await sandbox.process.execute_session_command(
                session_id,
                SessionExecuteRequest(command=cmd_str, run_async=True),
            )
            cmd_id = resp.cmd_id

            queue: asyncio.Queue[str | None] = asyncio.Queue()

            async def on_stdout(chunk: str) -> None:
                await queue.put(chunk)

            async def on_stderr(chunk: str) -> None:
                logger.debug("Daytona stderr chunk", content=chunk)

            async def stream_logs() -> None:
                try:
                    await sandbox.process.get_session_command_logs_async(
                        session_id, cmd_id, on_stdout, on_stderr,
                    )
                finally:
                    await queue.put(None)

            log_task = asyncio.create_task(stream_logs())

            # Buffer partial lines; yield only complete newline-delimited lines.
            buf = ""
            try:
                while True:
                    chunk = await queue.get()
                    if chunk is None:
                        break
                    buf += chunk
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        yield line
                # Yield any remaining partial line.
                if buf:
                    yield buf
            finally:
                if not log_task.done():
                    log_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await log_task

            # Propagate any exception from the log streaming task.
            if log_task.done():
                exc = log_task.exception()
                if exc is not None:
                    raise exc

            # Check exit code after streaming completes.
            cmd_info = await sandbox.process.get_session_command(
                session_id, cmd_id,
            )
            if cmd_info.exit_code is not None and cmd_info.exit_code != 0:
                raise RuntimeError(
                    f"Command exited with code {cmd_info.exit_code}: {cmd_str}"
                )
        finally:
            try:
                await sandbox.process.delete_session(session_id)
            except Exception:
                logger.debug("Failed to delete Daytona session", session_id=session_id)

    async def teardown(self) -> None:
        """Delete the ephemeral Daytona sandbox."""
        if self._sandbox is None:
            return
        logger.info("Tearing down Daytona sandbox", sandbox_id=self._sandbox.id)
        await self._sandbox.delete()
        self._sandbox = None

    async def health_check(self) -> bool:
        """Check if the sandbox is responsive.

        Returns:
            True if sandbox exists and responds to a trivial command.
        """
        if self._sandbox is None:
            return False
        try:
            response = await self._sandbox.process.exec("true")
            return bool(response.exit_code == 0)
        except Exception:
            logger.debug("Daytona health check failed")
            return False
