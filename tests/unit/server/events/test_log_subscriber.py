"""Tests for EventBus -> console log subscriber."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

from amelia.server.events.log_subscriber import log_event_to_console
from amelia.server.models.events import EventLevel, EventType, WorkflowEvent


def _make_event(
    event_type: EventType,
    message: str = "test message",
    agent: str = "architect",
    level: EventLevel | None = None,
) -> WorkflowEvent:
    return WorkflowEvent(
        id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        sequence=1,
        timestamp=datetime.now(UTC),
        agent=agent,
        event_type=event_type,
        message=message,
        level=level,
    )


class TestLogEventToConsole:
    """Tests for log_event_to_console subscriber."""

    @patch("amelia.server.events.log_subscriber.logger")
    def test_logs_info_event_at_info_level(self, mock_logger: object) -> None:
        event = _make_event(EventType.STAGE_STARTED, "Starting architect")
        log_event_to_console(event)
        mock_logger.log.assert_called_once()  # type: ignore[union-attr]
        assert mock_logger.log.call_args[0][0] == "INFO"  # type: ignore[union-attr]

    @patch("amelia.server.events.log_subscriber.logger")
    def test_logs_error_event_at_error_level(self, mock_logger: object) -> None:
        event = _make_event(EventType.WORKFLOW_FAILED, "Workflow failed: timeout")
        log_event_to_console(event)
        assert mock_logger.log.call_args[0][0] == "ERROR"  # type: ignore[union-attr]

    @patch("amelia.server.events.log_subscriber.logger")
    def test_logs_debug_event_at_debug_level(self, mock_logger: object) -> None:
        event = _make_event(EventType.CLAUDE_TOOL_CALL, "Calling EditFile")
        log_event_to_console(event)
        assert mock_logger.log.call_args[0][0] == "DEBUG"  # type: ignore[union-attr]

    @patch("amelia.server.events.log_subscriber.logger")
    def test_logs_warning_event_at_warning_level(self, mock_logger: object) -> None:
        event = _make_event(EventType.SYSTEM_WARNING, "Rate limit approaching")
        log_event_to_console(event)
        assert mock_logger.log.call_args[0][0] == "WARNING"  # type: ignore[union-attr]

    @patch("amelia.server.events.log_subscriber.logger")
    def test_includes_structured_fields(self, mock_logger: object) -> None:
        event = _make_event(EventType.STAGE_COMPLETED, "Completed architect")
        log_event_to_console(event)
        call_kwargs = mock_logger.log.call_args[1]  # type: ignore[union-attr]
        assert "workflow_id" in call_kwargs
        assert "event_type" in call_kwargs
        assert call_kwargs["event_type"] == "stage_completed"

    @patch("amelia.server.events.log_subscriber.logger")
    def test_defaults_agent_to_system(self, mock_logger: object) -> None:
        event = _make_event(EventType.WORKFLOW_STARTED, "Started", agent="")
        log_event_to_console(event)
        call_kwargs = mock_logger.log.call_args[1]  # type: ignore[union-attr]
        assert call_kwargs["agent"] == "system"

    @patch("amelia.server.events.log_subscriber.logger")
    def test_defaults_level_to_info_when_none(self, mock_logger: object) -> None:
        event = _make_event(EventType.STAGE_STARTED, "test", level=None)
        # model_post_init sets level from event type, so override after creation
        object.__setattr__(event, "level", None)
        log_event_to_console(event)
        assert mock_logger.log.call_args[0][0] == "INFO"  # type: ignore[union-attr]
