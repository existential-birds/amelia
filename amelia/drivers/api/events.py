"""Stream event types for API driver agentic execution."""
from typing import Any, Literal

from pydantic import BaseModel


ApiStreamEventType = Literal["thinking", "tool_use", "tool_result", "result", "error"]


class ApiStreamEvent(BaseModel):
    """Event from API driver agentic execution.

    Mirrors ClaudeStreamEvent structure for unified streaming interface.

    Attributes:
        type: Event type (thinking, tool_use, tool_result, result, error).
        content: Text content for thinking/error events.
        tool_name: Tool name for tool_use/tool_result events.
        tool_input: Tool input parameters for tool_use events.
        tool_result: Tool execution result for tool_result events.
        session_id: Session ID from result events for continuity.
        result_text: Final result text from result events.
    """

    type: ApiStreamEventType
    content: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_result: str | None = None
    session_id: str | None = None
    result_text: str | None = None
