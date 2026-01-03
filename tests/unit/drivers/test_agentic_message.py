"""Tests for AgenticMessage.to_stream_event() conversion logic."""

from amelia.core.types import StreamEventType
from amelia.drivers.base import AgenticMessage, AgenticMessageType


class TestAgenticMessageToStreamEvent:
    """Test AgenticMessage.to_stream_event() conversion."""

    def test_thinking_converts_to_claude_thinking(self) -> None:
        msg = AgenticMessage(
            type=AgenticMessageType.THINKING,
            content="Analyzing the problem...",
        )
        event = msg.to_stream_event(agent="developer", workflow_id="wf_123")

        assert event.type == StreamEventType.CLAUDE_THINKING
        assert event.content == "Analyzing the problem..."
        assert event.agent == "developer"
        assert event.workflow_id == "wf_123"
        assert event.is_error is False

    def test_tool_call_converts_to_claude_tool_call(self) -> None:
        msg = AgenticMessage(
            type=AgenticMessageType.TOOL_CALL,
            tool_name="read_file",
            tool_input={"path": "/test.py"},
        )
        event = msg.to_stream_event(agent="developer", workflow_id="wf_123")

        assert event.type == StreamEventType.CLAUDE_TOOL_CALL
        assert event.tool_name == "read_file"
        assert event.tool_input == {"path": "/test.py"}

    def test_tool_result_converts_to_claude_tool_result(self) -> None:
        msg = AgenticMessage(
            type=AgenticMessageType.TOOL_RESULT,
            tool_name="read_file",
            tool_output="file contents",
            is_error=False,
        )
        event = msg.to_stream_event(agent="developer", workflow_id="wf_123")

        assert event.type == StreamEventType.CLAUDE_TOOL_RESULT
        assert event.content == "file contents"
        assert event.is_error is False

    def test_error_result_preserves_is_error(self) -> None:
        msg = AgenticMessage(
            type=AgenticMessageType.TOOL_RESULT,
            tool_name="bash",
            tool_output="Command failed",
            is_error=True,
        )
        event = msg.to_stream_event(agent="developer", workflow_id="wf_123")

        assert event.type == StreamEventType.CLAUDE_TOOL_RESULT
        assert event.is_error is True

    def test_result_converts_to_agent_output(self) -> None:
        msg = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="Task completed",
            session_id="sess_abc",
        )
        event = msg.to_stream_event(agent="developer", workflow_id="wf_123")

        assert event.type == StreamEventType.AGENT_OUTPUT
        assert event.content == "Task completed"
        # Note: session_id is not included in StreamEvent by design - it's only
        # used for driver session tracking, not for UI streaming
