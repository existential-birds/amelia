from collections.abc import AsyncIterator
from datetime import UTC, datetime
import uuid
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol
from uuid import uuid4

from pydantic import BaseModel


if TYPE_CHECKING:
    from amelia.server.models.events import WorkflowEvent


class DriverUsage(BaseModel):
    """Token usage data returned by drivers.

    All fields optional - drivers populate what they can.
    """

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None
    num_turns: int | None = None
    model: str | None = None


class AgenticMessageType(StrEnum):
    """Types of messages yielded during agentic execution."""

    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    RESULT = "result"
    USAGE = "usage"


class AgenticMessage(BaseModel):
    """Unified message type for agentic execution across all drivers.

    This provides a common abstraction over driver-specific message types:
    - ClaudeCliDriver: claude_agent_sdk.types.Message
    - ApiDriver: langchain_core.messages.BaseMessage

    Attributes:
        type: Type of agentic message (thinking, tool_call, tool_result, result).
        content: Text content for thinking or result messages.
        tool_name: Name of the tool being called or returning.
        tool_input: Input parameters for tool calls.
        tool_output: Output from tool execution.
        tool_call_id: Unique identifier for the tool call.
        session_id: Session identifier for conversation continuity.
        is_error: Whether this message represents an error.
    """

    type: AgenticMessageType
    content: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: str | None = None
    tool_call_id: str | None = None
    session_id: str | None = None
    is_error: bool = False
    model: str | None = None
    usage: DriverUsage | None = None

    def _build_message(self) -> str:
        """Build a human-readable message from the agentic message content.

        Returns:
            Message string appropriate for the message type.
        """
        if self.type == AgenticMessageType.THINKING:
            return self.content or "Thinking..."
        elif self.type == AgenticMessageType.TOOL_CALL:
            return f"Calling {self.tool_name or 'tool'}"
        elif self.type == AgenticMessageType.TOOL_RESULT:
            if self.is_error:
                return f"Tool {self.tool_name or 'unknown'} failed"
            return f"Tool {self.tool_name or 'unknown'} completed"
        else:  # RESULT
            return self.content or self.tool_output or "Completed"

    def to_workflow_event(
        self,
        workflow_id: str,
        agent: str,
        sequence: int = 0,
    ) -> "WorkflowEvent":
        """Convert agentic message to WorkflowEvent for emission.

        Args:
            workflow_id: The workflow this event belongs to.
            agent: The agent that generated this message.
            sequence: Event sequence number (0 = will be assigned later).

        Returns:
            WorkflowEvent with trace level.
        """
        # Import inside method to avoid circular imports
        from amelia.server.models.events import (  # noqa: PLC0415
            EventLevel,
            EventType,
            WorkflowEvent,
        )

        type_mapping = {
            AgenticMessageType.THINKING: EventType.CLAUDE_THINKING,
            AgenticMessageType.TOOL_CALL: EventType.CLAUDE_TOOL_CALL,
            AgenticMessageType.TOOL_RESULT: EventType.CLAUDE_TOOL_RESULT,
            AgenticMessageType.RESULT: EventType.AGENT_OUTPUT,
        }

        message = self._build_message()

        return WorkflowEvent(
            id=uuid4(),
            workflow_id=workflow_id,
            sequence=sequence,
            timestamp=datetime.now(UTC),
            agent=agent,
            event_type=type_mapping[self.type],
            level=EventLevel.DEBUG,
            message=message,
            tool_name=self.tool_name,
            tool_input=self.tool_input,
            is_error=self.is_error,
            model=self.model,
        )


# Type alias for generate return value: (output, session_id)
# output is str when no schema, or instance of schema when schema provided
# (Any is used because Python's type system cannot express schema-dependent return types)
# session_id is None when driver doesn't support sessions or no session was returned
GenerateResult = tuple[Any, str | None]


class DriverInterface(Protocol):
    """Protocol defining the LLM driver interface.

    All drivers must implement both generate() for single-turn generation
    and execute_agentic() for autonomous tool-using execution.
    """

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        schema: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> GenerateResult:
        """Generate a response from the model.

        Args:
            prompt: The user prompt to send to the model.
            system_prompt: Optional system prompt for context/instructions.
            schema: Optional Pydantic model to validate/parse the output.
            **kwargs: Driver-specific parameters (e.g., cwd, session_id).

        Returns:
            GenerateResult tuple of (output, session_id):
            - output: str (if no schema) or instance of schema
            - session_id: str if driver supports sessions, None otherwise
        """
        ...

    def execute_agentic(
        self,
        prompt: str,
        cwd: str,
        session_id: str | None = None,
        instructions: str | None = None,
        schema: type[BaseModel] | None = None,
        allowed_tools: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator["AgenticMessage"]:
        """Execute prompt with autonomous tool use, yielding messages.

        Args:
            prompt: The prompt to send.
            cwd: Working directory for tool execution.
            session_id: Optional session ID for conversation continuity.
            instructions: Optional system instructions.
            schema: Optional schema for structured output.
            allowed_tools: Optional list of canonical tool names to allow.
                When None, all tools are available. When set, only listed
                tools may be used. Use canonical names from ToolName enum.
            **kwargs: Driver-specific options (e.g., required_tool, max_continuations).

        Yields:
            AgenticMessage for each event during execution.
        """
        ...

    def get_usage(self) -> DriverUsage | None:
        """Return accumulated usage from last execution, or None if unavailable."""
        ...

    async def cleanup_session(self, session_id: str) -> bool:
        """Clean up driver-specific session state.

        Called when a session is deleted or reaches terminal status.
        Drivers that maintain session state (e.g., checkpointers) should
        release resources here.

        Args:
            session_id: The driver session ID to clean up.

        Returns:
            True if session was found and cleaned up, False otherwise.
        """
        ...
