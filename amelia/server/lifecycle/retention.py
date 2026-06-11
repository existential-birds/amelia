"""Retention service for cleaning up old workflow run data.

Trajectory files are the only persistent run history. Retention removes the
trajectory file (and its per-workflow directory) for finished workflows past
the cutoff, NULLs the thin index columns on ``workflows``, and then deletes
``workflows`` rows whose index columns are already NULL (swept in a prior
cycle) and whose ``completed_at`` is before the cutoff.
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
    workflows_deleted: int = 0
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

        trajectories_deleted, swept_ids = await self._cleanup_trajectories(cutoff_date)
        deletable_ids = await self._select_deletable_workflow_ids(cutoff_date, swept_ids)
        checkpoints_deleted = await self._cleanup_checkpoints(force_ids=deletable_ids)
        workflows_deleted = await self._delete_old_workflow_rows(deletable_ids)

        return CleanupResult(
            trajectories_deleted=trajectories_deleted,
            workflows_deleted=workflows_deleted,
            checkpoints_deleted=checkpoints_deleted,
        )

    async def _cleanup_trajectories(
        self, cutoff_date: datetime
    ) -> tuple[int, list[Any]]:
        """Remove trajectory files for finished workflows past the cutoff.

        Paths come from the thin index (``workflows.trajectory_path``). A
        missing file is not an error — the index columns are NULLed either
        way so the workflow no longer appears to have a trajectory.

        Args:
            cutoff_date: Workflows completed before this moment are swept.

        Returns:
            Number of workflows whose trajectory index was cleared, and their
            ids — row deletion must skip these so a swept row survives until
            the next cleanup cycle.
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
            return 0, []

        cleared_ids: list[Any] = []
        for row in rows:
            path = Path(row["trajectory_path"])
            # One directory per workflow — remove the whole directory so
            # nothing (temp files included) outlives the trajectory. A row whose
            # directory can't be removed keeps its index so a later sweep retries
            # rather than orphaning the directory with no pointer to it.
            if path.parent.is_dir():
                try:
                    shutil.rmtree(path.parent)
                except OSError:
                    logger.warning(
                        "Failed to remove trajectory directory; keeping index",
                        workflow_id=row["id"],
                        path=str(path.parent),
                    )
                    continue
            cleared_ids.append(row["id"])

        if not cleared_ids:
            return 0, []

        cleared = await self._db.execute(
            """
            UPDATE workflows SET
                trajectory_path = NULL,
                total_cost_usd = NULL,
                total_tokens = NULL,
                total_duration_ms = NULL
            WHERE id = ANY($1::uuid[])
            """,
            cleared_ids,
        )
        logger.debug(
            "Swept trajectory files for finished workflows",
            count=cleared,
            cutoff=cutoff_date,
        )
        return cleared, cleared_ids

    async def _select_deletable_workflow_ids(
        self, cutoff_date: datetime, just_swept_ids: list[Any]
    ) -> list[Any]:
        """Select the workflow ids that this cycle is about to delete.

        Mirrors the WHERE clause of :meth:`_delete_old_workflow_rows` so the
        ids are known before deletion — their checkpoints must be cleaned up
        first or they would be orphaned once the row (the only pointer to the
        checkpoint thread) is gone.

        Rows are eligible only once their ``trajectory_path`` is NULL (meaning
        the trajectory sweep already ran for them), excluding rows swept in
        this same cycle, preserving the two-phase approach: first sweep files
        + NULL index columns, then on a later shutdown cycle delete the bare
        rows.

        Args:
            cutoff_date: Workflows completed before this moment are deletable.
            just_swept_ids: Workflow ids swept by this cycle's trajectory
                cleanup; these survive until the next cycle.

        Returns:
            Workflow ids the subsequent DELETE will remove.
        """
        rows = await self._db.fetch_all(
            """
            SELECT id FROM workflows
            WHERE status IN ('completed', 'failed', 'cancelled')
            AND completed_at < $1
            AND trajectory_path IS NULL
            AND NOT (id = ANY($2::uuid[]))
            """,
            cutoff_date,
            just_swept_ids,
        )
        return [row["id"] for row in rows]

    async def _delete_old_workflow_rows(self, deletable_ids: list[Any]) -> int:
        """Delete the workflow rows selected by :meth:`_select_deletable_workflow_ids`.

        Args:
            deletable_ids: Workflow ids to delete, already filtered to swept,
                finished, past-cutoff rows.

        Returns:
            Number of workflow rows deleted.
        """
        if not deletable_ids:
            return 0

        deleted = await self._db.execute(
            "DELETE FROM workflows WHERE id = ANY($1::uuid[])",
            deletable_ids,
        )
        if deleted:
            logger.debug("Deleted old workflow rows", count=deleted)
        return deleted

    async def _cleanup_checkpoints(self, force_ids: list[Any] | None = None) -> int:
        """Delete LangGraph checkpoints for finished workflows based on retention.

        Uses AsyncPostgresSaver.adelete_thread() for proper checkpoint cleanup,
        avoiding direct SQL queries against LangGraph's internal tables.

        Respects checkpoint_retention_days setting:
        - -1: Never delete checkpoints (useful for debugging)
        - 0: Delete immediately for all finished workflows
        - >0: Delete only for workflows finished more than N days ago

        Args:
            force_ids: Workflow ids whose checkpoints must be deleted regardless
                of the retention cutoff — their rows are about to be deleted, so
                their checkpoints would otherwise be orphaned. Deduped against
                the retention-eligible set so each checkpoint is deleted once.

        Returns:
            Number of workflows whose checkpoints were deleted.
        """
        retention_days = self._config.checkpoint_retention_days

        # No checkpointer means no checkpoints to delete
        if self._checkpointer is None:
            logger.debug("No checkpointer configured, skipping checkpoint cleanup")
            return 0

        checkpointer = self._checkpointer

        ids: set[str] = {str(wid) for wid in (force_ids or [])}

        # -1 means never delete on retention grounds (debugging mode); the
        # force_ids still get cleaned so their about-to-vanish rows don't orphan.
        if retention_days < 0:
            logger.debug(
                "Checkpoint retention pass disabled",
                checkpoint_retention_days=retention_days,
            )
        elif retention_days == 0:
            finished = await self._db.fetch_all(
                "SELECT id FROM workflows WHERE status IN ('completed', 'failed', 'cancelled')"
            )
            ids.update(str(row["id"]) for row in finished)
        else:
            cutoff = datetime.now(UTC) - timedelta(days=retention_days)
            finished = await self._db.fetch_all(
                "SELECT id FROM workflows WHERE status IN ('completed', 'failed', 'cancelled') AND completed_at < $1",
                cutoff,
            )
            ids.update(str(row["id"]) for row in finished)

        if not ids:
            return 0

        workflow_ids = list(ids)
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
