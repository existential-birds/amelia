"""Tests for event filtering in workflow_log persistence.

This module tests the PERSISTED_TYPES filtering logic in the repository's
save_event() method. Events not in PERSISTED_TYPES (trace events like
claude_thinking, claude_tool_call, etc.) are stream-only and not persisted
to the workflow_log table.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import aiosqlite
import pytest

from amelia.server.database.connection import Database
from amelia.server.database.repository import WorkflowRepository
from amelia.server.models import EventType
from amelia.server.models.events import (
    PERSISTED_TYPES,
    EventLevel,
    WorkflowEvent,
)
from amelia.server.models.state import ServerExecutionState, WorkflowStatus


# Stream-only event types that should NOT be persisted
STREAM_ONLY_TYPES = frozenset({
    EventType.STREAM,
    EventType.CLAUDE_THINKING,
    EventType.CLAUDE_TOOL_CALL,
    EventType.CLAUDE_TOOL_RESULT,
    EventType.AGENT_OUTPUT,
    EventType.AGENT_MESSAGE,  # Not in PERSISTED_TYPES
    EventType.ORACLE_CONSULTATION_THINKING,
    EventType.ORACLE_TOOL_CALL,
    EventType.ORACLE_TOOL_RESULT,
    # Brainstorm streaming events (not persisted)
    EventType.BRAINSTORM_REASONING,
    EventType.BRAINSTORM_TOOL_CALL,
    EventType.BRAINSTORM_TOOL_RESULT,
    EventType.BRAINSTORM_TEXT,
    EventType.BRAINSTORM_MESSAGE_COMPLETE,
})


class TestEventFiltering:
    """Tests for save_event filtering based on PERSISTED_TYPES."""

    @pytest.fixture
    async def db(self, temp_db_path) -> AsyncGenerator[Database, None]:
        """Database with schema initialized."""
        async with Database(temp_db_path) as db:
            await db.ensure_schema()
            yield db

    @pytest.fixture
    async def repository(self, db) -> WorkflowRepository:
        """WorkflowRepository instance."""
        return WorkflowRepository(db)

    @pytest.fixture
    async def sample_workflow(self, repository) -> ServerExecutionState:
        """Create a sample workflow for tests."""
        state = ServerExecutionState(
            id=f"wf-{uuid4().hex[:8]}",
            issue_id="ISSUE-FILTER-TEST",
            worktree_path="/path/to/filter-test",
            workflow_status=WorkflowStatus.IN_PROGRESS,
            started_at=datetime.now(UTC),
        )
        await repository.create(state)
        return state

    @pytest.mark.parametrize("stream_type", list(STREAM_ONLY_TYPES))
    async def test_save_event_filters_stream_only_types(
        self, repository, sample_workflow, stream_type: EventType
    ) -> None:
        """Stream-only event types should not be persisted to workflow_log.

        These include thinking, tool calls, and other ephemeral streaming events
        that would create excessive storage overhead.
        """
        event = WorkflowEvent(
            id=f"evt-stream-{stream_type.value}",
            workflow_id=sample_workflow.id,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=stream_type,
            message=f"Stream event: {stream_type.value}",
        )

        await repository.save_event(event)

        # Verify event was NOT persisted
        row = await repository._db.fetch_one(
            "SELECT id FROM workflow_log WHERE id = ?",
            (event.id,),
        )
        assert row is None, f"Stream-only event type {stream_type.value} should not be persisted"

    @pytest.mark.parametrize("persisted_type", [
        EventType.WORKFLOW_STARTED,
        EventType.WORKFLOW_COMPLETED,
        EventType.STAGE_STARTED,
        EventType.STAGE_COMPLETED,
        EventType.TASK_STARTED,
        EventType.TASK_COMPLETED,
        EventType.SYSTEM_ERROR,
        EventType.FILE_CREATED,
    ])
    async def test_save_event_persists_high_level_types(
        self, repository, sample_workflow, persisted_type: EventType
    ) -> None:
        """High-level event types in PERSISTED_TYPES should be persisted."""
        event = WorkflowEvent(
            id=f"evt-persist-{persisted_type.value}",
            workflow_id=sample_workflow.id,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=persisted_type,
            message=f"Persisted event: {persisted_type.value}",
        )

        await repository.save_event(event)

        # Verify event WAS persisted
        row = await repository._db.fetch_one(
            "SELECT id, event_type FROM workflow_log WHERE id = ?",
            (event.id,),
        )
        assert row is not None, f"Event type {persisted_type.value} should be persisted"
        assert row["event_type"] == persisted_type.value

    async def test_stream_only_types_not_in_persisted_types(self) -> None:
        """Verify our test set of stream-only types is disjoint from PERSISTED_TYPES."""
        overlap = STREAM_ONLY_TYPES & PERSISTED_TYPES
        assert not overlap, f"Types in both sets: {overlap}"

    async def test_persisted_types_coverage(self) -> None:
        """Verify PERSISTED_TYPES includes expected high-level events."""
        # Core lifecycle events must be persisted
        lifecycle_events = {
            EventType.WORKFLOW_CREATED,
            EventType.WORKFLOW_STARTED,
            EventType.WORKFLOW_COMPLETED,
            EventType.WORKFLOW_FAILED,
            EventType.WORKFLOW_CANCELLED,
        }
        assert lifecycle_events.issubset(PERSISTED_TYPES), "Lifecycle events must be persisted"

        # Stage events must be persisted
        stage_events = {EventType.STAGE_STARTED, EventType.STAGE_COMPLETED}
        assert stage_events.issubset(PERSISTED_TYPES), "Stage events must be persisted"


class TestWorkflowLogSchemaConstraints:
    """Tests for workflow_log table CHECK constraints."""

    @pytest.fixture
    async def db(self, temp_db_path) -> AsyncGenerator[Database, None]:
        """Database with schema initialized."""
        async with Database(temp_db_path) as db:
            await db.ensure_schema()
            yield db

    @pytest.fixture
    async def repository(self, db) -> WorkflowRepository:
        """WorkflowRepository instance."""
        return WorkflowRepository(db)

    @pytest.fixture
    async def sample_workflow(self, repository) -> ServerExecutionState:
        """Create a sample workflow for tests."""
        state = ServerExecutionState(
            id=f"wf-{uuid4().hex[:8]}",
            issue_id="ISSUE-CONSTRAINT-TEST",
            worktree_path="/path/to/constraint-test",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)
        return state

    @pytest.mark.parametrize("valid_level", ["info", "warning", "error"])
    async def test_level_check_accepts_valid_values(
        self, db, sample_workflow, valid_level: str
    ) -> None:
        """CHECK constraint should accept info, warning, error levels."""
        event_id = f"evt-level-{valid_level}"

        # Direct insert to test CHECK constraint
        await db.execute(
            """
            INSERT INTO workflow_log (
                id, workflow_id, sequence, timestamp, event_type,
                level, agent, message, is_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                sample_workflow.id,
                1,
                datetime.now(UTC).isoformat(),
                "workflow_started",
                valid_level,
                "system",
                f"Test with level {valid_level}",
                0,
            ),
        )

        # Verify insert succeeded
        row = await db.fetch_one(
            "SELECT level FROM workflow_log WHERE id = ?",
            (event_id,),
        )
        assert row is not None
        assert row["level"] == valid_level

    async def test_level_check_rejects_invalid_value(
        self, db, sample_workflow
    ) -> None:
        """CHECK constraint should reject invalid level values like 'debug'."""
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                """
                INSERT INTO workflow_log (
                    id, workflow_id, sequence, timestamp, event_type,
                    level, agent, message, is_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "evt-invalid-level",
                    sample_workflow.id,
                    1,
                    datetime.now(UTC).isoformat(),
                    "workflow_started",
                    "debug",  # Invalid - not in CHECK constraint
                    "system",
                    "Test with invalid level",
                    0,
                ),
            )

    async def test_level_check_rejects_trace_level(
        self, db, sample_workflow
    ) -> None:
        """CHECK constraint should reject 'trace' level."""
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                """
                INSERT INTO workflow_log (
                    id, workflow_id, sequence, timestamp, event_type,
                    level, agent, message, is_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "evt-trace-level",
                    sample_workflow.id,
                    1,
                    datetime.now(UTC).isoformat(),
                    "workflow_started",
                    "trace",  # Invalid - not in CHECK constraint
                    "system",
                    "Test with trace level",
                    0,
                ),
            )


