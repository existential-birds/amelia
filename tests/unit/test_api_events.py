"""Tests for API driver stream events."""
import pytest
from amelia.drivers.api.events import ApiStreamEvent, ApiStreamEventType


class TestApiStreamEvent:
    """Test ApiStreamEvent model."""

    def test_create_thinking_event(self):
        """Should create thinking event with content."""
        event = ApiStreamEvent(type="thinking", content="Processing request...")
        assert event.type == "thinking"
        assert event.content == "Processing request..."

    def test_create_tool_use_event(self):
        """Should create tool_use event with tool info."""
        event = ApiStreamEvent(
            type="tool_use",
            tool_name="run_shell_command",
            tool_input={"command": "ls -la"},
        )
        assert event.type == "tool_use"
        assert event.tool_name == "run_shell_command"
        assert event.tool_input == {"command": "ls -la"}

    def test_create_tool_result_event(self):
        """Should create tool_result event."""
        event = ApiStreamEvent(
            type="tool_result",
            tool_name="run_shell_command",
            tool_result="file1.txt\nfile2.txt",
        )
        assert event.type == "tool_result"
        assert event.tool_result == "file1.txt\nfile2.txt"

    def test_create_result_event(self):
        """Should create result event with session_id."""
        event = ApiStreamEvent(
            type="result",
            result_text="Task completed successfully",
            session_id="abc123",
        )
        assert event.type == "result"
        assert event.result_text == "Task completed successfully"
        assert event.session_id == "abc123"

    def test_create_error_event(self):
        """Should create error event."""
        event = ApiStreamEvent(type="error", content="Something went wrong")
        assert event.type == "error"
        assert event.content == "Something went wrong"
