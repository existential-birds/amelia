"""DeepAgents-based API driver for LLM generation and agentic execution."""
import asyncio
import os
import subprocess
from collections.abc import AsyncIterator
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend  # type: ignore[import-untyped]
from deepagents.backends.protocol import (  # type: ignore[import-untyped]
    ExecuteResponse,
    SandboxBackendProtocol,
)
from langchain.agents.structured_output import ToolStrategy
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from loguru import logger
from pydantic import BaseModel

from amelia.drivers.base import DriverInterface, GenerateResult


# Maximum output size before truncation (100KB)
_MAX_OUTPUT_SIZE = 100_000
# Default command timeout in seconds
_DEFAULT_TIMEOUT = 300


class LocalSandbox(FilesystemBackend, SandboxBackendProtocol):  # type: ignore[misc]
    """FilesystemBackend with local shell execution support.

    Extends FilesystemBackend and implements SandboxBackendProtocol for shell
    command execution. The explicit protocol inheritance is required because
    SandboxBackendProtocol is not @runtime_checkable, so isinstance() checks
    would fail without it.

    WARNING: This runs commands directly on the local machine without
    sandboxing. Only use in trusted environments (e.g., local development
    by the repo owner).

    Attributes:
        cwd: Working directory for command execution.
    """

    @property
    def id(self) -> str:
        """Unique identifier for this sandbox instance."""
        return f"local-{self.cwd}"

    def execute(self, command: str) -> ExecuteResponse:
        """Execute a shell command locally.

        Args:
            command: Shell command to execute.

        Returns:
            ExecuteResponse with output, exit code, and truncation status.
        """
        logger.debug("Executing command", command=command[:100], cwd=str(self.cwd))

        try:
            result = subprocess.run(
                command,
                shell=True,  # noqa: S602 - intentional for local dev
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=_DEFAULT_TIMEOUT,
            )
            output = result.stdout + result.stderr
            truncated = len(output) > _MAX_OUTPUT_SIZE
            if truncated:
                output = output[:_MAX_OUTPUT_SIZE] + "\n... [output truncated]"

            return ExecuteResponse(
                output=output,
                exit_code=result.returncode,
                truncated=truncated,
            )
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                output=f"Command timed out after {_DEFAULT_TIMEOUT} seconds",
                exit_code=124,
                truncated=False,
            )
        except Exception as e:
            return ExecuteResponse(
                output=f"Command execution failed: {e}",
                exit_code=1,
                truncated=False,
            )

    async def aexecute(self, command: str) -> ExecuteResponse:
        """Async wrapper for execute (runs in thread pool)."""
        return await asyncio.to_thread(self.execute, command)


def _create_chat_model(model: str) -> BaseChatModel:
    """Create a LangChain chat model, handling special provider prefixes.

    Handles the 'openrouter:' prefix by configuring ChatOpenAI with OpenRouter's
    base URL. OpenRouter provides an OpenAI-compatible API, so we use the openai
    provider with a custom base_url.

    Args:
        model: Model identifier. Can be:
            - 'openrouter:provider/model' - Routes through OpenRouter
            - Any standard model string (e.g., 'gpt-4', 'claude-3-opus')

    Returns:
        Configured BaseChatModel instance.

    Raises:
        ValueError: If OpenRouter is requested but OPENROUTER_API_KEY is not set.
    """
    if model.startswith("openrouter:"):
        # Extract the model name after 'openrouter:' prefix
        openrouter_model = model[len("openrouter:") :]

        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable is required for OpenRouter models"
            )

        # App attribution headers for OpenRouter rankings/analytics
        # See: https://openrouter.ai/docs/app-attribution
        site_url = os.environ.get(
            "OPENROUTER_SITE_URL", "https://github.com/existential-birds/amelia"
        )
        site_name = os.environ.get("OPENROUTER_SITE_NAME", "Amelia")

        # OpenRouter provides an OpenAI-compatible API
        return init_chat_model(
            model=openrouter_model,
            model_provider="openai",
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers={
                "HTTP-Referer": site_url,
                "X-Title": site_name,
            },
        )

    # Default: let init_chat_model infer the provider
    return init_chat_model(model)


