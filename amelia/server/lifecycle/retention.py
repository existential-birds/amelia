"""Log retention service for cleaning up old workflow data."""
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import aiosqlite
from loguru import logger
from pydantic import BaseModel


class DatabaseProtocol(Protocol):
    """Protocol for database operations."""

    async def execute(self, query: str, params: Sequence[Any] = ()) -> int:
        """Execute a query and return affected row count."""
        ...

    async def fetch_all(
        self, query: str, params: Sequence[Any] = ()
    ) -> list[aiosqlite.Row]:
        """Execute a query and return all rows."""
        ...


class ConfigProtocol(Protocol):
    """Protocol for config access."""

    log_retention_days: int
    log_retention_max_events: int
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
        db: Any,
        config: Any,
        checkpoint_path: Path | str | None = None,
    ) -> None:
        """Initialize retention service.

        Args:
            db: Database connection.
            config: Server configuration with retention settings.
            checkpoint_path: Path to LangGraph checkpoint database.
                If None, checkpoint cleanup is skipped.
        """
        self._db = db
        self._config = config
        self._checkpoint_path = (
            Path(checkpoint_path).expanduser().resolve()
            if checkpoint_path
            else None
        )

    async def cleanup_on_shutdown(self) -> CleanupResult:
        """Execute retention policy cleanup during server shutdown."""
        logger.info(
            "Running log retention cleanup",
            retention_days=self._config.log_retention_days,
            max_events=self._config.log_retention_max_events,
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
                AND completed_at < ?
            )
            """,
            (cutoff_date.isoformat(),),
        )

        workflows_deleted = await self._db.execute(
            """
            DELETE FROM workflows
            WHERE id NOT IN (SELECT DISTINCT workflow_id FROM workflow_log)
            AND status IN ('completed', 'failed', 'cancelled')
            AND completed_at < ?
            """,
            (cutoff_date.isoformat(),),
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

        if not self._checkpoint_path or not self._checkpoint_path.exists():
            return 0

        # Build query based on retention days
        if retention_days == 0:
            # Delete immediately for all finished workflows
            query = """
                SELECT id FROM workflows
                WHERE status IN ('completed', 'failed', 'cancelled')
            """
            params: tuple[Any, ...] = ()
        else:
            # Delete only for workflows past retention period
            cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)
            query = """
                SELECT id FROM workflows
                WHERE status IN ('completed', 'failed', 'cancelled')
                AND completed_at < ?
            """
            params = (cutoff_date.isoformat(),)

        finished_workflows = await self._db.fetch_all(query, params)

        if not finished_workflows:
            return 0

        workflow_ids = [row["id"] for row in finished_workflows]
        logger.debug(
            "Cleaning checkpoints for finished workflows",
            count=len(workflow_ids),
            retention_days=retention_days,
        )

        total_deleted = 0
        try:
            async with aiosqlite.connect(str(self._checkpoint_path)) as conn:
                # Delete from checkpoints table (thread_id = workflow_id)
                placeholders = ",".join("?" * len(workflow_ids))
                cursor = await conn.execute(
                    f"DELETE FROM checkpoints WHERE thread_id IN ({placeholders})",
                    workflow_ids,
                )
                total_deleted += cursor.rowcount

                # Delete from writes table
                cursor = await conn.execute(
                    f"DELETE FROM writes WHERE thread_id IN ({placeholders})",
                    workflow_ids,
                )
                total_deleted += cursor.rowcount

                await conn.commit()
        except Exception as e:
            # Log but don't fail shutdown on checkpoint cleanup errors
            logger.warning("Failed to cleanup checkpoints", error=str(e))

        return total_deleted
