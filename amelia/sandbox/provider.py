"""SandboxProvider protocol — transport-agnostic sandbox lifecycle interface."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class SandboxProvider(Protocol):
    """Manages sandbox lifecycle and command execution.

    Transport-agnostic interface that enables Docker (MVP), Daytona,
    Fly.io, or SSH-based sandbox implementations.
    """

    async def ensure_running(self) -> None:
        """Ensure the sandbox is ready. Start if not running, no-op if already up."""
        ...

    def exec_stream(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> AsyncIterator[str]:
        """Execute command in sandbox, streaming stdout lines.

        Args:
            command: Command and arguments to execute.
            cwd: Working directory inside the sandbox.
            env: Additional environment variables.
            stdin: Optional bytes to pipe to stdin.

        Yields:
            Lines of stdout output.
        """
        ...

    @property
    def worker_cmd(self) -> list[str]:
        """Base command to invoke the sandbox worker.

        Returns the command prefix (without subcommand or args).
        Default uses module invocation; providers that upload a standalone
        worker script should override this.
        """
        return ["python", "-m", "amelia.sandbox.worker"]

    @property
    def worker_env(self) -> dict[str, str]:
        """Environment variables for the worker process.

        Returns additional env vars the worker needs (e.g., LLM API keys
        for remote sandboxes). Default is empty.
        """
        return {}

    async def write_file(self, path: str, content: bytes) -> None:
        """Write content to a file inside the sandbox.

        Default implementation uses tee + stdin (works for Docker).
        Providers without stdin support should override this.
        """
        async for _ in self.exec_stream(["tee", path], stdin=content):
            pass

    async def teardown(self) -> None:
        """Stop and clean up the sandbox."""
        ...

    def resolve_cwd(self, cwd: str) -> str:
        """Translate a host working directory to a sandbox-internal path.

        The default implementation returns the path unchanged, which is
        correct for providers that mount the host filesystem (e.g. Docker).
        Providers with their own filesystem layout (e.g. Daytona) should
        override this to map to the sandbox's repo path.

        Args:
            cwd: Host-side working directory path.

        Returns:
            Path to use inside the sandbox.
        """
        return cwd

    async def health_check(self) -> bool:
        """Check if the sandbox is responsive.

        Returns:
            True if sandbox is running and healthy.
        """
        ...
