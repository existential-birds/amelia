"""Repository for workflow persistence operations."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import asyncpg

from amelia.server.database.connection import Database, in_clause_placeholders
from amelia.server.exceptions import WorkflowNotFoundError
from amelia.server.models.events import PERSISTED_TYPES, WorkflowEvent
from amelia.server.models.state import (
    PlanCache,
    ServerExecutionState,
    WorkflowStatus,
    WorkflowType,
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
                workflow_type, profile_id, plan_cache, issue_cache
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
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
        )

    async def get(self, workflow_id: uuid.UUID) -> ServerExecutionState | None:
        """Get workflow by ID.

        Args:
            workflow_id: Workflow identifier.

        Returns:
            Workflow state or None if not found.
        """
        row = await self._db.fetch_one(
            """
            SELECT
                id, issue_id, worktree_path, status,
                created_at, started_at, completed_at, failure_reason,
                workflow_type, profile_id, plan_cache, issue_cache
            FROM workflows WHERE id = $1
            """,
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
            SELECT
                id, issue_id, worktree_path, status,
                created_at, started_at, completed_at, failure_reason,
                workflow_type, profile_id, plan_cache, issue_cache
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
                issue_cache = $8
            WHERE id = $9
            """,
            state.workflow_status,
            state.started_at,
            state.completed_at,
            state.failure_reason,
            state.workflow_type,
            state.profile_id,
            plan_cache_data,
            state.issue_cache,  # dict|None - asyncpg handles JSONB encoding
            state.id,
        )

    async def set_status(
        self,
        workflow_id: uuid.UUID,
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
        if new_status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED):
            completed_at = datetime.now(UTC)

        await self._db.execute(
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
        result = await self._db.fetch_one(
            "SELECT id FROM workflows WHERE id = $1",
            workflow_id,
        )
        if result is None:
            raise WorkflowNotFoundError(workflow_id)

        await self._db.execute(
            "UPDATE workflows SET plan_cache = $1 WHERE id = $2",
            plan_cache.model_dump(), workflow_id,
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
                SELECT
                    id, issue_id, worktree_path, status,
                    created_at, started_at, completed_at, failure_reason,
                    workflow_type, profile_id, plan_cache, issue_cache
                FROM workflows
                WHERE status IN ('pending', 'in_progress', 'blocked')
                AND worktree_path = $1
                ORDER BY started_at DESC
                """,
                worktree_path,
            )
        else:
            rows = await self._db.fetch_all(
                """
                SELECT
                    id, issue_id, worktree_path, status,
                    created_at, started_at, completed_at, failure_reason,
                    workflow_type, profile_id, plan_cache, issue_cache
                FROM workflows
                WHERE status IN ('pending', 'in_progress', 'blocked')
                ORDER BY started_at DESC
                """
            )
        return [self._row_to_state(row) for row in rows]

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
            SELECT
                id, issue_id, worktree_path, status,
                created_at, started_at, completed_at, failure_reason,
                workflow_type, profile_id, plan_cache, issue_cache
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
        conditions = []
        params: list[Any] = []
        param_idx = 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if worktree_path:
            conditions.append(f"worktree_path = ${param_idx}")
            params.append(worktree_path)
            param_idx += 1

        # Cursor-based pagination
        if after_started_at and after_id:
            conditions.append(
                f"(started_at < ${param_idx} OR (started_at = ${param_idx + 1} AND id < ${param_idx + 2}))"
            )
            params.extend([after_started_at, after_started_at, after_id])
            param_idx += 3

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
            SELECT
                id, issue_id, worktree_path, status,
                created_at, started_at, completed_at, failure_reason,
                workflow_type, profile_id, plan_cache, issue_cache
            FROM workflows
            WHERE {where_clause}
            ORDER BY started_at DESC NULLS LAST, id DESC
            LIMIT ${param_idx}
        """
        params.append(limit)

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
        conditions = []
        params: list[Any] = []
        param_idx = 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if worktree_path:
            conditions.append(f"worktree_path = ${param_idx}")
            params.append(worktree_path)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"SELECT COUNT(*) FROM workflows WHERE {where_clause}"
        count = await self._db.fetch_scalar(query, *params)
        return count if isinstance(count, int) else 0

    # =========================================================================
    # Event Persistence
    # =========================================================================

    async def save_event(self, event: WorkflowEvent) -> None:
        """Persist workflow event to workflow_log if it's a persisted type.

        Stream-only events (trace, streaming) are silently skipped.

        Args:
            event: The event to persist.
        """
        if event.event_type not in PERSISTED_TYPES:
            return

        serialized = event.model_dump(mode="json")
        data = serialized["data"] if serialized["data"] else None

        await self._db.execute(
            """
            INSERT INTO workflow_log (
                id, workflow_id, sequence, timestamp, event_type,
                level, agent, message, data, is_error
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            event.id,
            event.workflow_id,
            event.sequence,
            event.timestamp,
            event.event_type.value,
            event.level.value if event.level else "debug",
            event.agent,
            event.message,
            data,
            event.is_error,
        )

    async def get_max_event_sequence(self, workflow_id: uuid.UUID) -> int:
        """Get maximum event sequence number for a workflow.

        Args:
            workflow_id: The workflow ID.

        Returns:
            Maximum sequence number, or 0 if no events exist.
        """
        result = await self._db.fetch_scalar(
            "SELECT COALESCE(MAX(sequence), 0) FROM workflow_log WHERE workflow_id = $1",
            workflow_id,
        )
        return result if isinstance(result, int) else 0

    async def event_exists(self, event_id: uuid.UUID) -> bool:
        """Check if an event exists by ID.

        Args:
            event_id: The event ID to check.

        Returns:
            True if event exists, False otherwise.
        """
        result = await self._db.fetch_scalar(
            "SELECT 1 FROM workflow_log WHERE id = $1 LIMIT 1",
            event_id,
        )
        return result is not None

    def _row_to_event(self, row: asyncpg.Record) -> WorkflowEvent:
        """Convert database row to WorkflowEvent model.

        Args:
            row: Database row from workflow_log table.

        Returns:
            Validated WorkflowEvent model instance.
        """
        event_data = dict(row)
        if not event_data.get("data"):
            event_data.pop("data", None)

        return WorkflowEvent(**event_data)

    async def get_events_after(
        self, since_event_id: uuid.UUID, limit: int = 1000
    ) -> list[WorkflowEvent]:
        """Get events after a specific event (for backfill on reconnect).

        Args:
            since_event_id: The event ID to start after.
            limit: Maximum number of events to return (default 1000).

        Returns:
            List of events after the given event, ordered by sequence.

        Raises:
            ValueError: If the since_event_id doesn't exist.
        """
        row = await self._db.fetch_one(
            "SELECT workflow_id, sequence FROM workflow_log WHERE id = $1",
            since_event_id,
        )

        if row is None:
            raise ValueError(f"Event {since_event_id} not found")

        workflow_id, since_sequence = row["workflow_id"], row["sequence"]

        rows = await self._db.fetch_all(
            """
            SELECT id, workflow_id, sequence, timestamp, event_type,
                   level, agent, message, data, is_error
            FROM workflow_log
            WHERE workflow_id = $1 AND sequence > $2
            ORDER BY sequence ASC
            LIMIT $3
            """,
            workflow_id, since_sequence, limit,
        )

        return [self._row_to_event(row) for row in rows]

    async def get_recent_events(
        self, workflow_id: uuid.UUID, limit: int = 50
    ) -> list[WorkflowEvent]:
        """Get the most recent events for a workflow.

        Args:
            workflow_id: The workflow to get events for.
            limit: Maximum number of events to return (default 50).

        Returns:
            List of events ordered by sequence ascending (oldest first).
        """
        if limit <= 0:
            return []

        rows = await self._db.fetch_all(
            """
            SELECT id, workflow_id, sequence, timestamp, event_type,
                   level, agent, message, data, is_error
            FROM workflow_log
            WHERE workflow_id = $1
            ORDER BY sequence DESC
            LIMIT $2
            """,
            workflow_id, limit,
        )

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
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """,
            usage.id,
            usage.workflow_id,
            usage.agent,
            usage.model,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_tokens,
            usage.cache_creation_tokens,
            float(usage.cost_usd),
            usage.duration_ms,
            usage.num_turns,
            usage.timestamp,
        )

    async def get_token_usage(self, workflow_id: uuid.UUID) -> list[TokenUsage]:
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
            WHERE workflow_id = $1
            ORDER BY timestamp ASC
            """,
            workflow_id,
        )

        return [self._row_to_token_usage(row) for row in rows]

    async def get_token_summary(self, workflow_id: uuid.UUID) -> TokenSummary | None:
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
        self, workflow_ids: list[uuid.UUID]
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
        placeholders = in_clause_placeholders(len(workflow_ids))
        rows = await self._db.fetch_all(
            f"""
            SELECT id, workflow_id, agent, model, input_tokens, output_tokens,
                   cache_read_tokens, cache_creation_tokens, cost_usd,
                   duration_ms, num_turns, timestamp
            FROM token_usage
            WHERE workflow_id IN ({placeholders})
            ORDER BY timestamp ASC
            """,
            *workflow_ids,
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

    def _row_to_token_usage(self, row: asyncpg.Record) -> TokenUsage:
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
            timestamp=row["timestamp"],
        )

    # =========================================================================
    # Usage Aggregation
    # =========================================================================

    async def get_usage_summary(
        self,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        """Get aggregated usage summary for a date range.

        Args:
            start_date: Start of date range (inclusive).
            end_date: End of date range (inclusive).

        Returns:
            Dict with total_cost_usd, total_workflows, total_tokens, total_duration_ms,
            previous_period_cost_usd, successful_workflows, success_rate.
        """
        # Calculate previous period (same duration, immediately before)
        period_days = (end_date - start_date).days + 1
        prev_end_date = start_date - timedelta(days=1)
        prev_start_date = prev_end_date - timedelta(days=period_days - 1)

        # Current period token usage metrics
        row = await self._db.fetch_one(
            """
            SELECT
                COALESCE(SUM(t.cost_usd), 0) as total_cost_usd,
                COUNT(DISTINCT t.workflow_id) as total_workflows,
                COALESCE(SUM(t.input_tokens + t.output_tokens), 0) as total_tokens,
                COALESCE(SUM(t.duration_ms), 0) as total_duration_ms
            FROM token_usage t
            WHERE t.timestamp::date >= $1 AND t.timestamp::date <= $2
            """,
            start_date, end_date,
        )

        # Previous period cost
        prev_row = await self._db.fetch_one(
            """
            SELECT COALESCE(SUM(t.cost_usd), 0) as prev_cost_usd
            FROM token_usage t
            WHERE t.timestamp::date >= $1 AND t.timestamp::date <= $2
            """,
            prev_start_date, prev_end_date,
        )

        # Store token_usage-derived total_workflows for consistent response
        total_workflows_from_usage = row[1] if row else 0

        # Success metrics from workflows table
        # Count successful workflows that have completed_at in the date range
        success_row = await self._db.fetch_one(
            """
            SELECT
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful_workflows
            FROM workflows
            WHERE completed_at::date >= $1 AND completed_at::date <= $2
              AND status IN ('completed', 'failed', 'cancelled')
            """,
            start_date, end_date,
        )

        successful_workflows = success_row[0] if success_row and success_row[0] else 0
        # Use token_usage-derived total_workflows as denominator for consistency
        success_rate = (
            (successful_workflows / total_workflows_from_usage)
            if total_workflows_from_usage > 0
            else 0.0
        )

        return {
            "total_cost_usd": float(row[0]) if row else 0.0,
            "total_workflows": total_workflows_from_usage,
            "total_tokens": row[2] if row else 0,
            "total_duration_ms": row[3] if row else 0,
            "previous_period_cost_usd": float(prev_row[0]) if prev_row else 0.0,
            "successful_workflows": successful_workflows,
            "success_rate": float(success_rate),
        }

    async def get_usage_trend(
        self,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Get daily usage trend for a date range.

        Args:
            start_date: Start of date range (inclusive).
            end_date: End of date range (inclusive).

        Returns:
            List of dicts with date, cost_usd, workflows, by_model.
        """
        # Get daily totals
        rows = await self._db.fetch_all(
            """
            SELECT
                t.timestamp::date as date,
                SUM(t.cost_usd) as cost_usd,
                COUNT(DISTINCT t.workflow_id) as workflows
            FROM token_usage t
            WHERE t.timestamp::date >= $1 AND t.timestamp::date <= $2
            GROUP BY t.timestamp::date
            ORDER BY date
            """,
            start_date, end_date,
        )

        # Get per-model breakdown by day
        model_rows = await self._db.fetch_all(
            """
            SELECT
                t.timestamp::date as date,
                t.model,
                SUM(t.cost_usd) as cost_usd
            FROM token_usage t
            WHERE t.timestamp::date >= $1 AND t.timestamp::date <= $2
            GROUP BY t.timestamp::date, t.model
            ORDER BY date, cost_usd DESC
            """,
            start_date, end_date,
        )

        # Build lookup: date_str -> {model: cost}
        by_model_lookup: dict[str, dict[str, float]] = {}
        for model_row in model_rows:
            row_date = str(model_row[0])
            model = model_row[1]
            cost = float(model_row[2])
            if row_date not in by_model_lookup:
                by_model_lookup[row_date] = {}
            by_model_lookup[row_date][model] = cost

        return [
            {
                "date": str(row[0]),
                "cost_usd": float(row[1]),
                "workflows": row[2],
                "by_model": by_model_lookup.get(str(row[0]), {}),
            }
            for row in rows
        ]

    async def get_usage_by_model(
        self,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Get usage breakdown by model for a date range.

        Args:
            start_date: Start of date range (inclusive).
            end_date: End of date range (inclusive).

        Returns:
            List of dicts with model, workflows, tokens, cost_usd, trend,
            successful_workflows, success_rate.
        """
        # Get aggregated stats per model
        rows = await self._db.fetch_all(
            """
            SELECT
                t.model,
                COUNT(DISTINCT t.workflow_id) as workflows,
                SUM(t.input_tokens + t.output_tokens) as tokens,
                SUM(t.cost_usd) as cost_usd
            FROM token_usage t
            WHERE t.timestamp::date >= $1 AND t.timestamp::date <= $2
            GROUP BY t.model
            ORDER BY cost_usd DESC
            """,
            start_date, end_date,
        )

        # Get daily trend per model for sparklines
        trend_rows = await self._db.fetch_all(
            """
            SELECT
                t.model,
                t.timestamp::date as date,
                SUM(t.cost_usd) as cost_usd
            FROM token_usage t
            WHERE t.timestamp::date >= $1 AND t.timestamp::date <= $2
            GROUP BY t.model, t.timestamp::date
            ORDER BY t.model, date
            """,
            start_date, end_date,
        )

        # Build trend lookup: model -> {date: cost}
        trend_lookup: dict[str, dict[date, float]] = {}
        for trend_row in trend_rows:
            model = trend_row[0]
            row_date = trend_row[1]
            cost = float(trend_row[2])
            if model not in trend_lookup:
                trend_lookup[model] = {}
            trend_lookup[model][row_date] = cost

        # Generate full date range for consistent trend arrays
        num_days = (end_date - start_date).days + 1
        date_range = [
            start_date + timedelta(days=i) for i in range(num_days)
        ]

        # Get success metrics per model (join with workflows)
        success_rows = await self._db.fetch_all(
            """
            SELECT
                t.model,
                COUNT(DISTINCT t.workflow_id) as total_workflows,
                COUNT(DISTINCT CASE WHEN w.status = 'completed' THEN t.workflow_id END)
                    as successful_workflows
            FROM token_usage t
            JOIN workflows w ON t.workflow_id = w.id
            WHERE t.timestamp::date >= $1 AND t.timestamp::date <= $2
            GROUP BY t.model
            """,
            start_date, end_date,
        )

        # Build success lookup: model -> {total, successful}
        success_lookup: dict[str, dict[str, int]] = {}
        for success_row in success_rows:
            model = success_row[0]
            total = success_row[1]
            successful = success_row[2]
            success_lookup[model] = {"total": total, "successful": successful}

        return [
            {
                "model": row[0],
                "workflows": row[1],
                "tokens": row[2],
                "cost_usd": float(row[3]),
                "trend": [
                    float(trend_lookup.get(row[0], {}).get(d, 0.0)) for d in date_range
                ],
                "successful_workflows": success_lookup.get(row[0], {}).get(
                    "successful", 0
                ),
                "success_rate": round(
                    success_lookup.get(row[0], {}).get("successful", 0)
                    / total,
                    4,
                )
                if (total := success_lookup.get(row[0], {}).get("total"))
                else 0.0,
            }
            for row in rows
        ]
