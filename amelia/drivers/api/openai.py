# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.agent import CallToolsNode
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from amelia.core.constants import ToolName
from amelia.core.exceptions import SecurityError
from amelia.core.state import AgentMessage
from amelia.drivers.api.events import ApiStreamEvent
from amelia.drivers.api.tools import AgenticContext, run_shell_command, write_file
from amelia.drivers.base import DriverInterface
from amelia.tools.safe_file import SafeFileWriter
from amelia.tools.safe_shell import SafeShellExecutor


MAX_MESSAGE_SIZE = 100_000  # 100KB per message
MAX_TOTAL_SIZE = 500_000  # 500KB total across all messages
MAX_INSTRUCTIONS_SIZE = 10_000  # 10KB max instructions

# OpenRouter app attribution
OPENROUTER_APP_URL = "https://github.com/existential-birds/amelia"
OPENROUTER_APP_TITLE = "Amelia"


class ApiDriver(DriverInterface):
    """OpenRouter API-based driver using pydantic-ai.

    Provides LLM generation capabilities through OpenRouter's API,
    which supports models from OpenAI, Anthropic, Google, and others.

    Attributes:
        model_name: The model identifier (e.g., 'anthropic/claude-sonnet-4-20250514').
    """

    DEFAULT_MODEL = "anthropic/claude-sonnet-4-20250514"

    def __init__(self, model: str | None = None):
        """Initialize the API driver.

        Args:
            model: Model identifier for OpenRouter (e.g., 'anthropic/claude-sonnet-4-20250514').
                   See https://openrouter.ai/models for available models.
        """
        self.model_name = model or self.DEFAULT_MODEL

    def _build_model(self) -> Model:
        """Build the OpenRouter model with app attribution.

        Returns:
            OpenRouterModel configured with app attribution headers.
        """
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable not set. "
                "Set OPENROUTER_API_KEY env var or use a different provider."
            )
        provider = OpenRouterProvider(
            api_key=api_key,
            app_url=OPENROUTER_APP_URL,
            app_title=OPENROUTER_APP_TITLE,
        )
        return OpenRouterModel(self.model_name, provider=provider)

    def _validate_messages(self, messages: list[AgentMessage]) -> None:
        """Validate message list for security and sanity.

        Args:
            messages: List of messages to validate.

        Raises:
            ValueError: If messages are invalid.
        """
        if not messages:
            raise ValueError("Messages list cannot be empty")

        # Check total size first (prevents many small messages attack)
        total_size = sum(len(m.content or "") for m in messages)
        if total_size > MAX_TOTAL_SIZE:
            raise ValueError(
                f"Total message content exceeds maximum ({MAX_TOTAL_SIZE // 1000}KB). "
                f"Got {total_size} characters."
            )

        for msg in messages:
            if msg.content is None:
                raise ValueError(f"Message with role '{msg.role}' has None content")
            if not msg.content.strip():
                raise ValueError(f"Message with role '{msg.role}' has empty or whitespace-only content")

            if len(msg.content) > MAX_MESSAGE_SIZE:
                raise ValueError(
                    f"Message content exceeds maximum length ({MAX_MESSAGE_SIZE // 1000}KB). "
                    f"Got {len(msg.content)} characters."
                )

            if msg.role not in ("system", "user", "assistant"):
                raise ValueError(f"Invalid message role: {msg.role}")

    def _build_message_history(self, messages: list[AgentMessage]) -> list[ModelMessage] | None:
        """Build pydantic-ai message history from AgentMessages.

        Args:
            messages: Current conversation messages.

        Returns:
            Pydantic-ai ModelMessage list, or None for empty history.
        """
        non_system = [m for m in messages if m.role != "system"]
        if len(non_system) <= 1:
            return None

        history: list[ModelMessage] = []
        for msg in non_system[:-1]:  # Exclude last (current prompt)
            if not msg.content:
                continue
            if msg.role == "user":
                history.append(ModelRequest(parts=[UserPromptPart(content=msg.content)]))
            elif msg.role == "assistant":
                history.append(ModelResponse(parts=[TextPart(content=msg.content)]))

        return history if history else None

    def _generate_session_id(self) -> str:
        """Generate a unique session ID.

        Returns:
            UUID string for session identification.
        """
        return str(uuid.uuid4())

    def _validate_instructions(self, instructions: str | None) -> None:
        """Validate instructions parameter for size and content.

        Args:
            instructions: Optional runtime instructions string.

        Raises:
            ValueError: If instructions are empty/whitespace or exceed size limit.
        """
        if instructions is None:
            return

        if not instructions.strip():
            raise ValueError("instructions cannot be empty or whitespace-only")

        if len(instructions) > MAX_INSTRUCTIONS_SIZE:
            raise ValueError(
                f"instructions exceeds maximum length ({MAX_INSTRUCTIONS_SIZE} chars). "
                f"Got {len(instructions)} characters."
            )

    async def generate(self, messages: list[AgentMessage], schema: type[BaseModel] | None = None, **kwargs: Any) -> tuple[Any, str | None]:
        """Generate a response from the OpenAI model.

        Args:
            messages: List of conversation messages to send.
            schema: Optional Pydantic model for structured output parsing.
            **kwargs: Additional arguments (unused).

        Returns:
            Tuple of (output, session_id):
            - output: Model output, either as string or parsed schema instance
            - session_id: Always None for API driver (no session support)

        Raises:
            ValueError: If message list is empty or does not end with a user message.
            RuntimeError: If API call fails.
        """
        if not os.environ.get("OPENROUTER_API_KEY"):
            raise ValueError("OPENROUTER_API_KEY environment variable is not set. Please configure it to use the ApiDriver.")

        # Extract system messages and combine them into a single system prompt
        system_messages = [msg for msg in messages if msg.role == 'system']
        system_prompt = "\n\n".join(msg.content for msg in system_messages if msg.content) if system_messages else None

        # Create agent with system prompt if present
        agent = Agent(
            self._build_model(),
            output_type=schema if schema else str,
            system_prompt=system_prompt if system_prompt else ()
        )

        # Constructing conversation history
        # Pydantic-ai Agent.run takes the user prompt and history separately.
        # We need to extract the last user message as the prompt, or use a dummy prompt if none.
        # However, Agent.run() signature is run(prompt: str, *, message_history: list[ModelMessage] | None = None)

        # Convert AgentMessages to pydantic-ai ModelMessages
        # Filter out system messages as they're handled via Agent constructor
        non_system_messages = [msg for msg in messages if msg.role != 'system']

        # We'll use the last message as the new prompt if it's from user.
        # Agent.run requires a string prompt from the user.
        history_messages: list[ModelMessage] = []

        # If the last message is from the user, use it as the prompt.
        if non_system_messages and non_system_messages[-1].role == 'user':
            current_prompt = non_system_messages[-1].content
            # Use all previous messages as history
            msgs_to_process = non_system_messages[:-1]
        elif non_system_messages:
            # No user message at the end - this is an invalid state
            raise ValueError("Cannot generate response: message list must end with a user message")
        else:
            # No messages at all
            raise ValueError("Cannot generate response: message list is empty after filtering system messages")

        for msg in msgs_to_process:
            if not msg.content:
                continue  # Skip messages with no content

            if msg.role == 'user':
                history_messages.append(ModelRequest(parts=[UserPromptPart(content=msg.content)]))
            elif msg.role == 'assistant':
                history_messages.append(ModelResponse(parts=[TextPart(content=msg.content)])) 
                
        try:
            result = await agent.run(current_prompt, message_history=history_messages)
            # Log usage information for monitoring
            logger.debug(
                "API call completed",
                usage=str(result.usage()) if hasattr(result, 'usage') else "N/A",
                model=self.model_name,
            )
            # Return tuple with None session_id (API drivers don't support sessions)
            return (result.output, None)
        except Exception as e:
            raise RuntimeError(f"ApiDriver generation failed: {e}") from e

    async def execute_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Execute a local tool by delegating to safe utilities.

        Args:
            tool_name: Name of the tool to execute (from ToolName constants).
            **kwargs: Tool-specific arguments.

        Returns:
            Tool execution result.

        Raises:
            ValueError: If required arguments are missing.
            NotImplementedError: If tool is not supported.
        """
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

    async def execute_agentic(
        self,
        messages: list[AgentMessage],
        cwd: str,
        session_id: str | None = None,
        instructions: str | None = None,
    ) -> AsyncIterator[ApiStreamEvent]:
        """Execute prompt with autonomous tool access using pydantic-ai.

        Args:
            messages: List of conversation messages.
            cwd: Working directory for execution context.
            session_id: Optional session ID (accepted for interface compatibility,
                        pydantic-ai manages conversation state via message_history).
            instructions: Runtime instructions for the agent.

        Yields:
            ApiStreamEvent objects as tools execute.

        Raises:
            ValueError: If invalid messages or cwd.
        """
        # Note: session_id is accepted for interface compatibility but not used
        # pydantic-ai manages its own conversation state via message_history
        if session_id:
            logger.debug(
                "session_id parameter provided but not used for continuity. "
                "Pydantic-ai manages conversation state via message_history parameter instead."
            )

        self._validate_messages(messages)
        self._validate_instructions(instructions)

        # Create agent with tools
        agent = Agent(
            self._build_model(),
            output_type=str,
            tools=[run_shell_command, write_file],
        )

        # Build context
        context = AgenticContext(cwd=cwd, allowed_dirs=[cwd])

        # Extract current prompt from last user message
        non_system = [m for m in messages if m.role != "system"]
        if not non_system or non_system[-1].role != "user":
            raise ValueError("Messages must end with a user message")
        current_prompt = non_system[-1].content

        if not current_prompt or not current_prompt.strip():
            raise ValueError("User message cannot be empty")

        # Build message history from prior messages
        history = self._build_message_history(messages)

        new_session_id = self._generate_session_id()

        try:
            async with agent.iter(  # type: ignore[call-overload]
                current_prompt,
                deps=context,
                message_history=history,
                instructions=instructions,
            ) as agent_run:
                async for node in agent_run:
                    # Process tool calls from CallToolsNode
                    if isinstance(node, CallToolsNode):
                        for part in node.model_response.parts:
                            if isinstance(part, ToolCallPart):
                                yield ApiStreamEvent(
                                    type="tool_use",
                                    tool_name=part.tool_name,
                                    tool_input=part.args_as_dict(),
                                )

                # Final result
                yield ApiStreamEvent(
                    type="result",
                    result_text=str(agent_run.result.output) if agent_run.result else "",
                    session_id=new_session_id,
                )

        except ValueError as e:
            logger.info("Validation failed", error=str(e))
            yield ApiStreamEvent(type="error", content=f"Invalid input: {e}")

        except SecurityError as e:
            logger.warning("Security violation", error=str(e))
            yield ApiStreamEvent(type="error", content=f"Security violation: {e}")

        except GeneratorExit:
            # Consumer closed the generator (e.g., via break) - just exit cleanly
            return

        except Exception as e:
            # Handle cancel scope cleanup errors from pydantic-ai/anyio during generator close
            if "cancel scope" in str(e).lower() or isinstance(e.__cause__, asyncio.CancelledError):
                logger.debug("Generator cleanup during cancel scope", error=str(e))
                return
            logger.error("Agentic execution failed", error=str(e), error_type=type(e).__name__)
            yield ApiStreamEvent(type="error", content=str(e))
