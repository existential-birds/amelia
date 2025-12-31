"""Tests for streaming types."""

from datetime import UTC, datetime
from typing import Any

import pytest

from amelia.core.types import StreamEvent, StreamEventType


class TestStreamEvent:
    """Test StreamEvent Pydantic model."""

    @pytest.mark.parametrize(
        "event_type,extra_fields",
        [
            (StreamEventType.CLAUDE_THINKING, {}),
            (StreamEventType.CLAUDE_TOOL_CALL, {"tool_name": "read_file", "tool_input": {"path": "/tmp/test.py"}}),
            (StreamEventType.CLAUDE_TOOL_RESULT, {"tool_name": "read_file", "content": "File contents: ..."}),
            (StreamEventType.AGENT_OUTPUT, {"content": "Plan generated successfully"}),
        ],
    )
    def test_stream_event_instantiation(self, event_type: StreamEventType, extra_fields: dict[str, Any]) -> None:
        """StreamEvent should validate with various field combinations."""
        now = datetime.now(UTC)
        event = StreamEvent(
            type=event_type,
            timestamp=now,
            agent="developer",
            workflow_id="workflow-123",
            **extra_fields,
        )
        assert event.type == event_type
        assert event.timestamp == now
        assert event.agent == "developer"
        assert event.workflow_id == "workflow-123"
        for key, value in extra_fields.items():
            assert getattr(event, key) == value

    def test_id_auto_generated(self) -> None:
        """StreamEvent should auto-generate a unique UUID id."""
        now = datetime.now(UTC)
        event1 = StreamEvent(
            type=StreamEventType.CLAUDE_THINKING,
            timestamp=now,
            agent="architect",
            workflow_id="workflow-123",
        )
        event2 = StreamEvent(
            type=StreamEventType.CLAUDE_THINKING,
            timestamp=now,
            agent="architect",
            workflow_id="workflow-123",
        )
        # Each event has an id
        assert event1.id is not None
        assert event2.id is not None
        # IDs are unique
        assert event1.id != event2.id
        # ID is a valid UUID string (36 chars with hyphens)
        assert len(event1.id) == 36
