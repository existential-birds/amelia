"""Repository for workflow persistence operations."""

import json
from datetime import UTC, datetime

import aiosqlite

from amelia.server.database.connection import Database, SqliteValue
from amelia.server.exceptions import WorkflowNotFoundError
from amelia.server.models.events import WorkflowEvent
from amelia.server.models.state import (
    ServerExecutionState,
    WorkflowStatus,
    validate_transition,
)
from amelia.server.models.tokens import TokenSummary, TokenUsage


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

    async def list_active(
        self, worktree_path: str | None = None
    ) -> list[ServerExecutionState]:
        """List all active workflows.

        Args:
            worktree_path: Optional filter by worktree path.

        Returns:
            List of active workflows (pending, in_progress, blocked).
        """
        if worktree_path:
            rows = await self._db.fetch_all(
                """
                SELECT state_json FROM workflows
                WHERE status IN ('pending', 'in_progress', 'blocked')
                AND worktree_path = ?
                ORDER BY started_at DESC
                """,
                (worktree_path,),
            )
        else:
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

    # =========================================================================
    # Event Persistence
    # =========================================================================

    async def save_event(self, event: WorkflowEvent) -> None:
        """Persist workflow event to database.

        Args:
            event: The event to persist.
        """
        # Use Pydantic's serialization which handles nested types (Path, models, etc.)
        serialized = event.model_dump(mode="json")
        data_json = json.dumps(serialized["data"]) if serialized["data"] else None

        await self._db.execute(
            """
            INSERT INTO events (
                id, workflow_id, sequence, timestamp, agent,
                event_type, message, data_json, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.workflow_id,
                event.sequence,
                event.timestamp.isoformat(),
                event.agent,
                event.event_type.value,
                event.message,
                data_json,
                event.correlation_id,
            ),
        )

    async def get_max_event_sequence(self, workflow_id: str) -> int:
        """Get maximum event sequence number for a workflow.

        Args:
            workflow_id: The workflow ID.

        Returns:
            Maximum sequence number, or 0 if no events exist.
        """
        result = await self._db.fetch_scalar(
            "SELECT COALESCE(MAX(sequence), 0) FROM events WHERE workflow_id = ?",
            (workflow_id,),
        )
        return result if isinstance(result, int) else 0

    async def event_exists(self, event_id: str) -> bool:
        """Check if an event exists by ID.

        Args:
            event_id: The event ID to check.

        Returns:
            True if event exists, False otherwise.
        """
        result = await self._db.fetch_scalar(
            "SELECT 1 FROM events WHERE id = ? LIMIT 1",
            (event_id,),
        )
        return result is not None

    def _row_to_event(self, row: aiosqlite.Row) -> WorkflowEvent:
        """Convert database row to WorkflowEvent model.

        Handles conversion of the data_json column to the data field,
        parsing JSON when present.

        Args:
            row: Database row from events table.

        Returns:
            Validated WorkflowEvent model instance.
        """
        event_data = dict(row)
        # Parse JSON data field if present (column is data_json, model field is data)
        if event_data.get("data_json"):
            event_data["data"] = json.loads(event_data.pop("data_json"))
        else:
            event_data.pop("data_json", None)  # Remove None value
        return WorkflowEvent(**event_data)

    async def get_events_after(self, since_event_id: str) -> list[WorkflowEvent]:
        """Get all events after a specific event (for backfill on reconnect).

        Args:
            since_event_id: The event ID to start after.

        Returns:
            List of events after the given event, ordered by sequence.

        Raises:
            ValueError: If the since_event_id doesn't exist.
        """
        # First, get the workflow_id and sequence of the since event
        row = await self._db.fetch_one(
            "SELECT workflow_id, sequence FROM events WHERE id = ?",
            (since_event_id,),
        )

        if row is None:
            raise ValueError(f"Event {since_event_id} not found")

        workflow_id, since_sequence = row["workflow_id"], row["sequence"]

        # Get all events from same workflow with higher sequence
        rows = await self._db.fetch_all(
            """
            SELECT id, workflow_id, sequence, timestamp, agent, event_type,
                   message, data_json, correlation_id
            FROM events
            WHERE workflow_id = ? AND sequence > ?
            ORDER BY sequence ASC
            """,
            (workflow_id, since_sequence),
        )

        return [self._row_to_event(row) for row in rows]

    async def get_recent_events(
        self, workflow_id: str, limit: int = 50
    ) -> list[WorkflowEvent]:
        """Get the most recent events for a workflow.

        Args:
            workflow_id: The workflow to get events for.
            limit: Maximum number of events to return (default 50).

        Returns:
            List of events ordered by sequence ascending (oldest first).
        """
        # Guard against non-positive limits (SQLite treats LIMIT -1 as no limit)
        if limit <= 0:
            return []

        rows = await self._db.fetch_all(
            """
            SELECT id, workflow_id, sequence, timestamp, agent, event_type,
                   message, data_json, correlation_id
            FROM events
            WHERE workflow_id = ?
            ORDER BY sequence DESC
            LIMIT ?
            """,
            (workflow_id, limit),
        )

        # Reverse to get oldest first (UI expects chronological order)
        events = [self._row_to_event(row) for row in rows]
        events.reverse()
        return events

    # =========================================================================
    # Token Usage Persistence
    # =========================================================================

    async def save_token_usage(self, usage: TokenUsage) -> None:
        """Persist token usage record to database.

        Args:
            usage: The token usage record to persist.
        """
        await self._db.execute(
            """
            INSERT INTO token_usage (
                id, workflow_id, agent, model, input_tokens, output_tokens,
                cache_read_tokens, cache_creation_tokens, cost_usd,
                duration_ms, num_turns, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usage.id,
                usage.workflow_id,
                usage.agent,
                usage.model,
                usage.input_tokens,
                usage.output_tokens,
                usage.cache_read_tokens,
                usage.cache_creation_tokens,
                usage.cost_usd,
                usage.duration_ms,
                usage.num_turns,
                usage.timestamp.isoformat(),
            ),
        )

    async def get_token_usage(self, workflow_id: str) -> list[TokenUsage]:
        """Get all token usage records for a workflow.

        Args:
            workflow_id: The workflow ID to get token usage for.

        Returns:
            List of token usage records ordered by timestamp ascending.
        """
        rows = await self._db.fetch_all(
            """
            SELECT id, workflow_id, agent, model, input_tokens, output_tokens,
                   cache_read_tokens, cache_creation_tokens, cost_usd,
                   duration_ms, num_turns, timestamp
            FROM token_usage
            WHERE workflow_id = ?
            ORDER BY timestamp ASC
            """,
            (workflow_id,),
        )

        return [self._row_to_token_usage(row) for row in rows]

    async def get_token_summary(self, workflow_id: str) -> TokenSummary | None:
        """Get aggregated token usage summary for a workflow.

        Args:
            workflow_id: The workflow ID to get summary for.

        Returns:
            Token summary with totals and breakdown, or None if no usage exists.
        """
        usages = await self.get_token_usage(workflow_id)

        if not usages:
            return None

        return TokenSummary(
            total_input_tokens=sum(u.input_tokens for u in usages),
            total_output_tokens=sum(u.output_tokens for u in usages),
            total_cache_read_tokens=sum(u.cache_read_tokens for u in usages),
            total_cost_usd=sum(u.cost_usd for u in usages),
            total_duration_ms=sum(u.duration_ms for u in usages),
            total_turns=sum(u.num_turns for u in usages),
            breakdown=usages,
        )

    async def get_token_summaries_batch(
        self, workflow_ids: list[str]
    ) -> dict[str, TokenSummary | None]:
        """Get aggregated token usage summaries for multiple workflows.

        Fetches all token usage records for the given workflow IDs in a single
        query, then groups and aggregates them in Python. This solves the N+1
        query problem when listing workflows with token data.

        Args:
            workflow_ids: List of workflow IDs to get summaries for.

        Returns:
            Dict mapping workflow_id to TokenSummary (or None if no usage).
            All requested workflow_ids are included as keys.
        """
        if not workflow_ids:
            return {}

        # Build parameterized query with IN clause
        placeholders = ",".join("?" for _ in workflow_ids)
        rows = await self._db.fetch_all(
            f"""
            SELECT id, workflow_id, agent, model, input_tokens, output_tokens,
                   cache_read_tokens, cache_creation_tokens, cost_usd,
                   duration_ms, num_turns, timestamp
            FROM token_usage
            WHERE workflow_id IN ({placeholders})
            ORDER BY timestamp ASC
            """,
            list(workflow_ids),
        )

        # Group usages by workflow_id
        usages_by_workflow: dict[str, list[TokenUsage]] = {
            wid: [] for wid in workflow_ids
        }
        for row in rows:
            usage = self._row_to_token_usage(row)
            usages_by_workflow[usage.workflow_id].append(usage)

        # Build summaries for each workflow
        result: dict[str, TokenSummary | None] = {}
        for wid in workflow_ids:
            usages = usages_by_workflow[wid]
            if not usages:
                result[wid] = None
            else:
                result[wid] = TokenSummary(
                    total_input_tokens=sum(u.input_tokens for u in usages),
                    total_output_tokens=sum(u.output_tokens for u in usages),
                    total_cache_read_tokens=sum(u.cache_read_tokens for u in usages),
                    total_cost_usd=sum(u.cost_usd for u in usages),
                    total_duration_ms=sum(u.duration_ms for u in usages),
                    total_turns=sum(u.num_turns for u in usages),
                    breakdown=usages,
                )

        return result

    def _row_to_token_usage(self, row: aiosqlite.Row) -> TokenUsage:
        """Convert database row to TokenUsage model.

        Args:
            row: Database row from token_usage table.

        Returns:
            Validated TokenUsage model instance.
        """
        return TokenUsage(
            id=row["id"],
            workflow_id=row["workflow_id"],
            agent=row["agent"],
            model=row["model"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            cache_read_tokens=row["cache_read_tokens"],
            cache_creation_tokens=row["cache_creation_tokens"],
            cost_usd=row["cost_usd"],
            duration_ms=row["duration_ms"],
            num_turns=row["num_turns"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
        )
