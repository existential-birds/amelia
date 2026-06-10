"""Repository for workflow persistence operations."""

import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import asyncpg
from loguru import logger

from amelia.server.database.connection import Database, in_clause_placeholders
from amelia.server.exceptions import WorkflowNotFoundError
from amelia.server.models.state import (
    PlanCache,
    ServerExecutionState,
    WorkflowStatus,
    WorkflowType,
    validate_transition,
)


if TYPE_CHECKING:
    from harbor.models.trajectories import FinalMetrics


# Workflow SELECT column list. Order is cosmetic; _row_to_state reads all fields by name.
_WORKFLOW_COLUMNS = (
    "id, issue_id, worktree_path, status, "
    "created_at, started_at, completed_at, failure_reason, "
    "workflow_type, profile_id, plan_cache, issue_cache, "
    "base_commit, branch, "
    "trajectory_path, total_cost_usd, total_tokens, total_duration_ms"
)

_ACTIVE_STATUS_SQL = "status IN ('pending', 'in_progress', 'blocked')"


def _build_workflow_filters(
    status: WorkflowStatus | None = None,
    worktree_path: str | None = None,
    after_started_at: datetime | None = None,
    after_id: str | None = None,
) -> tuple[list[str], list[Any]]:
    """Build workflow WHERE conditions and parameters.

    Pure and DB-free: appends, in order, an equality clause for ``status`` and
    ``worktree_path`` when truthy, then a cursor clause when both
    ``after_started_at`` and ``after_id`` are truthy. Placeholders number
    sequentially from ``$1``; callers derive the next index as
    ``len(params) + 1``.

    Returns:
        Tuple of (conditions, params).
    """
    conditions: list[str] = []
    params: list[Any] = []

    if status is not None:
        params.append(status)
        conditions.append(f"status = ${len(params)}")

    if worktree_path is not None:
        params.append(worktree_path)
        conditions.append(f"worktree_path = ${len(params)}")

    if after_started_at and after_id:
        idx = len(params) + 1
        conditions.append(
            f"(started_at < ${idx} OR (started_at = ${idx + 1} AND id < ${idx + 2}))"
        )
        params.extend([after_started_at, after_started_at, after_id])

    return conditions, params


