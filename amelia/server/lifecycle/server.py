"""Server lifecycle management for startup and shutdown."""

import asyncio
from typing import TYPE_CHECKING

from loguru import logger


if TYPE_CHECKING:
    from amelia.server.lifecycle.retention import LogRetentionService
    from amelia.server.orchestrator.service import OrchestratorService


class ServerLifecycle:
    """Manages server startup and graceful shutdown.

    Coordinates:
    - Workflow recovery on startup
    - Graceful workflow completion on shutdown
    - Log retention cleanup
    - Connection cleanup
    """

    def __init__(
        self,
        orchestrator: "OrchestratorService",
        log_retention: "LogRetentionService",
        shutdown_timeout: int = 30,
    ) -> None:
        """Initialize lifecycle manager.

        Args:
            orchestrator: Orchestrator service instance.
            log_retention: Log retention service instance.
            shutdown_timeout: Seconds to wait for workflows before cancelling.
        """
        self._orchestrator = orchestrator
        self._log_retention = log_retention
        self._shutting_down = False
        self._shutdown_timeout = shutdown_timeout

    @property
    def is_shutting_down(self) -> bool:
        """Check if server is shutting down.

        Returns:
            True if shutdown has been initiated.
        """
        return self._shutting_down

    async def startup(self) -> None:
        """Execute startup sequence.

        Recovers any workflows that were interrupted by server crash.
        """
        logger.info("Server starting up...")
        await self._orchestrator.recover_interrupted_workflows()
        logger.info("Server startup complete")

    async def shutdown(self) -> None:
        """Execute graceful shutdown sequence.

        Steps:
        1. Set shutting_down flag (middleware rejects new workflows)
        2. Wait for active workflows to complete (with timeout)
        3. Cancel remaining workflows
        4. Run log retention cleanup
        5. Close connections (handled by caller)
        """
        self._shutting_down = True
        logger.info("Server shutting down...")

        # Wait for blocked workflows with timeout
        active = self._orchestrator.get_active_workflows()
        if active:
            logger.info(f"Waiting for {len(active)} active workflows...")
            try:
                await asyncio.wait_for(
                    self._wait_for_workflows_to_finish(),
                    timeout=self._shutdown_timeout,
                )
            except TimeoutError:
                logger.warning("Shutdown timeout - cancelling remaining workflows")

        # Cancel any still-running workflows
        await self._orchestrator.cancel_all_workflows()

        # Persist final state (already done via repository on each update)
        logger.info("Final state persisted to database")

        # Run log retention cleanup
        cleanup_result = await self._log_retention.cleanup_on_shutdown()
        logger.info(
            "Cleanup complete",
            events_deleted=cleanup_result.events_deleted,
            workflows_deleted=cleanup_result.workflows_deleted,
        )

        logger.info("Server shutdown complete")

    async def _wait_for_workflows_to_finish(self) -> None:
        """Wait for all active workflows to complete."""
        while self._orchestrator.get_active_workflows():
            await asyncio.sleep(1)
