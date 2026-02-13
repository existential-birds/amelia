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

    async def teardown(self) -> None:
        """Stop and clean up the sandbox."""
        ...

    async def health_check(self) -> bool:
        """Check if the sandbox is responsive.

        Returns:
            True if sandbox is running and healthy.
        """
        ...
