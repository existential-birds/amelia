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
