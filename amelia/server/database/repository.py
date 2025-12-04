"""Repository for workflow persistence operations."""

from datetime import UTC, datetime

from amelia.server.database.connection import Database, SqliteValue
from amelia.server.exceptions import WorkflowNotFoundError
from amelia.server.models.state import (
    ServerExecutionState,
    WorkflowStatus,
    validate_transition,
)


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

    async def create(self, state: ServerExecutionState) -> None:
        """Create a new workflow.

        Args:
            state: Initial workflow state.
        """
        await self._db.execute(
            """
            INSERT INTO workflows (
                id, issue_id, worktree_path, worktree_name,
                status, started_at, completed_at, failure_reason, state_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state.id,
                state.issue_id,
                state.worktree_path,
                state.worktree_name,
                state.workflow_status,
                state.started_at,
                state.completed_at,
                state.failure_reason,
                state.model_dump_json(),
            ),
        )

    async def get(self, workflow_id: str) -> ServerExecutionState | None:
        """Get workflow by ID.

        Args:
            workflow_id: Workflow identifier.

        Returns:
            Workflow state or None if not found.
        """
        row = await self._db.fetch_one(
            "SELECT state_json FROM workflows WHERE id = ?",
            (workflow_id,),
        )
        if row is None:
            return None
        return ServerExecutionState.model_validate_json(row[0])

    async def get_by_worktree(
        self,
        worktree_path: str,
    ) -> ServerExecutionState | None:
        """Get active workflow for a worktree.

        Args:
            worktree_path: Worktree path to check.

        Returns:
            Active workflow or None if no active workflow.
        """
        row = await self._db.fetch_one(
            """
            SELECT state_json FROM workflows
            WHERE worktree_path = ?
            AND status IN ('pending', 'in_progress', 'blocked')
            """,
            (worktree_path,),
        )
        if row is None:
            return None
        return ServerExecutionState.model_validate_json(row[0])

    async def update(self, state: ServerExecutionState) -> None:
        """Update workflow state.

        Args:
            state: Updated workflow state.
        """
        await self._db.execute(
            """
            UPDATE workflows SET
                status = ?,
                started_at = ?,
                completed_at = ?,
                failure_reason = ?,
                state_json = ?
            WHERE id = ?
            """,
            (
                state.workflow_status,
                state.started_at,
                state.completed_at,
                state.failure_reason,
                state.model_dump_json(),
                state.id,
            ),
        )

    async def set_status(
        self,
        workflow_id: str,
        new_status: WorkflowStatus,
        failure_reason: str | None = None,
    ) -> None:
        """Update workflow status with state machine validation.

        Args:
            workflow_id: Workflow to update.
            new_status: Target status.
            failure_reason: Optional failure reason (for failed status).

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidStateTransitionError: If transition is invalid.
        """
        workflow = await self.get(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(workflow_id)

        validate_transition(workflow.workflow_status, new_status)

        # Set completed_at for terminal states
        completed_at = None
        if new_status in ("completed", "failed", "cancelled"):
            completed_at = datetime.now(UTC)

        # NOTE: We update both indexed columns AND the JSON blob in one query.
        # This is more efficient than loading the full state and re-serializing.
        # If adding new fields, update both places to prevent drift.
        await self._db.execute(
            """
            UPDATE workflows SET
                status = ?,
                completed_at = ?,
                failure_reason = ?,
                state_json = json_set(state_json,
                    '$.workflow_status', ?,
                    '$.completed_at', ?,
                    '$.failure_reason', ?
                )
            WHERE id = ?
            """,
            (
                new_status,
                completed_at.isoformat() if completed_at else None,
                failure_reason,
                new_status,
                completed_at.isoformat() if completed_at else None,
                failure_reason,
                workflow_id,
            ),
        )

    async def list_active(self) -> list[ServerExecutionState]:
        """List all active workflows.

        Returns:
            List of active workflows (pending, in_progress, blocked).
        """
        rows = await self._db.fetch_all(
            """
            SELECT state_json FROM workflows
            WHERE status IN ('pending', 'in_progress', 'blocked')
            ORDER BY started_at DESC
            """
        )
        return [ServerExecutionState.model_validate_json(row[0]) for row in rows]

    async def count_active(self) -> int:
        """Count active workflows.

        Returns:
            Number of active workflows.
        """
        result = await self._db.fetch_scalar(
            """
            SELECT COUNT(*) FROM workflows
            WHERE status IN ('pending', 'in_progress', 'blocked')
            """
        )
        # COUNT(*) always returns int; use isinstance for type narrowing
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
        placeholders = ",".join("?" for _ in statuses)
        rows = await self._db.fetch_all(
            f"""
            SELECT state_json FROM workflows
            WHERE status IN ({placeholders})
            """,
            statuses,
        )
        return [ServerExecutionState.model_validate_json(row[0]) for row in rows]

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
        conditions = []
        params: list[SqliteValue] = []

        if status:
            conditions.append("status = ?")
            params.append(status)

        if worktree_path:
            conditions.append("worktree_path = ?")
            params.append(worktree_path)

        # Cursor-based pagination
        if after_started_at and after_id:
            conditions.append(
                "(started_at < ? OR (started_at = ? AND id < ?))"
            )
            params.extend([after_started_at.isoformat(), after_started_at.isoformat(), after_id])

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
            SELECT state_json FROM workflows
            WHERE {where_clause}
            ORDER BY started_at DESC NULLS LAST, id DESC
            LIMIT ?
        """
        params.append(limit)

        rows = await self._db.fetch_all(query, params)
        return [ServerExecutionState.model_validate_json(row[0]) for row in rows]

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
        conditions = []
        params: list[SqliteValue] = []

        if status:
            conditions.append("status = ?")
            params.append(status)

        if worktree_path:
            conditions.append("worktree_path = ?")
            params.append(worktree_path)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"SELECT COUNT(*) FROM workflows WHERE {where_clause}"
        count = await self._db.fetch_scalar(query, params)
        return count if isinstance(count, int) else 0
