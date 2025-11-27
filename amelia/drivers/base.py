from typing import Any
from typing import Protocol

from pydantic import BaseModel

from amelia.core.state import AgentMessage


class DriverInterface(Protocol):
    """
    Abstract interface for interaction with LLMs.
    Must be implemented by both CliDriver and ApiDriver.
    """

    async def generate(self, messages: list[AgentMessage], schema: type[BaseModel] | None = None) -> Any:
        """
        Generate a response from the model.
        
        Args:
            messages: History of conversation.
            schema: Optional Pydantic model to validate/parse the output.
            
        Returns:
            Either a string (if no schema) or an instance of the schema.
        """
        ...

    async def execute_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """
        Execute a local tool (if driver supports tool calling).
        """
        ...
