"""Tests for EventBus -> console log subscriber."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

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
    def test_logs_info_event_at_info_level(self, mock_logger: MagicMock) -> None:
        event = _make_event(EventType.STAGE_STARTED, "Starting architect")
        log_event_to_console(event)
        mock_logger.log.assert_called_once()
        assert mock_logger.log.call_args[0][0] == "INFO"

    @patch("amelia.server.events.log_subscriber.logger")
    def test_logs_error_event_at_error_level(self, mock_logger: MagicMock) -> None:
        event = _make_event(EventType.WORKFLOW_FAILED, "Workflow failed: timeout")
        log_event_to_console(event)
        assert mock_logger.log.call_args[0][0] == "ERROR"

    @patch("amelia.server.events.log_subscriber.logger")
    def test_logs_warning_event_at_warning_level(self, mock_logger: MagicMock) -> None:
        event = _make_event(EventType.SYSTEM_WARNING, "Rate limit approaching")
        log_event_to_console(event)
        assert mock_logger.log.call_args[0][0] == "WARNING"

    @patch("amelia.server.events.log_subscriber.logger")
    def test_includes_structured_fields(self, mock_logger: MagicMock) -> None:
        event = _make_event(EventType.STAGE_COMPLETED, "Completed architect")
        log_event_to_console(event)
        call_kwargs = mock_logger.log.call_args[1]
        assert "workflow_id" in call_kwargs
        assert "event_type" in call_kwargs
        assert call_kwargs["event_type"] == "stage_completed"

    @patch("amelia.server.events.log_subscriber.logger")
    def test_defaults_agent_to_system(self, mock_logger: MagicMock) -> None:
        event = _make_event(EventType.WORKFLOW_STARTED, "Started", agent="")
        log_event_to_console(event)
        call_kwargs = mock_logger.log.call_args[1]
        assert call_kwargs["agent"] == "system"

    @patch("amelia.server.events.log_subscriber.logger")
    def test_defaults_level_to_info_when_none(self, mock_logger: MagicMock) -> None:
        # Use model_construct to bypass model_post_init which auto-sets level
        event = WorkflowEvent.model_construct(
            id=uuid.uuid4(),
            workflow_id=uuid.uuid4(),
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="architect",
            event_type=EventType.STAGE_STARTED,
            message="test",
            level=None,
        )
        log_event_to_console(event)
        assert mock_logger.log.call_args[0][0] == "INFO"


class TestConsoleEventFiltering:
    """Tests for console-event-type filtering."""

    @patch("amelia.server.events.log_subscriber.logger")
    def test_skips_claude_tool_call(self, mock_logger: MagicMock) -> None:
        event = _make_event(EventType.CLAUDE_TOOL_CALL, "Calling EditFile")
        log_event_to_console(event)
        mock_logger.log.assert_not_called()

    @patch("amelia.server.events.log_subscriber.logger")
    def test_skips_claude_thinking(self, mock_logger: MagicMock) -> None:
        event = _make_event(EventType.CLAUDE_THINKING, "Thinking...")
        log_event_to_console(event)
        mock_logger.log.assert_not_called()

    @patch("amelia.server.events.log_subscriber.logger")
    def test_skips_stream_events(self, mock_logger: MagicMock) -> None:
        event = _make_event(EventType.STREAM, "streaming chunk")
        log_event_to_console(event)
        mock_logger.log.assert_not_called()

    @patch("amelia.server.events.log_subscriber.logger")
    def test_allows_agent_message(self, mock_logger: MagicMock) -> None:
        event = _make_event(EventType.AGENT_MESSAGE, "Planning architecture")
        log_event_to_console(event)
        mock_logger.log.assert_called_once()

    @patch("amelia.server.events.log_subscriber.logger")
    def test_allows_workflow_lifecycle(self, mock_logger: MagicMock) -> None:
        event = _make_event(EventType.WORKFLOW_COMPLETED, "Done")
        log_event_to_console(event)
        mock_logger.log.assert_called_once()


class TestAgentMessageLevelPromotion:
    """Tests for AGENT_MESSAGE DEBUG -> INFO promotion."""

    @patch("amelia.server.events.log_subscriber.logger")
    def test_promotes_debug_agent_message_to_info(self, mock_logger: MagicMock) -> None:
        event = _make_event(
            EventType.AGENT_MESSAGE, "Planning", level=EventLevel.DEBUG
        )
        log_event_to_console(event)
        assert mock_logger.log.call_args[0][0] == "INFO"

    @patch("amelia.server.events.log_subscriber.logger")
    def test_preserves_info_agent_message(self, mock_logger: MagicMock) -> None:
        event = _make_event(
            EventType.AGENT_MESSAGE, "Planning", level=EventLevel.INFO
        )
        log_event_to_console(event)
        assert mock_logger.log.call_args[0][0] == "INFO"

    @patch("amelia.server.events.log_subscriber.logger")
    def test_preserves_warning_agent_message(self, mock_logger: MagicMock) -> None:
        event = _make_event(
            EventType.AGENT_MESSAGE, "Retrying", level=EventLevel.WARNING
        )
        log_event_to_console(event)
        assert mock_logger.log.call_args[0][0] == "WARNING"
