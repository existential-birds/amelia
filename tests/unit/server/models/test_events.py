"""Tests for event models."""

from datetime import datetime
from typing import Any

from amelia.server.models.events import EventType, WorkflowEvent


def make_event(**overrides: Any) -> WorkflowEvent:
    """Create a WorkflowEvent with sensible defaults."""
    defaults: dict[str, Any] = {
        "id": "event-123",
        "workflow_id": "wf-456",
        "sequence": 1,
        "timestamp": datetime(2025, 1, 1, 12, 0, 0),
        "agent": "system",
        "event_type": EventType.WORKFLOW_STARTED,
        "message": "Test event",
    }
    return WorkflowEvent(**{**defaults, **overrides})


class TestWorkflowEvent:
    """Tests for WorkflowEvent model."""

    def test_create_event_with_all_fields(self) -> None:
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

    def test_event_json_round_trip(self) -> None:
        """Event survives JSON serialization round-trip."""
        original = make_event(
            data={"key": "value"},
            correlation_id="corr-123",
        )

        json_str = original.model_dump_json()
        restored = WorkflowEvent.model_validate_json(json_str)

        assert restored.id == original.id
        assert restored.workflow_id == original.workflow_id
        assert restored.event_type == original.event_type
        assert restored.data == original.data
        assert restored.correlation_id == original.correlation_id
