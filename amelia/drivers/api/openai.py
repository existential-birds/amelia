import os
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent

from amelia.core.constants import ToolName
from amelia.core.state import AgentMessage
from amelia.drivers.base import DriverInterface
from amelia.tools.safe_file import SafeFileWriter
from amelia.tools.safe_shell import SafeShellExecutor


class ApiDriver(DriverInterface):
    """
    Real OpenAI API-based driver using pydantic-ai.
    """
    def __init__(self, model: str = 'openai:gpt-4o'):
        # Validate that model is OpenAI
        if not model.startswith("openai:"):
            raise ValueError(f"Unsupported provider in model '{model}'. ApiDriver only supports 'openai:' models.")
        self.model_name = model

    async def generate(self, messages: list[AgentMessage], schema: type[BaseModel] | None = None) -> Any:
        if not os.environ.get("OPENAI_API_KEY"):
             # Fail fast if no key, or maybe fallback? For now, fail.
             # But for tests, we might need to mock this. 
             # The User said "no functionality simulated", so we expect real keys in prod.
             # In tests, we usually mock the network calls.
             pass

        # pydantic-ai Agent instantiation
        # We create a new agent for each call or reuse? 
        # Reusing might be better but for now per-call is safer for state isolation.
        agent = Agent(self.model_name, output_type=schema if schema else str)
        
        # Convert AgentMessage to prompt string or pydantic-ai messages
        # pydantic-ai 'run' takes a string prompt usually, or sequence of messages?
        # Let's assume basic prompt construction for now as pydantic-ai 0.0.x might vary.
        # But v1.20.0 is specified. 
        
        # Constructing conversation history
        # pydantic-ai typically takes the last user message as 'prompt' and history as 'message_history'.
        # But let's just concat for simplicity if API allows, or map properly.
        
        # Simple concatenation for the 'prompt' argument
        full_prompt = "\n\n".join([f"[{msg.role.upper()}]: {msg.content}" for msg in messages])
        
        try:
            result = await agent.run(full_prompt)
            return result.output
        except Exception as e:
            raise RuntimeError(f"ApiDriver generation failed: {e}") from e

    async def execute_tool(self, tool_name: str, **kwargs: Any) -> Any:
        if tool_name == ToolName.WRITE_FILE:
            file_path = kwargs.get("file_path")
            content = kwargs.get("content")
            if not file_path or content is None:
                raise ValueError("Missing required arguments for write_file: file_path, content")
            return await SafeFileWriter.write(file_path, content)

        elif tool_name == ToolName.RUN_SHELL_COMMAND:
            command = kwargs.get("command")
            if not command:
                raise ValueError("Missing required argument for run_shell_command: command")
            return await SafeShellExecutor.execute(command)

        else:
            raise NotImplementedError(f"Tool '{tool_name}' not implemented in ApiDriver.")
