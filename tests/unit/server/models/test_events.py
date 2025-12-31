"""Tests for event models."""

from amelia.server.models.events import EventType


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
