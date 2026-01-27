"""Tests for event models."""

from datetime import UTC, datetime

import pytest

from amelia.server.models.events import (
    EventLevel,
    EventType,
    WorkflowEvent,
    get_event_level,
)


class TestEventLevel:
    """Tests for EventLevel enum and classification."""

    def test_event_level_values(self) -> None:
        """EventLevel has info, debug, trace values."""
        assert EventLevel.INFO == "info"
        assert EventLevel.DEBUG == "debug"
        assert EventLevel.TRACE == "trace"

    @pytest.mark.parametrize(
        "event_type,expected_level",
        [
            # INFO level - workflow lifecycle
            (EventType.WORKFLOW_STARTED, EventLevel.INFO),
            (EventType.WORKFLOW_COMPLETED, EventLevel.INFO),
            (EventType.WORKFLOW_FAILED, EventLevel.INFO),
            (EventType.WORKFLOW_CANCELLED, EventLevel.INFO),
            # INFO level - stages
            (EventType.STAGE_STARTED, EventLevel.INFO),
            (EventType.STAGE_COMPLETED, EventLevel.INFO),
            # INFO level - approvals
            (EventType.APPROVAL_REQUIRED, EventLevel.INFO),
            (EventType.APPROVAL_GRANTED, EventLevel.INFO),
            (EventType.APPROVAL_REJECTED, EventLevel.INFO),
            # INFO level - review completion
            (EventType.REVIEW_COMPLETED, EventLevel.INFO),
            # DEBUG level - tasks
            (EventType.TASK_STARTED, EventLevel.DEBUG),
            (EventType.TASK_COMPLETED, EventLevel.DEBUG),
            (EventType.TASK_FAILED, EventLevel.DEBUG),
            # DEBUG level - files
            (EventType.FILE_CREATED, EventLevel.DEBUG),
            (EventType.FILE_MODIFIED, EventLevel.DEBUG),
            (EventType.FILE_DELETED, EventLevel.DEBUG),
            # DEBUG level - other
            (EventType.AGENT_MESSAGE, EventLevel.DEBUG),
            (EventType.REVISION_REQUESTED, EventLevel.DEBUG),
            (EventType.REVIEW_REQUESTED, EventLevel.DEBUG),
            (EventType.SYSTEM_ERROR, EventLevel.DEBUG),
            (EventType.SYSTEM_WARNING, EventLevel.DEBUG),
            # TRACE level - stream events
            (EventType.CLAUDE_THINKING, EventLevel.TRACE),
            (EventType.CLAUDE_TOOL_CALL, EventLevel.TRACE),
            (EventType.CLAUDE_TOOL_RESULT, EventLevel.TRACE),
            (EventType.AGENT_OUTPUT, EventLevel.TRACE),
        ],
    )
    def test_get_event_level(self, event_type: EventType, expected_level: EventLevel) -> None:
        """get_event_level returns correct level for each event type."""
        assert get_event_level(event_type) == expected_level


class TestWorkflowEvent:
    """Tests for WorkflowEvent model."""

    def test_create_event_with_all_fields(self, make_event) -> None:
        """Event can be created with all fields including optional ones."""
        event = make_event(
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
            level=EventLevel.TRACE,
            message="Tool call: Edit",
            tool_name="Edit",
            tool_input={"file": "test.py"},
            is_error=False,
        )
        assert event.level == EventLevel.TRACE
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

        # TRACE event
        trace_event = WorkflowEvent(
            id="evt-3",
            workflow_id="wf-1",
            sequence=3,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.CLAUDE_THINKING,
            message="Thinking...",
        )
        assert trace_event.level == EventLevel.TRACE
