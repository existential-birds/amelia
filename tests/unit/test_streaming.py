"""Unit tests for WebSocket streaming helpers."""

from io import StringIO
from typing import cast

import pytest
from rich.console import Console

from amelia.client.streaming import _display_event


@pytest.fixture
def console() -> Console:
    """Create a test console that writes to a string buffer."""
    return Console(file=StringIO(), highlight=False)


def get_output(console: Console) -> str:
    """Extract text output from console buffer."""
    return cast(StringIO, console.file).getvalue()


class TestDisplayEventTraceTypes:
    """Tests for trace event type formatting in _display_event."""

    def test_claude_thinking_displays_agent_and_preview(self, console: Console) -> None:
        """claude_thinking events show agent name and truncated message."""
        event = {
            "event_type": "claude_thinking",
            "agent": "developer",
            "message": "I need to analyze the code structure first",
        }
        _display_event(console, event)
        output = get_output(console)
        assert "developer" in output
        assert "thinking" in output

    def test_claude_thinking_truncates_long_message(self, console: Console) -> None:
        """claude_thinking truncates messages longer than 200 chars."""
        long_message = "x" * 300
        event = {
            "event_type": "claude_thinking",
            "agent": "developer",
            "message": long_message,
        }
        _display_event(console, event)
        output = get_output(console)
        # Should contain at most 200 x's (truncated)
        assert "x" * 201 not in output

    def test_claude_thinking_handles_empty_agent(self, console: Console) -> None:
        """claude_thinking works with empty agent field."""
        event = {
            "event_type": "claude_thinking",
            "message": "Some thinking",
        }
        _display_event(console, event)
        output = get_output(console)
        assert "thinking" in output

    def test_claude_tool_call_displays_tool_name(self, console: Console) -> None:
        """claude_tool_call events show the tool name."""
        event = {
            "event_type": "claude_tool_call",
            "agent": "developer",
            "data": {"tool_name": "read_file"},
        }
        _display_event(console, event)
        output = get_output(console)
        assert "read_file" in output
        assert "developer" in output

    def test_claude_tool_call_handles_missing_data(self, console: Console) -> None:
        """claude_tool_call shows 'unknown' when data is missing."""
        event = {
            "event_type": "claude_tool_call",
            "agent": "developer",
        }
        _display_event(console, event)
        output = get_output(console)
        assert "unknown" in output

    def test_claude_tool_call_handles_none_data(self, console: Console) -> None:
        """claude_tool_call shows 'unknown' when data is None."""
        event = {
            "event_type": "claude_tool_call",
            "agent": "developer",
            "data": None,
        }
        _display_event(console, event)
        output = get_output(console)
        assert "unknown" in output

    def test_agent_output_displays_result_header(self, console: Console) -> None:
        """agent_output events show a result header with agent name."""
        event = {
            "event_type": "agent_output",
            "agent": "architect",
            "message": "The plan has been created.",
        }
        _display_event(console, event)
        output = get_output(console)
        assert "architect" in output
        assert "Result" in output

    def test_agent_output_displays_message_content(self, console: Console) -> None:
        """agent_output events show message content."""
        event = {
            "event_type": "agent_output",
            "agent": "developer",
            "message": "Implementation complete.",
        }
        _display_event(console, event)
        output = get_output(console)
        assert "Implementation complete." in output

    def test_agent_output_truncates_long_message(self, console: Console) -> None:
        """agent_output truncates messages longer than 500 chars."""
        long_message = "y" * 600
        event = {
            "event_type": "agent_output",
            "agent": "developer",
            "message": long_message,
        }
        _display_event(console, event)
        output = get_output(console)
        assert "y" * 501 not in output

    def test_agent_output_handles_empty_message(self, console: Console) -> None:
        """agent_output works with empty message."""
        event = {
            "event_type": "agent_output",
            "agent": "developer",
            "message": "",
        }
        _display_event(console, event)
        output = get_output(console)
        assert "Result" in output

    def test_unknown_event_type_uses_dim_default(self, console: Console) -> None:
        """Unknown event types fall through to dim default formatting."""
        event = {
            "event_type": "some_unknown_type",
            "message": "Some message",
        }
        _display_event(console, event)
        output = get_output(console)
        assert "some_unknown_type" in output
        assert "Some message" in output
