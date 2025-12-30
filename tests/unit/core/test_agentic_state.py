"""Tests for agentic execution state model."""
import pytest
from pydantic import ValidationError

from amelia.core.agentic_state import AgenticState, ToolCall, ToolResult


class TestToolCall:
    """Test ToolCall model."""

    def test_create_tool_call(self) -> None:
        """Should create tool call with required fields."""
        call = ToolCall(
            id="call-1",
            tool_name="run_shell_command",
            tool_input={"command": "ls -la"},
        )
        assert call.id == "call-1"
        assert call.tool_name == "run_shell_command"
        assert call.tool_input == {"command": "ls -la"}

    def test_tool_call_is_frozen(self) -> None:
        """ToolCall should be immutable."""
        call = ToolCall(id="1", tool_name="test", tool_input={})
        with pytest.raises(ValidationError):
            call.id = "2"


class TestToolResult:
    """Test ToolResult model."""

    def test_create_success_result(self) -> None:
        """Should create successful tool result."""
        result = ToolResult(
            call_id="call-1",
            tool_name="run_shell_command",
            output="file1.txt\nfile2.txt",
            success=True,
        )
        assert result.success is True
        assert result.error is None

    def test_create_error_result(self) -> None:
        """Should create error tool result."""
        result = ToolResult(
            call_id="call-1",
            tool_name="run_shell_command",
            output="",
            success=False,
            error="Command not found",
        )
        assert result.success is False
        assert result.error == "Command not found"

    def test_tool_result_is_frozen(self) -> None:
        """ToolResult should be immutable."""
        result = ToolResult(
            call_id="1", tool_name="test", output="ok", success=True
        )
        with pytest.raises(ValidationError):
            result.success = False


class TestAgenticState:
    """Test AgenticState model."""

    def test_create_initial_state(self) -> None:
        """Should create state with conversation history."""
        state = AgenticState(
            workflow_id="wf-123",
            issue_key="ISSUE-1",
            goal="Implement feature X",
        )
        assert state.workflow_id == "wf-123"
        assert state.tool_calls == ()
        assert state.tool_results == ()
        assert state.status == "running"

    def test_state_tracks_tool_history(self) -> None:
        """Should track tool call and result history."""
        call = ToolCall(id="1", tool_name="shell", tool_input={"cmd": "ls"})
        result = ToolResult(call_id="1", tool_name="shell", output="ok", success=True)

        state = AgenticState(
            workflow_id="wf-1",
            issue_key="ISSUE-1",
            goal="test",
            tool_calls=(call,),
            tool_results=(result,),
        )
        assert len(state.tool_calls) == 1
        assert len(state.tool_results) == 1

    def test_agentic_state_is_frozen(self) -> None:
        """AgenticState should be immutable."""
        state = AgenticState(
            workflow_id="wf-1", issue_key="ISSUE-1", goal="test"
        )
        with pytest.raises(ValidationError):
            state.status = "completed"
