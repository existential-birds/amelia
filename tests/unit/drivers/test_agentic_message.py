"""Tests for AgenticMessage unified driver message type."""

import pytest

from amelia.drivers.base import AgenticMessage, AgenticMessageType


class TestAgenticMessageType:
    """Test AgenticMessageType enum values."""

    def test_has_thinking_type(self) -> None:
        assert AgenticMessageType.THINKING == "thinking"

    def test_has_tool_call_type(self) -> None:
        assert AgenticMessageType.TOOL_CALL == "tool_call"

    def test_has_tool_result_type(self) -> None:
        assert AgenticMessageType.TOOL_RESULT == "tool_result"

    def test_has_result_type(self) -> None:
        assert AgenticMessageType.RESULT == "result"


class TestAgenticMessage:
    """Test AgenticMessage model."""

    def test_creates_thinking_message(self) -> None:
        msg = AgenticMessage(
            type=AgenticMessageType.THINKING,
            content="Let me analyze this problem...",
        )
        assert msg.type == AgenticMessageType.THINKING
        assert msg.content == "Let me analyze this problem..."
        assert msg.tool_name is None
        assert msg.is_error is False

    def test_creates_tool_call_message(self) -> None:
        msg = AgenticMessage(
            type=AgenticMessageType.TOOL_CALL,
            tool_name="read_file",
            tool_input={"path": "/test.py"},
            tool_call_id="call_123",
        )
        assert msg.type == AgenticMessageType.TOOL_CALL
        assert msg.tool_name == "read_file"
        assert msg.tool_input == {"path": "/test.py"}
        assert msg.tool_call_id == "call_123"

    def test_creates_tool_result_message(self) -> None:
        msg = AgenticMessage(
            type=AgenticMessageType.TOOL_RESULT,
            tool_name="read_file",
            tool_output="file contents here",
            tool_call_id="call_123",
            is_error=False,
        )
        assert msg.type == AgenticMessageType.TOOL_RESULT
        assert msg.tool_output == "file contents here"
        assert msg.is_error is False

    def test_creates_error_result_message(self) -> None:
        msg = AgenticMessage(
            type=AgenticMessageType.TOOL_RESULT,
            tool_name="read_file",
            tool_output="File not found",
            tool_call_id="call_123",
            is_error=True,
        )
        assert msg.is_error is True

    def test_creates_result_message(self) -> None:
        msg = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="Task completed successfully",
            session_id="session_abc",
        )
        assert msg.type == AgenticMessageType.RESULT
        assert msg.content == "Task completed successfully"
        assert msg.session_id == "session_abc"

    def test_is_error_defaults_to_false(self) -> None:
        msg = AgenticMessage(type=AgenticMessageType.THINKING, content="test")
        assert msg.is_error is False


from amelia.core.types import StreamEvent, StreamEventType


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