class ApiDriver(DriverInterface):
    """DeepAgents-based driver for LLM generation and agentic execution.

    Uses LangGraph-based autonomous agent via the deepagents library.
    Supports any model available through langchain's init_chat_model.

    Attributes:
        model: The model identifier (e.g., 'openrouter:minimax/minimax-m2').
        cwd: Working directory for agentic execution.
    """

    DEFAULT_MODEL = "openrouter:minimax/minimax-m2"

    def __init__(self, model: str | None = None, cwd: str | None = None):
        """Initialize the API driver.

        Args:
            model: Model identifier for langchain (e.g., 'openrouter:minimax/minimax-m2').
            cwd: Working directory for agentic execution. Required for execute_agentic().
        """
        self.model = model or self.DEFAULT_MODEL
        self.cwd = cwd

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
            **kwargs: Additional arguments (unused).

        Returns:
            GenerateResult tuple of (output, session_id):
            - output: str (if no schema) or instance of schema
            - session_id: Always None for API driver (no session support)

        Raises:
            ValueError: If prompt is empty.
            RuntimeError: If API call fails.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        try:
            chat_model = _create_chat_model(self.model)
            # Use FilesystemBackend for non-agentic generation - no shell execution needed
            backend = FilesystemBackend(root_dir=self.cwd or ".")

            # Configure structured output via ToolStrategy when schema is provided
            agent_kwargs: dict[str, Any] = {
                "model": chat_model,
                "system_prompt": system_prompt or "",
                "backend": backend,
            }
            if schema:
                agent_kwargs["response_format"] = ToolStrategy(schema=schema)

            agent = create_deep_agent(**agent_kwargs)

            result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})

            # If schema is provided, extract from structured_response
            output: Any
            if schema:
                structured_response = result.get("structured_response")
                if structured_response is not None:
                    output = structured_response
                    logger.debug(
                        "Extracted structured response via ToolStrategy",
                        schema=schema.__name__,
                    )
                else:
                    # Log diagnostic info for debugging structured output failures
                    messages = result.get("messages", [])
                    last_msg_type = type(messages[-1]).__name__ if messages else "None"
                    logger.warning(
                        "ToolStrategy did not populate structured_response",
                        schema=schema.__name__,
                        message_count=len(messages),
                        last_message_type=last_msg_type,
                    )
                    raise RuntimeError(
                        f"Model did not call the {schema.__name__} tool to return structured output. "
                        f"Got {len(messages)} messages, last was {last_msg_type}. "
                        "Ensure the model supports tool calling and the prompt instructs it to use the schema tool."
                    )
            else:
                # No schema - extract text from messages
                messages = result.get("messages", [])
                if not messages:
                    raise RuntimeError("No response messages from agent")

                final_message = messages[-1]
                if isinstance(final_message, AIMessage):
                    content = final_message.content
                    if isinstance(content, list):
                        text_parts = [
                            block.get("text", "")
                            if isinstance(block, dict)
                            else str(block)
                            for block in content
                        ]
                        output = "".join(text_parts)
                    else:
                        output = str(content)
                else:
                    output = str(final_message.content)

            logger.debug(
                "DeepAgents generate completed",
                model=self.model,
                prompt_length=len(prompt),
            )

            return (output, None)

        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"ApiDriver generation failed: {e}") from e

    async def execute_agentic(self, prompt: str) -> AsyncIterator[BaseMessage]:
        """Execute prompt with autonomous tool access using DeepAgents.

        Uses the DeepAgents library to create an autonomous agent that can
        use filesystem tools to complete tasks.

        Args:
            prompt: The prompt to execute.

        Yields:
            BaseMessage objects as the agent executes.

        Raises:
            ValueError: If cwd is not set or prompt is empty.
            RuntimeError: If execution fails.
        """
        if not self.cwd:
            raise ValueError("cwd must be set for agentic execution")

        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        try:
            chat_model = _create_chat_model(self.model)
            backend = LocalSandbox(root_dir=self.cwd)
            agent = create_deep_agent(
                model=chat_model,
                system_prompt="",
                backend=backend,
            )

            logger.debug(
                "Starting agentic execution",
                model=self.model,
                cwd=self.cwd,
                prompt_length=len(prompt),
            )

            async for chunk in agent.astream(
                {"messages": [HumanMessage(content=prompt)]},
                stream_mode="values",
            ):
                messages = chunk.get("messages", [])
                if messages:
                    yield messages[-1]

        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"Agentic execution failed: {e}") from e
