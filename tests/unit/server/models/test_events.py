"""Tests for event models."""

from datetime import UTC, datetime

import pytest

from amelia.server.models.events import (
    PERSISTED_TYPES,
    EventLevel,
    EventType,
    WorkflowEvent,
    get_event_level,
)


class TestEventLevel:
    """Tests for EventLevel enum and classification."""

    def test_event_level_values(self) -> None:
        """EventLevel has info, warning, debug, error values."""
        assert EventLevel.INFO == "info"
        assert EventLevel.WARNING == "warning"
        assert EventLevel.DEBUG == "debug"
        assert EventLevel.ERROR == "error"

    @pytest.mark.parametrize(
        "event_type,expected_level",
        [
            # ERROR level - failures
            (EventType.WORKFLOW_FAILED, EventLevel.ERROR),
            (EventType.TASK_FAILED, EventLevel.ERROR),
            (EventType.SYSTEM_ERROR, EventLevel.ERROR),
            (EventType.ORACLE_CONSULTATION_FAILED, EventLevel.ERROR),
            # WARNING level
            (EventType.SYSTEM_WARNING, EventLevel.WARNING),
            # INFO level - workflow lifecycle
            (EventType.WORKFLOW_CREATED, EventLevel.INFO),
            (EventType.WORKFLOW_STARTED, EventLevel.INFO),
            (EventType.WORKFLOW_COMPLETED, EventLevel.INFO),
            (EventType.WORKFLOW_CANCELLED, EventLevel.INFO),
            # INFO level - stages
            (EventType.STAGE_STARTED, EventLevel.INFO),
            (EventType.STAGE_COMPLETED, EventLevel.INFO),
            # INFO level - approvals
            (EventType.APPROVAL_REQUIRED, EventLevel.INFO),
            (EventType.APPROVAL_GRANTED, EventLevel.INFO),
            (EventType.APPROVAL_REJECTED, EventLevel.INFO),
            # INFO level - review/oracle
            (EventType.REVIEW_COMPLETED, EventLevel.INFO),
            (EventType.ORACLE_CONSULTATION_STARTED, EventLevel.INFO),
            (EventType.ORACLE_CONSULTATION_COMPLETED, EventLevel.INFO),
            # DEBUG level - tasks
            (EventType.TASK_STARTED, EventLevel.DEBUG),
            (EventType.TASK_COMPLETED, EventLevel.DEBUG),
            # DEBUG level - files
            (EventType.FILE_CREATED, EventLevel.DEBUG),
            (EventType.FILE_MODIFIED, EventLevel.DEBUG),
            (EventType.FILE_DELETED, EventLevel.DEBUG),
            # DEBUG level - other
            (EventType.AGENT_MESSAGE, EventLevel.DEBUG),
            (EventType.REVISION_REQUESTED, EventLevel.DEBUG),
            (EventType.REVIEW_REQUESTED, EventLevel.DEBUG),
            # DEBUG level - stream/trace events
            (EventType.CLAUDE_THINKING, EventLevel.DEBUG),
            (EventType.CLAUDE_TOOL_CALL, EventLevel.DEBUG),
            (EventType.CLAUDE_TOOL_RESULT, EventLevel.DEBUG),
            (EventType.AGENT_OUTPUT, EventLevel.DEBUG),
            # DEBUG level - brainstorm trace events
            (EventType.BRAINSTORM_REASONING, EventLevel.DEBUG),
            (EventType.BRAINSTORM_TOOL_CALL, EventLevel.DEBUG),
            (EventType.BRAINSTORM_TOOL_RESULT, EventLevel.DEBUG),
            (EventType.BRAINSTORM_TEXT, EventLevel.DEBUG),
            (EventType.BRAINSTORM_MESSAGE_COMPLETE, EventLevel.DEBUG),
            # DEBUG level - oracle trace events
            (EventType.ORACLE_CONSULTATION_THINKING, EventLevel.DEBUG),
            (EventType.ORACLE_TOOL_CALL, EventLevel.DEBUG),
            (EventType.ORACLE_TOOL_RESULT, EventLevel.DEBUG),
        ],
    )
    def test_get_event_level(self, event_type: EventType, expected_level: EventLevel) -> None:
        """get_event_level returns correct level for each event type."""
        assert get_event_level(event_type) == expected_level


