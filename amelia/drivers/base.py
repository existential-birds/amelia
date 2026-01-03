from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel


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


# Type alias for generate return value: (output, session_id)
# output is str when no schema, or instance of schema when schema provided
# (Any is used because Python's type system cannot express schema-dependent return types)
# session_id is None when driver doesn't support sessions or no session was returned
GenerateResult = tuple[Any, str | None]


class DriverInterface(Protocol):
    """Abstract interface for interaction with LLMs.

    Must be implemented by both CliDriver and ApiDriver.
    Defines the contract for single-turn LLM generation.

    Note: execute_agentic() is intentionally NOT part of this protocol.
    Each driver implementation (CLI, API) has its own typed execute_agentic()
    method that yields driver-specific message types:
    - ClaudeCliDriver.execute_agentic() yields claude_agent_sdk.types.Message
    - ApiDriver.execute_agentic() yields langchain_core.messages.BaseMessage

    This design allows agents to use isinstance() checks on the driver
    and handle the appropriate message types without type erasure.
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
