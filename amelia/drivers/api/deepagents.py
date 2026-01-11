"""DeepAgents-based API driver for LLM generation and agentic execution."""
import asyncio
import os
import subprocess
import time
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
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from loguru import logger
from pydantic import BaseModel

from amelia.core.constants import normalize_tool_name
from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverInterface,
    DriverUsage,
    GenerateResult,
)


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


def _create_chat_model(model: str, provider: str | None = None) -> BaseChatModel:
    """Create a LangChain chat model, handling provider configuration.

    Args:
        model: Model identifier (e.g., 'minimax/minimax-m2').
        provider: Optional provider name. If 'openrouter', configures OpenRouter API.

    Returns:
        Configured BaseChatModel instance.

    Raises:
        ValueError: If model contains 'openrouter:' prefix (use provider param instead).
        ValueError: If OpenRouter is requested but OPENROUTER_API_KEY is not set.
    """
    if model.startswith("openrouter:"):
        raise ValueError(
            "The 'openrouter:' prefix in model names is no longer supported. "
            "Use driver='api:openrouter' with the model name directly "
            f"(e.g., model='{model[len('openrouter:'):]}')."
        )

    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable is required for OpenRouter models"
            )

        site_url = os.environ.get(
            "OPENROUTER_SITE_URL", "https://github.com/existential-birds/amelia"
        )
        site_name = os.environ.get("OPENROUTER_SITE_NAME", "Amelia")

        return init_chat_model(
            model=model,
            model_provider="openai",
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers={
                "HTTP-Referer": site_url,
                "X-Title": site_name,
            },
        )

    return init_chat_model(model)


