from typing import Protocol, Any, List
from pydantic import BaseModel

class AgentMessage(BaseModel):
    role: str  # "user", "assistant", "system"
    content: str

class DriverInterface(Protocol):
    """
    Abstract interface for interaction with LLMs.
    Must be implemented by both CliDriver and ApiDriver.
    """

    async def generate(self, messages: List[AgentMessage], schema: type[BaseModel] | None = None) -> Any:
        """
        Generate a response from the model.
        
        Args:
            messages: History of conversation.
            schema: Optional Pydantic model to validate/parse the output.
            
        Returns:
            Either a string (if no schema) or an instance of the schema.
        """
        ...

    async def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """
        Execute a local tool (if driver supports tool calling).
        """
        ...
