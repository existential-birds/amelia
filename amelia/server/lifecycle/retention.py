"""Retention service for cleaning up old workflow run data.

Trajectory files are the only persistent run history. Retention removes the
trajectory file (and its per-workflow directory) for finished workflows past
the cutoff and NULLs the thin index columns on ``workflows``.
"""

import asyncio
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import asyncpg
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


class CheckpointerProtocol(Protocol):
    """Protocol for LangGraph checkpoint operations."""

    async def adelete_thread(self, thread_id: str) -> None:
        """Delete all checkpoints for a thread."""
        ...


class ConfigProtocol(Protocol):
    """Protocol for config access."""

    log_retention_days: int
    checkpoint_retention_days: int


class CleanupResult(BaseModel):
    """Result of cleanup operation."""

    trajectories_deleted: int
    checkpoints_deleted: int = 0


class LogRetentionService:
    """Manages trajectory file and checkpoint cleanup on server shutdown.

    Cleanup runs only during graceful shutdown to:
    - Avoid runtime performance impact
    - Ensure cleanup completes before server exits
    - Keep implementation simple (no background tasks)
    """

    def __init__(
        self,
        db: DatabaseProtocol,
        config: ConfigProtocol,
        checkpointer: CheckpointerProtocol | None = None,
    ) -> None:
        """Initialize retention service.

        Args:
            db: Database connection.
            config: Server configuration with retention settings.
            checkpointer: LangGraph checkpointer for checkpoint cleanup.
        """
        self._db = db
        self._config = config
        self._checkpointer = checkpointer

    async def cleanup_on_shutdown(self) -> CleanupResult:
        """Execute retention policy cleanup during server shutdown."""
        logger.info(
            "Running trajectory retention cleanup",
            retention_days=self._config.log_retention_days,
        )

        cutoff_date = datetime.now(UTC) - timedelta(
            days=self._config.log_retention_days
        )

        trajectories_deleted = await self._cleanup_trajectories(cutoff_date)
        checkpoints_deleted = await self._cleanup_checkpoints()

        return CleanupResult(
            trajectories_deleted=trajectories_deleted,
            checkpoints_deleted=checkpoints_deleted,
        )

    async def _cleanup_trajectories(self, cutoff_date: datetime) -> int:
        """Remove trajectory files for finished workflows past the cutoff.

        Paths come from the thin index (``workflows.trajectory_path``). A
        missing file is not an error — the index columns are NULLed either
        way so the workflow no longer appears to have a trajectory.

        Args:
            cutoff_date: Workflows completed before this moment are swept.

        Returns:
            Number of workflows whose trajectory index was cleared.
        """
        rows = await self._db.fetch_all(
            """
            SELECT id, trajectory_path FROM workflows
            WHERE status IN ('completed', 'failed', 'cancelled')
            AND completed_at < $1
            AND trajectory_path IS NOT NULL
            """,
            cutoff_date,
        )
        if not rows:
            return 0

        for row in rows:
            path = Path(row["trajectory_path"])
            # One directory per workflow — remove the whole directory so
            # nothing (temp files included) outlives the trajectory.
            if path.parent.is_dir():
                shutil.rmtree(path.parent, ignore_errors=True)

        cleared = await self._db.execute(
            """
            UPDATE workflows SET
                trajectory_path = NULL,
                total_cost_usd = NULL,
                total_tokens = NULL,
                total_duration_ms = NULL
            WHERE status IN ('completed', 'failed', 'cancelled')
            AND completed_at < $1
            AND trajectory_path IS NOT NULL
            """,
            cutoff_date,
        )
        logger.debug(
            "Swept trajectory files for finished workflows",
            count=cleared,
            cutoff=cutoff_date,
        )
        return cleared

    async def _cleanup_checkpoints(self) -> int:
        """Delete LangGraph checkpoints for finished workflows based on retention.

        Uses AsyncPostgresSaver.adelete_thread() for proper checkpoint cleanup,
        avoiding direct SQL queries against LangGraph's internal tables.

        Respects checkpoint_retention_days setting:
        - -1: Never delete checkpoints (useful for debugging)
        - 0: Delete immediately for all finished workflows
        - >0: Delete only for workflows finished more than N days ago

        Returns:
            Number of workflows whose checkpoints were deleted.
        """
        retention_days = self._config.checkpoint_retention_days

        # -1 means never delete (debugging mode)
        if retention_days < 0:
            logger.debug(
                "Checkpoint cleanup disabled",
                checkpoint_retention_days=retention_days,
            )
            return 0

        # No checkpointer means no checkpoints to delete
        if self._checkpointer is None:
            logger.debug("No checkpointer configured, skipping checkpoint cleanup")
            return 0

        checkpointer = self._checkpointer

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

        async def delete_checkpoint(workflow_id: str) -> bool:
            """Delete a single checkpoint, returning True on success."""
            try:
                await checkpointer.adelete_thread(workflow_id)
                return True
            except asyncpg.PostgresError as e:
                logger.warning(
                    "Failed to delete checkpoint for workflow",
                    workflow_id=workflow_id,
                    error=str(e),
                )
                return False

        results = await asyncio.gather(*[delete_checkpoint(wid) for wid in workflow_ids])
        return sum(results)
