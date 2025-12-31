"""Log retention service for cleaning up old workflow data."""
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from loguru import logger
from pydantic import BaseModel


class DatabaseProtocol(Protocol):
    """Protocol for database operations."""

    async def execute(self, query: str, params: tuple[Any, ...] = ()) -> int:
        """Execute a query and return affected row count."""
        ...


class ConfigProtocol(Protocol):
    """Protocol for config access."""

    log_retention_days: int
    log_retention_max_events: int


class CleanupResult(BaseModel):
    """Result of cleanup operation."""

    events_deleted: int
    workflows_deleted: int


class LogRetentionService:
    """Manages event log cleanup on server shutdown.

    Cleanup runs only during graceful shutdown to:
    - Avoid runtime performance impact
    - Ensure cleanup completes before server exits
    - Keep implementation simple (no background tasks)
    """

    def __init__(self, db: Any, config: Any) -> None:
        """Initialize retention service.

        Args:
            db: Database connection.
            config: Server configuration with retention settings.
        """
        self._db = db
        self._config = config

    async def cleanup_on_shutdown(self) -> CleanupResult:
        """Execute retention policy cleanup during server shutdown.

        Deletes:
        1. Events from workflows completed/failed/cancelled more than
           retention_days ago
        2. Workflows that are past retention and have no remaining events

        Returns:
            CleanupResult with counts of deleted records.
        """
        logger.info(
            "Running log retention cleanup",
            retention_days=self._config.log_retention_days,
            max_events=self._config.log_retention_max_events,
        )

        cutoff_date = datetime.now(UTC) - timedelta(
            days=self._config.log_retention_days
        )

        # Delete old events from completed/failed/cancelled workflows
        events_deleted = await self._db.execute(
            """
            DELETE FROM events
            WHERE workflow_id IN (
                SELECT id FROM workflows
                WHERE status IN ('completed', 'failed', 'cancelled')
                AND completed_at < ?
            )
            """,
            (cutoff_date.isoformat(),),
        )

        # Delete workflows past retention with no remaining events
        # Only delete workflows that are also past the retention cutoff
        # to avoid purging recent workflows that haven't emitted events yet
        workflows_deleted = await self._db.execute(
            """
            DELETE FROM workflows
            WHERE id NOT IN (SELECT DISTINCT workflow_id FROM events)
            AND status IN ('completed', 'failed', 'cancelled')
            AND completed_at < ?
            """,
            (cutoff_date.isoformat(),),
        )

        logger.info(
            "Cleanup complete",
            events_deleted=events_deleted,
            workflows_deleted=workflows_deleted,
        )

        return CleanupResult(
            events_deleted=events_deleted,
            workflows_deleted=workflows_deleted,
        )