class WorkflowRepository:
    """Repository for workflow CRUD operations.

    Handles persistence and retrieval of workflow state,
    with state machine validation on status transitions.
    """

    def __init__(self, db: Database):
        """Initialize repository.

        Args:
            db: Database connection.
        """
        self._db = db

    @property
    def db(self) -> Database:
        """Expose database connection for shared access.

        Returns:
            The underlying Database instance.
        """
        return self._db

    def _row_to_state(self, row: asyncpg.Record) -> ServerExecutionState:
        """Convert database row to ServerExecutionState.

        Args:
            row: Database row with workflow columns.

        Returns:
            ServerExecutionState instance.
        """
        plan_cache = None
        if row["plan_cache"]:
            plan_cache = PlanCache.model_validate(row["plan_cache"])

        # issue_cache is dict|None - JSONB in DB, asyncpg returns dict directly
        issue_cache = row["issue_cache"]

        return ServerExecutionState(
            id=row["id"],
            issue_id=row["issue_id"],
            worktree_path=row["worktree_path"],
            workflow_type=WorkflowType(row["workflow_type"]) if row["workflow_type"] else WorkflowType.FULL,
            profile_id=row["profile_id"],
            plan_cache=plan_cache,
            issue_cache=issue_cache,
            workflow_status=row["status"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            failure_reason=row["failure_reason"],
            base_commit=row["base_commit"],
            branch=row["branch"],
            trajectory_path=row["trajectory_path"],
            total_cost_usd=row["total_cost_usd"],
            total_tokens=row["total_tokens"],
            total_duration_ms=row["total_duration_ms"],
        )

    async def create(self, state: ServerExecutionState) -> None:
        """Create a new workflow.

        Args:
            state: Initial workflow state.
        """
        # JSONB columns: pass dicts directly (asyncpg codec handles encoding)
        plan_cache_data = state.plan_cache.model_dump() if state.plan_cache else None

        await self._db.execute(
            """
            INSERT INTO workflows (
                id, issue_id, worktree_path,
                status, created_at, started_at, completed_at, failure_reason,
                workflow_type, profile_id, plan_cache, issue_cache, base_commit,
                branch
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            """,
            state.id,
            state.issue_id,
            state.worktree_path,
            state.workflow_status,
            state.created_at,
            state.started_at,
            state.completed_at,
            state.failure_reason,
            state.workflow_type,
            state.profile_id,
            plan_cache_data,
            state.issue_cache,  # dict|None - asyncpg handles JSONB encoding
            state.base_commit,
            state.branch,
        )

    async def get(self, workflow_id: uuid.UUID) -> ServerExecutionState | None:
        """Get workflow by ID.

        Args:
            workflow_id: Workflow identifier.

        Returns:
            Workflow state or None if not found.
        """
        row = await self._db.fetch_one(
            f"SELECT {_WORKFLOW_COLUMNS} FROM workflows WHERE id = $1",
            workflow_id,
        )
        if row is None:
            return None

        return self._row_to_state(row)

    async def get_by_worktree(
        self,
        worktree_path: str,
        statuses: tuple[WorkflowStatus, ...] = (WorkflowStatus.IN_PROGRESS, WorkflowStatus.BLOCKED),
    ) -> ServerExecutionState | None:
        """Get workflow for a worktree matching specified statuses.

        By default, only returns workflows that are actively running (in_progress
        or blocked). This excludes pending workflows because multiple pending
        workflows on the same worktree are allowed by design.

        Args:
            worktree_path: Worktree path to check.
            statuses: Workflow statuses to match. Defaults to ('in_progress', 'blocked').

        Returns:
            Matching workflow or None if no workflow matches.
        """
        placeholders = in_clause_placeholders(len(statuses), start=2)
        row = await self._db.fetch_one(
            f"""
            SELECT {_WORKFLOW_COLUMNS}
            FROM workflows
            WHERE worktree_path = $1
            AND status IN ({placeholders})
            """,
            worktree_path, *statuses,
        )
        if row is None:
            return None

        return self._row_to_state(row)

    async def update(self, state: ServerExecutionState) -> None:
        """Update workflow state.

        Args:
            state: Updated workflow state.
        """
        # JSONB columns: pass dicts directly (asyncpg codec handles encoding)
        plan_cache_data = state.plan_cache.model_dump() if state.plan_cache else None

        await self._db.execute(
            """
            UPDATE workflows SET
                status = $1,
                started_at = $2,
                completed_at = $3,
                failure_reason = $4,
                workflow_type = $5,
                profile_id = $6,
                plan_cache = $7,
                issue_cache = $8,
                base_commit = $9,
                branch = $10
            WHERE id = $11
            """,
            state.workflow_status,
            state.started_at,
            state.completed_at,
            state.failure_reason,
            state.workflow_type,
            state.profile_id,
            plan_cache_data,
            state.issue_cache,  # dict|None - asyncpg handles JSONB encoding
            state.base_commit,
            state.branch,
            state.id,
        )

    async def set_status(
        self,
        workflow_id: uuid.UUID,
        new_status: WorkflowStatus,
        failure_reason: str | None = None,
    ) -> None:
        """Update workflow status with state machine validation.

        Atomic: reads the current status under a ``SELECT … FOR UPDATE`` row lock
        inside a transaction, so concurrent transitions can never corrupt the row.

        Terminal precedence (#604): a completion overrides a concurrent
        cancellation (``CANCELLED`` → ``COMPLETED``). An immutable terminal row
        (``COMPLETED`` or ``CANCELLED``) is otherwise frozen — any other
        transition against it is absorbed as a no-op. ``FAILED`` is *not*
        immutable: ``VALID_TRANSITIONS[FAILED] = {IN_PROGRESS}`` (resumable via
        recovery — see the orchestrator resume path), so ``FAILED`` rows and all
        non-terminal source rows go through the usual ``validate_transition``
        state-machine check (a duplicate ``FAILED`` therefore raises rather than
        being absorbed).

        Silent absorption note: if the row is already in an immutable terminal
        state and the caller supplies a ``failure_reason`` that will be dropped by
        the no-op, a ``WARNING`` is emitted so the lost diagnostic is visible in
        logs; no exception is raised. Callers that must guarantee failure
        diagnostics are persisted should check the current status first.

        Args:
            workflow_id: Workflow to update.
            new_status: Target status.
            failure_reason: Optional failure reason (for failed status).

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidStateTransitionError: If a non-terminal transition is invalid.
        """
        async with self._db.transaction() as conn:
            row = await conn.fetchrow(
                "SELECT status FROM workflows WHERE id = $1 FOR UPDATE",
                workflow_id,
            )
            if row is None:
                raise WorkflowNotFoundError(workflow_id)

            current = WorkflowStatus(row["status"])

            # Resolve against the locked status, in priority order:
            if current == WorkflowStatus.CANCELLED and new_status == WorkflowStatus.COMPLETED:
                pass  # a completion overrides a concurrent cancellation (#604) — apply it
            elif current in (WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED):
                # Terminal row is otherwise immutable — absorb as a no-op. Surface
                # any diagnostic that the no-op would silently discard.
                if failure_reason is not None:
                    logger.warning(
                        "status update absorbed (workflow already terminal); failure_reason dropped",
                        workflow_id=workflow_id,
                        current_status=current,
                        new_status=new_status,
                        has_failure_reason=True,
                    )
                return
            else:
                validate_transition(current, new_status)  # non-terminal: state machine rules

            completed_at = None
            if new_status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED):
                completed_at = datetime.now(UTC)

            await conn.execute(
                """
                UPDATE workflows SET
                    status = $1,
                    completed_at = $2,
                    failure_reason = $3
                WHERE id = $4
                """,
                new_status,
                completed_at,
                failure_reason,
                workflow_id,
            )

    async def update_plan_cache(
        self,
        workflow_id: uuid.UUID,
        plan_cache: PlanCache,
    ) -> None:
        """Update plan_cache column directly without loading full state.

        This is used by _sync_plan_from_checkpoint to efficiently update
        plan data from the LangGraph checkpoint without re-serializing
        the entire ServerExecutionState.

        Args:
            workflow_id: Workflow to update.
            plan_cache: PlanCache instance to serialize and store.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
        """
        rows_affected = await self._db.execute(
            "UPDATE workflows SET plan_cache = $1 WHERE id = $2",
            plan_cache.model_dump(), workflow_id,
        )
        if rows_affected == 0:
            raise WorkflowNotFoundError(workflow_id)

    async def set_trajectory_index(
        self,
        workflow_id: uuid.UUID,
        path: Path,
        final_metrics: "FinalMetrics | None",
        execution_duration_ms: int | None = None,
    ) -> None:
        """Persist the thin trajectory index columns for a finalized workflow.

        Single UPDATE writing ``trajectory_path``, ``total_cost_usd``,
        ``total_tokens``, and ``total_duration_ms`` from the trajectory's
        final metrics and driver-reported execution time.

        Args:
            workflow_id: Workflow whose index columns to set.
            path: Canonical trajectory file path.
            final_metrics: Parent trajectory final metrics, if available.
            execution_duration_ms: Sum of driver-reported agent execution times
                in milliseconds, stored directly as ``total_duration_ms``. Left
                NULL when drivers do not track duration; never substituted with
                wall-clock, which would conflate human approval-wait time into
                the metric for BLOCKED workflows.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
        """
        total_cost: float | None = None
        total_tokens: int | None = None
        if final_metrics is not None:
            total_cost = final_metrics.total_cost_usd
            prompt = final_metrics.total_prompt_tokens
            completion = final_metrics.total_completion_tokens
            if prompt is not None or completion is not None:
                total_tokens = (prompt or 0) + (completion or 0)

        rows_affected = await self._db.execute(
            """
            UPDATE workflows SET
                trajectory_path = $1,
                total_cost_usd = $2,
                total_tokens = $3,
                total_duration_ms = $4::bigint
            WHERE id = $5
            """,
            str(path),
            total_cost,
            total_tokens,
            execution_duration_ms,
            workflow_id,
        )
        if rows_affected == 0:
            raise WorkflowNotFoundError(workflow_id)

    async def list_trajectory_paths(
        self,
        start_date: date,
        end_date: date,
    ) -> list[tuple[str, date, int | None]]:
        """List trajectory index rows for workflows completed in a date range.

        Args:
            start_date: First completion date (inclusive).
            end_date: Last completion date (inclusive).

        Returns:
            ``(trajectory_path, completed_date, total_duration_ms)`` per
            workflow with a non-null ``trajectory_path``, ordered by
            completion time.
        """
        rows = await self._db.fetch_all(
            """
            SELECT trajectory_path, completed_at::date, total_duration_ms
            FROM workflows
            WHERE trajectory_path IS NOT NULL
              AND completed_at::date >= $1
              AND completed_at::date <= $2
            ORDER BY completed_at
            """,
            start_date,
            end_date,
        )
        return [(row[0], row[1], row[2]) for row in rows]

    async def list_active(
        self, worktree_path: str | None = None
    ) -> list[ServerExecutionState]:
        """List all active workflows.

        Args:
            worktree_path: Optional filter by worktree path.

        Returns:
            List of active workflows (pending, in_progress, blocked).
        """
        conditions, params = _build_workflow_filters(worktree_path=worktree_path)
        where_clause = " AND ".join([_ACTIVE_STATUS_SQL, *conditions])
        rows = await self._db.fetch_all(
            f"SELECT {_WORKFLOW_COLUMNS} FROM workflows "
            f"WHERE {where_clause} ORDER BY started_at DESC",
            *params,
        )
        return [self._row_to_state(row) for row in rows]

    async def count_active(self) -> int:
        """Count active workflows.

        Returns:
            Number of active workflows.
        """
        result = await self._db.fetch_scalar(
            f"SELECT COUNT(*) FROM workflows WHERE {_ACTIVE_STATUS_SQL}"
        )
        # Type narrowing for asyncpg return type (COUNT returns int but fetch_scalar returns Any)
        return result if isinstance(result, int) else 0

    async def find_by_status(
        self,
        statuses: list[WorkflowStatus],
    ) -> list[ServerExecutionState]:
        """Find workflows by status.

        Args:
            statuses: List of statuses to match.

        Returns:
            List of matching workflows.
        """
        placeholders = in_clause_placeholders(len(statuses))
        rows = await self._db.fetch_all(
            f"""
            SELECT {_WORKFLOW_COLUMNS}
            FROM workflows
            WHERE status IN ({placeholders})
            """,
            *statuses,
        )
        return [self._row_to_state(row) for row in rows]

    async def list_workflows(
        self,
        status: WorkflowStatus | None = None,
        worktree_path: str | None = None,
        limit: int = 20,
        after_started_at: datetime | None = None,
        after_id: str | None = None,
    ) -> list[ServerExecutionState]:
        """List workflows with cursor-based pagination.

        Args:
            status: Optional status filter.
            worktree_path: Optional worktree path filter.
            limit: Maximum number of workflows to return.
            after_started_at: Cursor for pagination (started_at).
            after_id: Cursor for pagination (id).

        Returns:
            List of workflows matching filters.
        """
        conditions, params = _build_workflow_filters(
            status=status,
            worktree_path=worktree_path,
            after_started_at=after_started_at,
            after_id=after_id,
        )
        where_clause = " AND ".join(conditions) if conditions else "1=1"

        params.append(limit)
        query = (
            f"SELECT {_WORKFLOW_COLUMNS} FROM workflows "
            f"WHERE {where_clause} "
            f"ORDER BY started_at DESC NULLS LAST, id DESC "
            f"LIMIT ${len(params)}"
        )

        rows = await self._db.fetch_all(query, *params)
        return [self._row_to_state(row) for row in rows]

    async def count_workflows(
        self,
        status: WorkflowStatus | None = None,
        worktree_path: str | None = None,
    ) -> int:
        """Count workflows matching filters.

        Args:
            status: Optional status filter.
            worktree_path: Optional worktree path filter.

        Returns:
            Number of workflows matching filters.
        """
        conditions, params = _build_workflow_filters(
            status=status,
            worktree_path=worktree_path,
        )
        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"SELECT COUNT(*) FROM workflows WHERE {where_clause}"
        count = await self._db.fetch_scalar(query, *params)
        return count if isinstance(count, int) else 0
