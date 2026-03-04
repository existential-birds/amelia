"""Daytona cloud sandbox provider.

Implements the SandboxProvider protocol using Daytona's native APIs
for sandbox lifecycle and git operations, with process.exec() for
command execution.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from daytona_sdk import (
    AsyncDaytona,
    AsyncSandbox,
    CreateSandboxFromImageParams,
    DaytonaConfig,
    Image,
    Resources,
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
        """Execute command in sandbox, yielding stdout lines.

        Wraps Daytona's process.exec() and splits the result into lines.
        Note: stdin is not supported by the Daytona SDK and is ignored
        with a warning if provided.

        Args:
            command: Command and arguments to execute.
            cwd: Working directory inside the sandbox.
            env: Additional environment variables.
            stdin: Ignored (Daytona process.exec does not support stdin).

        Yields:
            Lines of stdout output.

        Raises:
            RuntimeError: If the sandbox is not running or command fails.
        """
        if self._sandbox is None:
            raise RuntimeError("Sandbox not running — call ensure_running() first")

        if stdin:
            logger.warning("Daytona exec_stream does not support stdin, ignoring")

        cmd_str = " ".join(command)
        response = await self._sandbox.process.exec(
            cmd_str,
            cwd=cwd,
            env=env,
        )

        if response.exit_code != 0:
            raise RuntimeError(
                f"Command exited with code {response.exit_code}: {cmd_str}"
            )

        for line in response.result.splitlines():
            yield line

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