class TestWorkflowEvent:
    """Tests for WorkflowEvent model."""

    def test_create_event_with_all_fields(self, event_factory) -> None:
        """Event can be created with all fields including optional ones."""
        event = event_factory(
            agent="developer",
            event_type=EventType.FILE_CREATED,
            message="Created file",
            data={"path": "src/main.py", "lines": 100},
            correlation_id="req-789",
        )

        assert event.id == "event-123"
        assert event.workflow_id == "wf-456"
        assert event.sequence == 1
        assert event.agent == "developer"
        assert event.event_type == EventType.FILE_CREATED
        assert event.data == {"path": "src/main.py", "lines": 100}
        assert event.correlation_id == "req-789"

    def test_workflow_event_has_level_field(self) -> None:
        """WorkflowEvent includes level field with default."""
        event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="architect",
            event_type=EventType.STAGE_STARTED,
            message="Test",
        )
        assert event.level == EventLevel.INFO

    def test_workflow_event_trace_fields(self) -> None:
        """WorkflowEvent includes trace-specific fields."""
        event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.CLAUDE_TOOL_CALL,
            level=EventLevel.DEBUG,
            message="Tool call: Edit",
            tool_name="Edit",
            tool_input={"file": "test.py"},
            is_error=False,
        )
        assert event.level == EventLevel.DEBUG
        assert event.tool_name == "Edit"
        assert event.tool_input == {"file": "test.py"}
        assert event.is_error is False

    def test_workflow_event_session_id_field(self) -> None:
        """WorkflowEvent includes optional session_id independent from workflow_id."""
        event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="oracle",
            event_type=EventType.STAGE_STARTED,
            message="Consultation started",
            session_id="sess-abc-123",
        )
        assert event.session_id == "sess-abc-123"
        assert event.workflow_id == "wf-1"

    def test_workflow_event_session_id_defaults_to_none(self) -> None:
        """WorkflowEvent session_id defaults to None when not provided."""
        event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )
        assert event.session_id is None

    def test_workflow_event_distributed_tracing_fields(self) -> None:
        """WorkflowEvent includes trace_id and parent_id for distributed tracing."""
        event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.CLAUDE_TOOL_RESULT,
            message="Tool result",
            trace_id="trace-abc-123",
            parent_id="evt-parent",
        )
        assert event.trace_id == "trace-abc-123"
        assert event.parent_id == "evt-parent"

    def test_workflow_event_level_defaults_from_event_type(self) -> None:
        """Level defaults based on event_type when not provided."""
        # INFO event
        info_event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )
        assert info_event.level == EventLevel.INFO

        # DEBUG event
        debug_event = WorkflowEvent(
            id="evt-2",
            workflow_id="wf-1",
            sequence=2,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.FILE_MODIFIED,
            message="Modified file",
        )
        assert debug_event.level == EventLevel.DEBUG

        # ERROR event
        error_event = WorkflowEvent(
            id="evt-3",
            workflow_id="wf-1",
            sequence=3,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.WORKFLOW_FAILED,
            message="Failed",
        )
        assert error_event.level == EventLevel.ERROR


class TestPersistedTypes:
    """Tests for PERSISTED_TYPES classification."""

    def test_persisted_types_is_frozenset(self):
        """PERSISTED_TYPES must be immutable."""
        assert isinstance(PERSISTED_TYPES, frozenset)

    def test_lifecycle_events_are_persisted(self):
        """All lifecycle events must be persisted."""
        lifecycle = {
            EventType.WORKFLOW_CREATED,
            EventType.WORKFLOW_STARTED,
            EventType.WORKFLOW_COMPLETED,
            EventType.WORKFLOW_FAILED,
            EventType.WORKFLOW_CANCELLED,
        }
        assert lifecycle <= PERSISTED_TYPES

    def test_trace_events_are_not_persisted(self):
        """Trace events must NOT be persisted."""
        trace_types = {
            EventType.CLAUDE_THINKING,
            EventType.CLAUDE_TOOL_CALL,
            EventType.CLAUDE_TOOL_RESULT,
            EventType.AGENT_OUTPUT,
            EventType.ORACLE_CONSULTATION_THINKING,
            EventType.ORACLE_TOOL_CALL,
            EventType.ORACLE_TOOL_RESULT,
        }
        assert trace_types.isdisjoint(PERSISTED_TYPES)

    def test_stream_events_are_not_persisted(self):
        """Stream and agent_message events must NOT be persisted."""
        stream_types = {EventType.STREAM, EventType.AGENT_MESSAGE}
        assert stream_types.isdisjoint(PERSISTED_TYPES)

    def test_brainstorm_trace_events_are_not_persisted(self):
        """Brainstorm trace events must NOT be persisted."""
        brainstorm_trace = {
            EventType.BRAINSTORM_REASONING,
            EventType.BRAINSTORM_TOOL_CALL,
            EventType.BRAINSTORM_TOOL_RESULT,
            EventType.BRAINSTORM_TEXT,
            EventType.BRAINSTORM_MESSAGE_COMPLETE,
        }
        assert brainstorm_trace.isdisjoint(PERSISTED_TYPES)

    def test_every_event_type_is_classified(self):
        """Every EventType must be either persisted or explicitly stream-only.

        Guards against new event types being added without classification.
        """
        all_types = set(EventType)
        stream_only = {
            EventType.CLAUDE_THINKING,
            EventType.CLAUDE_TOOL_CALL,
            EventType.CLAUDE_TOOL_RESULT,
            EventType.AGENT_OUTPUT,
            EventType.ORACLE_CONSULTATION_THINKING,
            EventType.ORACLE_TOOL_CALL,
            EventType.ORACLE_TOOL_RESULT,
            EventType.BRAINSTORM_REASONING,
            EventType.BRAINSTORM_TOOL_CALL,
            EventType.BRAINSTORM_TOOL_RESULT,
            EventType.BRAINSTORM_TEXT,
            EventType.BRAINSTORM_MESSAGE_COMPLETE,
            EventType.STREAM,
            EventType.AGENT_MESSAGE,
            EventType.DOCUMENT_INGESTION_PROGRESS,
        }
        classified = PERSISTED_TYPES | stream_only
        unclassified = all_types - classified
        assert not unclassified, f"Unclassified event types: {unclassified}"
