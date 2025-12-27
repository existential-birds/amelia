"""State model for agentic execution.

This module defines the state model for agentic (tool-calling) execution,
replacing the structured batch/step execution model.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


AgenticStatus = Literal["running", "awaiting_approval", "completed", "failed", "cancelled"]


class ToolCall(BaseModel):
    """A tool call made by the LLM.

    Attributes:
        id: Unique identifier for this call.
        tool_name: Name of the tool being called.
        tool_input: Input parameters for the tool.
        timestamp: When the call was made (ISO format).
    """

    model_config = ConfigDict(frozen=True)

    id: str
    tool_name: str
    tool_input: dict[str, Any]
    timestamp: str | None = None


class ToolResult(BaseModel):
    """Result from a tool execution.

    Attributes:
        call_id: ID of the ToolCall this result is for.
        tool_name: Name of the tool that was called.
        output: Output from the tool (stdout, file content, etc.).
        success: Whether the tool executed successfully.
        error: Error message if success is False.
        duration_ms: Execution time in milliseconds.
    """

    model_config = ConfigDict(frozen=True)

    call_id: str
    tool_name: str
    output: str
    success: bool
    error: str | None = None
    duration_ms: int | None = None


class AgenticState(BaseModel):
    """State for agentic workflow execution.

    Tracks the conversation, tool calls, and results for an agentic
    execution session where the LLM autonomously decides actions.

    Attributes:
        workflow_id: Unique workflow identifier.
        issue_key: Issue being worked on.
        goal: High-level goal or task description.
        system_prompt: System prompt for the agent.
        tool_calls: History of tool calls made.
        tool_results: History of tool results received.
        final_response: Final response from the agent when complete.
        status: Current execution status.
        error: Error message if status is 'failed'.
        session_id: Session ID for driver continuity.
    """

    model_config = ConfigDict(frozen=True)

    workflow_id: str
    issue_key: str
    goal: str
    system_prompt: str | None = None

    # Tool execution history
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()

    # Completion state
    final_response: str | None = None
    status: AgenticStatus = "running"
    error: str | None = None

    # Session continuity
    session_id: str | None = None