class TestEventLevelMapping:
    """Tests for EventLevel to workflow_log level mapping."""

    @pytest.fixture
    async def db(self, temp_db_path) -> AsyncGenerator[Database, None]:
        """Database with schema initialized."""
        async with Database(temp_db_path) as db:
            await db.ensure_schema()
            yield db

    @pytest.fixture
    async def repository(self, db) -> WorkflowRepository:
        """WorkflowRepository instance."""
        return WorkflowRepository(db)

    @pytest.fixture
    async def sample_workflow(self, repository) -> ServerExecutionState:
        """Create a sample workflow for tests."""
        state = ServerExecutionState(
            id=f"wf-{uuid4().hex[:8]}",
            issue_id="ISSUE-LEVEL-MAP",
            worktree_path="/path/to/level-map",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)
        return state

    async def test_info_level_preserved(
        self, repository, sample_workflow
    ) -> None:
        """EventLevel.INFO should be stored as 'info' in workflow_log."""
        event = WorkflowEvent(
            id="evt-info-level",
            workflow_id=sample_workflow.id,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            level=EventLevel.INFO,
            message="Info level event",
        )

        await repository.save_event(event)

        row = await repository._db.fetch_one(
            "SELECT level FROM workflow_log WHERE id = ?",
            (event.id,),
        )
        assert row["level"] == "info"

    async def test_debug_level_mapped_to_info(
        self, repository, sample_workflow
    ) -> None:
        """EventLevel.DEBUG should be mapped to 'info' for workflow_log storage.

        workflow_log only supports info/warning/error levels, so debug must be
        mapped to prevent CHECK constraint violations.
        """
        event = WorkflowEvent(
            id="evt-debug-mapped",
            workflow_id=sample_workflow.id,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.TASK_STARTED,
            level=EventLevel.DEBUG,
            message="Debug level event",
        )

        await repository.save_event(event)

        row = await repository._db.fetch_one(
            "SELECT level FROM workflow_log WHERE id = ?",
            (event.id,),
        )
        assert row["level"] == "info", "DEBUG should be mapped to 'info'"

    async def test_trace_level_mapped_to_info(
        self, repository, sample_workflow
    ) -> None:
        """EventLevel.TRACE should be mapped to 'info' for workflow_log storage."""
        event = WorkflowEvent(
            id="evt-trace-mapped",
            workflow_id=sample_workflow.id,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.TASK_COMPLETED,
            level=EventLevel.TRACE,
            message="Trace level event",
        )

        await repository.save_event(event)

        row = await repository._db.fetch_one(
            "SELECT level FROM workflow_log WHERE id = ?",
            (event.id,),
        )
        assert row["level"] == "info", "TRACE should be mapped to 'info'"

    async def test_none_level_defaults_to_info(
        self, repository, sample_workflow
    ) -> None:
        """Events with level=None should default to 'info' in workflow_log."""
        event = WorkflowEvent(
            id="evt-none-level",
            workflow_id=sample_workflow.id,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.STAGE_COMPLETED,
            level=None,  # Explicitly None
            message="Event without level",
        )

        await repository.save_event(event)

        row = await repository._db.fetch_one(
            "SELECT level FROM workflow_log WHERE id = ?",
            (event.id,),
        )
        assert row["level"] == "info", "None level should default to 'info'"
