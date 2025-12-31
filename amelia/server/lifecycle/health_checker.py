"""Worktree health checker for periodic validation."""

import asyncio
import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger


if TYPE_CHECKING:
    from amelia.server.orchestrator.service import OrchestratorService


class WorktreeHealthChecker:
    """Periodically validates worktree health for active workflows.

    Checks that worktree directories still exist and are valid git repositories.
    If a worktree is deleted while a workflow is running, cancels the workflow.
    """

    def __init__(
        self,
        orchestrator: "OrchestratorService",
        check_interval: float = 30.0,
    ) -> None:
        """Initialize health checker.

        Args:
            orchestrator: Orchestrator service instance.
            check_interval: Seconds between health checks (default: 30).
        """
        self._orchestrator = orchestrator
        self._check_interval = check_interval
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the health check loop."""
        self._task = asyncio.create_task(self._check_loop())
        logger.info(
            "WorktreeHealthChecker started",
            interval=self._check_interval,
        )

    async def stop(self) -> None:
        """Stop the health check loop."""
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            logger.info("WorktreeHealthChecker stopped")

    async def _check_loop(self) -> None:
        """Periodically check all active worktrees for health issues.

        Runs continuously until task is cancelled, sleeping between checks.
        """
        while True:
            await asyncio.sleep(self._check_interval)
            try:
                await self._check_all_worktrees()
            except Exception as e:
                logger.error(
                    "Health check failed - continuing loop",
                    error=str(e),
                    error_type=type(e).__name__,
                )

    async def _check_all_worktrees(self) -> None:
        """Check health of all active workflow worktrees and cancel unhealthy ones.

        Cancels workflows whose worktrees have been deleted.
        """
        for worktree_path in self._orchestrator.get_active_workflows():
            if not await self._is_worktree_healthy(worktree_path):
                workflow = await self._orchestrator.get_workflow_by_worktree(
                    worktree_path
                )
                if workflow:
                    logger.warning(
                        "Worktree deleted - cancelling workflow",
                        worktree_path=worktree_path,
                        workflow_id=workflow.id,
                    )
                    await self._orchestrator.cancel_workflow(
                        workflow.id,
                        reason="Worktree directory no longer exists",
                    )

    def _check_worktree_sync(self, path: Path) -> bool:
        """Perform synchronous filesystem checks for worktree health.

        Args:
            path: Path to worktree directory.

        Returns:
            True if worktree is healthy, False otherwise.
        """
        if not path.exists():
            return False

        if not path.is_dir():
            return False

        # Check .git exists (file for worktrees, dir for main repo)
        git_path = path / ".git"
        return git_path.exists()

    async def _is_worktree_healthy(self, worktree_path: str) -> bool:
        """Check if worktree directory still exists and is a valid git repository.

        Performs async filesystem check using thread pool to avoid blocking
        the event loop on slow or network filesystems.

        Args:
            worktree_path: Absolute path to worktree.

        Returns:
            True if worktree is healthy, False otherwise.
        """
        path = Path(worktree_path)
        return await asyncio.to_thread(self._check_worktree_sync, path)