class ApiDriver(DriverInterface):
    """DeepAgents-based driver for LLM generation and agentic execution.

    Uses LangGraph-based autonomous agent via the deepagents library.
    Supports any model available through langchain's init_chat_model.

    Attributes:
        model: The model identifier (e.g., 'minimax/minimax-m2').
        provider: The provider name (e.g., 'openrouter').
        cwd: Working directory for agentic execution.
    """

    DEFAULT_MODEL = "minimax/minimax-m2"

    def __init__(
        self,
        model: str | None = None,
        cwd: str | None = None,
        provider: str = "openrouter",
    ):
        """Initialize the API driver.

        Args:
            model: Model identifier for langchain (e.g., 'minimax/minimax-m2').
            cwd: Working directory for agentic execution. Required for execute_agentic().
            provider: Provider name (e.g., 'openrouter'). Defaults to 'openrouter'.
        """
        self.model = model or self.DEFAULT_MODEL
        self.provider = provider
        self.cwd = cwd
        self._usage: DriverUsage | None = None

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
            chat_model = _create_chat_model(self.model, provider=self.provider)
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

    async def execute_agentic(
        self,
        prompt: str,
        cwd: str,
        session_id: str | None = None,
        instructions: str | None = None,
        schema: type[BaseModel] | None = None,
    ) -> AsyncIterator[AgenticMessage]:
        """Execute prompt with autonomous tool access using DeepAgents.

        Uses the DeepAgents library to create an autonomous agent that can
        use filesystem tools to complete tasks.

        Args:
            prompt: The prompt to execute.
            cwd: Working directory for tool execution.
            session_id: Unused (API driver has no session support).
            instructions: Unused (system prompt set at agent creation).
            schema: Unused (structured output not supported in agentic mode).

        Yields:
            AgenticMessage for each event (thinking, tool_call, tool_result, result).

        Raises:
            ValueError: If prompt is empty.
            RuntimeError: If execution fails.
        """

        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        # Initialize usage tracking
        start_time = time.perf_counter()
        total_input = 0
        total_output = 0
        total_cost = 0.0
        num_turns = 0
        seen_message_ids: set[int] = set()

        try:
            chat_model = _create_chat_model(self.model, provider=self.provider)
            backend = LocalSandbox(root_dir=cwd)
            agent = create_deep_agent(
                model=chat_model,
                system_prompt="",
                backend=backend,
            )

            logger.debug(
                "Starting agentic execution",
                model=self.model,
                cwd=cwd,
                prompt_length=len(prompt),
            )

            last_message: AIMessage | None = None
            tool_call_count = 0  # DEBUG: Track tool calls

            async for chunk in agent.astream(
                {"messages": [HumanMessage(content=prompt)]},
                stream_mode="values",
            ):
                messages = chunk.get("messages", [])
                if not messages:
                    continue

                message = messages[-1]

                if isinstance(message, AIMessage):
                    last_message = message

                    # Extract usage from new AIMessages (avoid double-counting)
                    msg_id = id(message)
                    if msg_id not in seen_message_ids:
                        seen_message_ids.add(msg_id)
                        num_turns += 1

                        # Extract token usage from usage_metadata
                        usage_meta = getattr(message, "usage_metadata", None)
                        if usage_meta:
                            total_input += usage_meta.get("input_tokens", 0)
                            total_output += usage_meta.get("output_tokens", 0)

                        # Extract cost from OpenRouter response_metadata
                        # OpenRouter returns cost in token_usage object
                        resp_meta = getattr(message, "response_metadata", None)
                        if resp_meta:
                            token_usage = resp_meta.get("token_usage", {})
                            total_cost += token_usage.get("cost", 0.0)

                    # Text blocks in list content -> THINKING (intermediate text during tool use)
                    # Plain string content is NOT yielded as THINKING - it will be yielded as RESULT
                    # at the end to avoid duplicate content (same pattern as ClaudeCliDriver where
                    # TextBlock -> THINKING and ResultMessage.result -> RESULT are distinct sources)
                    if isinstance(message.content, list):
                        for block in message.content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                yield AgenticMessage(
                                    type=AgenticMessageType.THINKING,
                                    content=block.get("text", ""),
                                    model=self.model,
                                )

                    # Tool calls
                    for tool_call in message.tool_calls or []:
                        tool_raw_name = tool_call["name"]
                        # Normalize tool name to standard format
                        tool_normalized = normalize_tool_name(tool_raw_name)
                        tool_call_count += 1  # DEBUG: Increment counter
                        # DEBUG: Log tool call normalization
                        logger.debug(
                            "DEBUG: API driver yielding tool call",
                            raw_name=tool_raw_name,
                            normalized_name=tool_normalized,
                            input_keys=list(tool_call.get("args", {}).keys()),
                            tool_call_number=tool_call_count,
                        )
                        yield AgenticMessage(
                            type=AgenticMessageType.TOOL_CALL,
                            tool_name=tool_normalized,
                            tool_input=tool_call.get("args", {}),
                            tool_call_id=tool_call.get("id"),
                            model=self.model,
                        )

                elif isinstance(message, ToolMessage):
                    # Normalize tool name to standard format
                    result_raw_name = message.name
                    result_normalized: str | None = (
                        normalize_tool_name(result_raw_name)
                        if result_raw_name
                        else None
                    )
                    yield AgenticMessage(
                        type=AgenticMessageType.TOOL_RESULT,
                        tool_name=result_normalized,
                        tool_output=str(message.content),
                        tool_call_id=message.tool_call_id,
                        is_error=message.status == "error",
                        model=self.model,
                    )

            # Store accumulated usage before yielding result
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            self._usage = DriverUsage(
                input_tokens=total_input if total_input > 0 else None,
                output_tokens=total_output if total_output > 0 else None,
                cost_usd=total_cost if total_cost > 0 else None,
                duration_ms=duration_ms,
                num_turns=num_turns if num_turns > 0 else None,
                model=self.model,
            )

            # Final result from last AI message
            # DEBUG: Log summary before yielding result
            logger.debug(
                "DEBUG: API driver execution complete",
                total_tool_calls=tool_call_count,
                num_turns=num_turns,
                has_last_message=last_message is not None,
            )

            if last_message:
                final_content = ""
                if isinstance(last_message.content, str):
                    final_content = last_message.content
                elif isinstance(last_message.content, list):
                    for block in last_message.content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            final_content += block.get("text", "")

                yield AgenticMessage(
                    type=AgenticMessageType.RESULT,
                    content=final_content,
                    session_id=None,  # API driver has no session support
                    model=self.model,
                )
            else:
                # Always yield RESULT per interface contract
                yield AgenticMessage(
                    type=AgenticMessageType.RESULT,
                    content="Agent produced no output",
                    session_id=None,
                    is_error=True,
                    model=self.model,
                )

        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"Agentic execution failed: {e}") from e

    def get_usage(self) -> DriverUsage | None:
        """Return accumulated usage from last execution.

        Returns:
            DriverUsage with accumulated totals, or None if no execution occurred.
        """
        return self._usage
