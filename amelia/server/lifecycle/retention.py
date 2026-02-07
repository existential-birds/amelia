"""Log retention service for cleaning up old workflow data."""

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from loguru import logger
from pydantic import BaseModel


class DatabaseProtocol(Protocol):
    """Protocol for database operations."""

    async def execute(self, query: str, *args: Any) -> int:
        """Execute a query and return affected row count."""
        ...

    async def fetch_all(
        self, query: str, *args: Any
    ) -> list[Any]:
        """Execute a query and return all rows."""
        ...


class ConfigProtocol(Protocol):
    """Protocol for config access."""

    log_retention_days: int
    checkpoint_retention_days: int


class CleanupResult(BaseModel):
    """Result of cleanup operation."""

    events_deleted: int
    workflows_deleted: int
    checkpoints_deleted: int = 0


class LogRetentionService:
    """Manages event log and checkpoint cleanup on server shutdown.

    Cleanup runs only during graceful shutdown to:
    - Avoid runtime performance impact
    - Ensure cleanup completes before server exits
    - Keep implementation simple (no background tasks)
    """

    def __init__(
        self,
        db: DatabaseProtocol,
        config: ConfigProtocol,
    ) -> None:
        """Initialize retention service.

        Args:
            db: Database connection.
            config: Server configuration with retention settings.
        """
        self._db = db
        self._config = config

    async def cleanup_on_shutdown(self) -> CleanupResult:
        """Execute retention policy cleanup during server shutdown."""
        logger.info(
            "Running log retention cleanup",
            retention_days=self._config.log_retention_days,
        )

        cutoff_date = datetime.now(UTC) - timedelta(
            days=self._config.log_retention_days
        )

        events_deleted = await self._db.execute(
            """
            DELETE FROM workflow_log
            WHERE workflow_id IN (
                SELECT id FROM workflows
                WHERE status IN ('completed', 'failed', 'cancelled')
                AND completed_at < $1
            )
            """,
            cutoff_date,
        )

        workflows_deleted = await self._db.execute(
            """
            DELETE FROM workflows
            WHERE id NOT IN (SELECT DISTINCT workflow_id FROM workflow_log)
            AND status IN ('completed', 'failed', 'cancelled')
            AND completed_at < $1
            """,
            cutoff_date,
        )

        checkpoints_deleted = await self._cleanup_checkpoints()

        return CleanupResult(
            events_deleted=events_deleted,
            workflows_deleted=workflows_deleted,
            checkpoints_deleted=checkpoints_deleted,
        )

    async def _cleanup_checkpoints(self) -> int:
        """Delete LangGraph checkpoints for finished workflows based on retention.

        Respects checkpoint_retention_days setting:
        - -1: Never delete checkpoints (useful for debugging)
        - 0: Delete immediately for all finished workflows
        - >0: Delete only for workflows finished more than N days ago

        Returns:
            Number of checkpoint entries deleted.
        """
        retention_days = self._config.checkpoint_retention_days

        # -1 means never delete (debugging mode)
        if retention_days < 0:
            logger.debug(
                "Checkpoint cleanup disabled",
                checkpoint_retention_days=retention_days,
            )
            return 0

        # Build query based on retention days
        if retention_days == 0:
            finished = await self._db.fetch_all(
                "SELECT id FROM workflows WHERE status IN ('completed', 'failed', 'cancelled')"
            )
        else:
            cutoff = datetime.now(UTC) - timedelta(days=retention_days)
            finished = await self._db.fetch_all(
                "SELECT id FROM workflows WHERE status IN ('completed', 'failed', 'cancelled') AND completed_at < $1",
                cutoff,
            )

        if not finished:
            return 0

        workflow_ids = [str(row["id"]) for row in finished]
        logger.debug(
            "Cleaning checkpoints for finished workflows",
            count=len(workflow_ids),
            retention_days=retention_days,
        )

        total_deleted = 0
        try:
            for wf_id in workflow_ids:
                r1 = await self._db.execute(
                    "DELETE FROM checkpoints WHERE thread_id = $1", wf_id
                )
                r2 = await self._db.execute(
                    "DELETE FROM writes WHERE thread_id = $1", wf_id
                )
                total_deleted += r1 + r2
        except Exception as e:
            logger.warning("Failed to cleanup checkpoints", error=str(e))

        return total_deleted
