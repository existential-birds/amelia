"""Tests for event models."""

from collections.abc import Callable
from uuid import uuid4

import pytest

from amelia.server.models.events import (
    TRACE_TYPES,
    BrainstormEventType,
    EventLevel,
    EventType,
    WorkflowEvent,
    get_event_level,
)


class TestEventLevel:
    """Tests for EventLevel enum and classification."""

    @pytest.mark.parametrize(
        "member,expected_value",
        [
            (EventLevel.INFO, "info"),
            (EventLevel.WARNING, "warning"),
            (EventLevel.DEBUG, "debug"),
            (EventLevel.ERROR, "error"),
        ],
    )
    def test_event_level_values(self, member: EventLevel, expected_value: str) -> None:
        """EventLevel members have correct string values."""
        assert member.value == expected_value

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
            (BrainstormEventType.REASONING, EventLevel.DEBUG),
            (BrainstormEventType.TOOL_CALL, EventLevel.DEBUG),
            (BrainstormEventType.TOOL_RESULT, EventLevel.DEBUG),
            (BrainstormEventType.TEXT, EventLevel.DEBUG),
            (BrainstormEventType.MESSAGE_COMPLETE, EventLevel.DEBUG),
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

    def test_create_event_with_all_fields(self, event_factory: Callable[..., WorkflowEvent]) -> None:
        """Event can be created with all fields including optional ones."""
        event = event_factory(
            agent="developer",
            event_type=EventType.FILE_CREATED,
            message="Created file",
            data={"path": "src/main.py", "lines": 100},
            correlation_id=uuid4(),
        )

        assert event.id is not None
        assert event.workflow_id is not None
        assert event.sequence == 1
        assert event.agent == "developer"
        assert event.event_type == EventType.FILE_CREATED
        assert event.data == {"path": "src/main.py", "lines": 100}
        assert event.correlation_id is not None

    def test_workflow_event_has_level_field(self, event_factory: Callable[..., WorkflowEvent]) -> None:
        """WorkflowEvent includes level field with default."""
        event = event_factory(agent="architect", event_type=EventType.STAGE_STARTED)
        assert event.level == EventLevel.INFO

    def test_workflow_event_trace_fields(self, event_factory: Callable[..., WorkflowEvent]) -> None:
        """WorkflowEvent includes trace-specific fields."""
        event = event_factory(
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

    def test_workflow_event_session_id_field(self, event_factory: Callable[..., WorkflowEvent]) -> None:
        """WorkflowEvent includes optional session_id independent from workflow_id."""
        event = event_factory(
            agent="oracle",
            event_type=EventType.STAGE_STARTED,
            message="Consultation started",
            session_id=uuid4(),
        )
        assert event.session_id is not None
        assert event.workflow_id is not None

    def test_workflow_event_session_id_defaults_to_none(
        self, event_factory: Callable[..., WorkflowEvent]
    ) -> None:
        """WorkflowEvent session_id defaults to None when not provided."""
        event = event_factory(agent="system", event_type=EventType.WORKFLOW_STARTED)
        assert event.session_id is None

    def test_workflow_event_distributed_tracing_fields(
        self, event_factory: Callable[..., WorkflowEvent]
    ) -> None:
        """WorkflowEvent includes trace_id and parent_id for distributed tracing."""
        event = event_factory(
            agent="developer",
            event_type=EventType.CLAUDE_TOOL_RESULT,
            message="Tool result",
            trace_id=uuid4(),
            parent_id=uuid4(),
        )
        assert event.trace_id is not None
        assert event.parent_id is not None

    @pytest.mark.parametrize(
        "event_type,expected_level",
        [
            (EventType.WORKFLOW_STARTED, EventLevel.INFO),
            (EventType.FILE_MODIFIED, EventLevel.DEBUG),
            (EventType.WORKFLOW_FAILED, EventLevel.ERROR),
        ],
    )
    def test_workflow_event_level_defaults_from_event_type(
        self,
        event_factory: Callable[..., WorkflowEvent],
        event_type: EventType,
        expected_level: EventLevel,
    ) -> None:
        """Level defaults based on event_type when not provided."""
        event = event_factory(event_type=event_type)
        assert event.level == expected_level


class TestTraceTypes:
    """Tests for TRACE_TYPES broadcast classification."""

    def test_trace_types_is_frozenset(self) -> None:
        """TRACE_TYPES must be immutable."""
        assert isinstance(TRACE_TYPES, frozenset)

    def test_lifecycle_events_are_not_trace(self) -> None:
        """Lifecycle events are workflow-scoped, not trace broadcast."""
        lifecycle = {
            EventType.WORKFLOW_CREATED,
            EventType.WORKFLOW_STARTED,
            EventType.WORKFLOW_COMPLETED,
            EventType.WORKFLOW_FAILED,
            EventType.WORKFLOW_CANCELLED,
        }
        assert lifecycle.isdisjoint(TRACE_TYPES)

    def test_agent_stream_events_are_trace(self) -> None:
        """High-volume agent stream events broadcast to all clients."""
        trace_types = {
            EventType.STREAM,
            EventType.AGENT_MESSAGE,
            EventType.CLAUDE_THINKING,
            EventType.CLAUDE_TOOL_CALL,
            EventType.CLAUDE_TOOL_RESULT,
            EventType.AGENT_OUTPUT,
            EventType.ORACLE_CONSULTATION_THINKING,
            EventType.ORACLE_TOOL_CALL,
            EventType.ORACLE_TOOL_RESULT,
            EventType.DOCUMENT_INGESTION_PROGRESS,
        }
        assert trace_types <= TRACE_TYPES

    def test_brainstorm_stream_events_are_trace(self) -> None:
        """Brainstorm streaming events broadcast to all clients."""
        brainstorm_trace = {
            BrainstormEventType.REASONING,
            BrainstormEventType.TOOL_CALL,
            BrainstormEventType.TOOL_RESULT,
            BrainstormEventType.TEXT,
            BrainstormEventType.ASK_USER,
            BrainstormEventType.MESSAGE_COMPLETE,
        }
        assert brainstorm_trace <= TRACE_TYPES

    def test_brainstorm_lifecycle_events_are_not_trace(self) -> None:
        """Brainstorm lifecycle events are session-scoped, not trace."""
        brainstorm_lifecycle = {
            BrainstormEventType.SESSION_CREATED,
            BrainstormEventType.SESSION_COMPLETED,
            BrainstormEventType.ARTIFACT_CREATED,
            BrainstormEventType.MESSAGE_FAILED,
        }
        assert brainstorm_lifecycle.isdisjoint(TRACE_TYPES)
