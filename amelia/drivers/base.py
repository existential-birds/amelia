from collections.abc import AsyncIterator
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel

from amelia.core.types import StreamEvent, StreamEventType


class AgenticMessageType(StrEnum):
    """Types of messages yielded during agentic execution."""

    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    RESULT = "result"


class AgenticMessage(BaseModel):
    """Unified message type for agentic execution across all drivers.

    This provides a common abstraction over driver-specific message types:
    - ClaudeCliDriver: claude_agent_sdk.types.Message
    - ApiDriver: langchain_core.messages.BaseMessage
    """

    type: AgenticMessageType
    content: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: str | None = None
    tool_call_id: str | None = None
    session_id: str | None = None
    is_error: bool = False

    def to_stream_event(self, agent: str, workflow_id: str) -> StreamEvent:
        """Convert to StreamEvent for dashboard consumption.

        Args:
            agent: Agent name (e.g., "developer", "reviewer").
            workflow_id: Unique workflow identifier.

        Returns:
            StreamEvent for dashboard streaming.
        """
        type_mapping = {
            AgenticMessageType.THINKING: StreamEventType.CLAUDE_THINKING,
            AgenticMessageType.TOOL_CALL: StreamEventType.CLAUDE_TOOL_CALL,
            AgenticMessageType.TOOL_RESULT: StreamEventType.CLAUDE_TOOL_RESULT,
            AgenticMessageType.RESULT: StreamEventType.AGENT_OUTPUT,
        }
        return StreamEvent(
            type=type_mapping[self.type],
            content=self.content or self.tool_output,
            timestamp=datetime.now(UTC),
            agent=agent,
            workflow_id=workflow_id,
            tool_name=self.tool_name,
            tool_input=self.tool_input,
            is_error=self.is_error,
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
    ) -> AsyncIterator["AgenticMessage"]:
        """Execute prompt with autonomous tool use, yielding messages.

        Args:
            prompt: The prompt to send.
            cwd: Working directory for tool execution.
            session_id: Optional session ID for conversation continuity.
            instructions: Optional system instructions.
            schema: Optional schema for structured output.

        Yields:
            AgenticMessage for each event during execution.
        """
        ...
