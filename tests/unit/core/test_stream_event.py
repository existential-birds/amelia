# tests/unit/core/test_stream_event.py
"""Tests for StreamEvent with is_error field."""

from datetime import UTC, datetime

from amelia.core.types import StreamEvent, StreamEventType


class TestStreamEventIsError:
    """Test StreamEvent is_error field."""

    def test_is_error_defaults_to_false(self) -> None:
        event = StreamEvent(
            type=StreamEventType.CLAUDE_TOOL_RESULT,
            content="result",
            timestamp=datetime.now(UTC),
            agent="developer",
            workflow_id="wf_123",
        )
        assert event.is_error is False

    def test_is_error_can_be_true(self) -> None:
        event = StreamEvent(
            type=StreamEventType.CLAUDE_TOOL_RESULT,
            content="Error: file not found",
            timestamp=datetime.now(UTC),
            agent="developer",
            workflow_id="wf_123",
            is_error=True,
        )
        assert event.is_error is True
