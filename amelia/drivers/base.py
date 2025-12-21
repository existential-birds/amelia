# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from collections.abc import AsyncIterator
from typing import Any, Protocol

from pydantic import BaseModel

from amelia.core.state import AgentMessage


# Type alias for generate return value: (output, session_id)
# output is str when no schema, or instance of schema when schema provided
# (Any is used because Python's type system cannot express schema-dependent return types)
# session_id is None when driver doesn't support sessions or no session was returned
GenerateResult = tuple[Any, str | None]


class DriverInterface(Protocol):
    """Abstract interface for interaction with LLMs.

    Must be implemented by both CliDriver and ApiDriver.
    Defines the contract for LLM generation, tool execution, and agentic mode.
    """

    async def generate(self, messages: list[AgentMessage], schema: type[BaseModel] | None = None, **kwargs: Any) -> GenerateResult:
        """Generate a response from the model.

        Args:
            messages: History of conversation.
            schema: Optional Pydantic model to validate/parse the output.
            **kwargs: Driver-specific parameters (e.g., cwd, session_id).

        Returns:
            GenerateResult tuple of (output, session_id):
            - output: str (if no schema) or instance of schema
            - session_id: str if driver supports sessions, None otherwise
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

    def execute_agentic(self, messages: list[AgentMessage], cwd: str, session_id: str | None = None, system_prompt: str | None = None) -> AsyncIterator[Any]:
        """Execute prompt with autonomous tool access (agentic mode).

        Args:
            messages: List of conversation messages (user, assistant only - no system messages).
            cwd: Working directory for execution context.
            session_id: Optional session ID to resume.
            system_prompt: System prompt passed separately via context.system_prompt.

        Yields:
            Stream events from execution.
        """
        ...
