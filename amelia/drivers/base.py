from collections.abc import AsyncIterator
from typing import Any, Protocol

from pydantic import BaseModel

from amelia.core.state import AgentMessage


class DriverInterface(Protocol):
    """Abstract interface for interaction with LLMs.

    Must be implemented by both CliDriver and ApiDriver.
    Defines the contract for LLM generation, tool execution, and agentic mode.
    """

    async def generate(self, messages: list[AgentMessage], schema: type[BaseModel] | None = None, **kwargs: Any) -> Any:
        """Generate a response from the model.

        Args:
            messages: History of conversation.
            schema: Optional Pydantic model to validate/parse the output.
            **kwargs: Driver-specific parameters (e.g., cwd, session_id).

        Returns:
            Either a string (if no schema) or an instance of the schema.
        """
        ...

    async def execute_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Execute a local tool (if driver supports tool calling).

        Args:
            tool_name: Name of the tool to execute.
            **kwargs: Tool-specific arguments.

        Returns:
            The result of the tool execution, format varies by tool.
        """
        ...

    def execute_agentic(self, prompt: str, cwd: str, session_id: str | None = None) -> AsyncIterator[Any]:
        """Execute prompt with autonomous tool access (agentic mode).

        Args:
            prompt: The task or instruction for the model.
            cwd: Working directory for execution context.
            session_id: Optional session ID to resume.

        Yields:
            Stream events from execution.
        """
        ...
