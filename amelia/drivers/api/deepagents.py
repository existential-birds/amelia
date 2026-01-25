"""DeepAgents-based API driver for LLM generation and agentic execution."""
import asyncio
import os
import subprocess
import time
from collections.abc import AsyncIterator
from typing import Any, ClassVar
from uuid import uuid4

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.backends.protocol import (
    ExecuteResponse,
    SandboxBackendProtocol,
)
from langchain.agents.middleware.types import AgentMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
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


class LocalSandbox(FilesystemBackend, SandboxBackendProtocol):
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
            "Use driver='api' with the model name directly "
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

    # Class-level session storage for conversation continuity
    # Maps session_id -> MemorySaver checkpointer
    _sessions: ClassVar[dict[str, MemorySaver]] = {}

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
        **kwargs: Any,
    ) -> AsyncIterator[AgenticMessage]:
        """Execute prompt with autonomous tool access using DeepAgents.

        Uses the DeepAgents library to create an autonomous agent that can
        use filesystem tools to complete tasks.

        Args:
            prompt: The prompt to execute.
            cwd: Working directory for tool execution.
            session_id: Optional session ID for conversation continuity. If
                provided, reuses the checkpointer from a previous call to
                maintain conversation history. If None, creates a new session.
            instructions: Optional system prompt for the agent. Passed with
                every request to preserve system-level guidance.
            schema: Unused (structured output not supported in agentic mode).
            tools: Optional list of tools to provide to the agent. If None,
                uses default tools (ls, read_file, write_file, edit_file,
                glob, grep, execute, write_todos).
            required_tool: If set, agent will be prompted to continue if this
                tool wasn't called. Use "write_file" to ensure file creation.
            max_continuations: Maximum continuation attempts if required_tool
                wasn't called. Default 3.

        Yields:
            AgenticMessage for each event (thinking, tool_call, tool_result, result).

        Raises:
            ValueError: If prompt is empty.
            RuntimeError: If execution fails.
        """

        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        # Extract optional parameters from kwargs
        tools: list[Any] | None = kwargs.get("tools")
        middleware: list[AgentMiddleware] | None = kwargs.get("middleware")
        required_tool: str | None = kwargs.get("required_tool")
        required_file_path: str | None = kwargs.get("required_file_path")
        max_continuations: int = kwargs.get("max_continuations", 10)

        # Initialize usage tracking
        start_time = time.perf_counter()
        total_input = 0
        total_output = 0
        total_cost = 0.0
        num_turns = 0
        seen_message_ids: set[int] = set()

        try:
            chat_model = _create_chat_model(self.model, provider=self.provider)
            # virtual_mode=True ensures paths like "docs/plans/..." resolve relative
            # to cwd (e.g., /project/docs/plans/...) rather than being treated as
            # absolute paths from filesystem root (e.g., /docs/plans/...)
            backend = LocalSandbox(root_dir=cwd, virtual_mode=True)

            # Session management for conversation continuity
            # - If session_id is provided, reuse the existing checkpointer
            # - If session_id is None, create a new session with fresh checkpointer
            is_new_session = session_id is None
            current_session_id = session_id or str(uuid4())

            if current_session_id in ApiDriver._sessions:
                checkpointer = ApiDriver._sessions[current_session_id]
                logger.debug(
                    "Resuming existing session",
                    session_id=current_session_id,
                )
            else:
                checkpointer = MemorySaver()
                ApiDriver._sessions[current_session_id] = checkpointer
                logger.debug(
                    "Created new session",
                    session_id=current_session_id,
                )

            # Use session_id as thread_id for checkpointing
            thread_id = current_session_id

            # LLM APIs are stateless - always pass system prompt with every request
            effective_system_prompt = instructions or ""

            agent = create_deep_agent(
                model=chat_model,
                system_prompt=effective_system_prompt,
                backend=backend,
                checkpointer=checkpointer,
                tools=tools,
                middleware=middleware or (),
            )

            logger.debug(
                "Starting agentic execution",
                model=self.model,
                cwd=cwd,
                prompt_length=len(prompt),
                session_id=current_session_id,
                is_new_session=is_new_session,
            )

            last_message: AIMessage | None = None
            tool_call_count = 0  # DEBUG: Track tool calls
            last_write_todos_input: dict[str, Any] | None = None  # Track incomplete tasks
            all_tool_names: list[str] = []  # Track all tool calls for debugging
            continuation_count = 0

            # Config for checkpointing
            config = {"configurable": {"thread_id": thread_id}}

            # Initial message
            current_input: dict[str, Any] = {"messages": [HumanMessage(content=prompt)]}

            # Continuation loop - keeps going until required file is created or max attempts
            while True:
                async for chunk in agent.astream(
                    current_input,
                    config=config,
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
                                    thinking_text = block.get("text", "")
                                    if thinking_text:
                                        logger.debug(
                                            "Streaming thinking content",
                                            thinking_preview=thinking_text[:200],
                                            model=self.model,
                                        )
                                    yield AgenticMessage(
                                        type=AgenticMessageType.THINKING,
                                        content=thinking_text,
                                        model=self.model,
                                    )
                                # Also check for 'thinking' type blocks (some models use this)
                                elif isinstance(block, dict) and block.get("type") == "thinking":
                                    thinking_text = block.get("thinking", "") or block.get("text", "")
                                    if thinking_text:
                                        logger.debug(
                                            "Streaming thinking block",
                                            thinking_preview=thinking_text[:200],
                                            model=self.model,
                                        )
                                    yield AgenticMessage(
                                        type=AgenticMessageType.THINKING,
                                        content=thinking_text,
                                        model=self.model,
                                    )

                        # Tool calls
                        for tool_call in message.tool_calls or []:
                            tool_raw_name = tool_call["name"]
                            # Normalize tool name to standard format
                            tool_normalized = normalize_tool_name(tool_raw_name)
                            tool_call_count += 1
                            all_tool_names.append(tool_normalized)
                            tool_args = tool_call.get("args", {})

                            # Track write_todos calls to detect incomplete tasks
                            if tool_raw_name == "write_todos":
                                last_write_todos_input = tool_args
                                logger.info(
                                    "Agent called write_todos",
                                    todos=tool_args.get("todos", []),
                                )

                            logger.debug(
                                "Tool call",
                                tool_name=tool_normalized,
                                tool_call_number=tool_call_count,
                                tool_args_keys=list(tool_args.keys()),
                            )
                            yield AgenticMessage(
                                type=AgenticMessageType.TOOL_CALL,
                                tool_name=tool_normalized,
                                tool_input=tool_args,
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

                # After inner loop: check if we need to continue
                needs_continuation = False
                continuation_reason = ""

                # Check if required tool was called
                if required_tool and required_tool not in all_tool_names:
                    needs_continuation = True
                    continuation_reason = "required tool not called"

                # If required_file_path is specified, verify file exists with content
                if required_file_path and not needs_continuation:
                    file_path = backend.cwd / required_file_path
                    if not file_path.exists():
                        needs_continuation = True
                        continuation_reason = "file not created"
                    elif file_path.stat().st_size == 0:
                        needs_continuation = True
                        continuation_reason = "file is empty"

                if needs_continuation:
                    continuation_count += 1

                    if continuation_count > max_continuations:
                        logger.warning(
                            "Max continuations reached",
                            reason=continuation_reason,
                            required_file_path=required_file_path,
                            attempts=continuation_count,
                            tool_sequence=all_tool_names,
                        )
                        break

                    # Extract agent's final response for debugging
                    agent_response = ""
                    if last_message:
                        if isinstance(last_message.content, str):
                            agent_response = last_message.content
                        elif isinstance(last_message.content, list):
                            for block in last_message.content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    agent_response += block.get("text", "")

                    response_preview = agent_response[:500] if agent_response else "EMPTY"
                    logger.info(
                        f"Agent stopped before completing task ({continuation_reason}), "
                        f"continuing ({continuation_count}/{max_continuations}). "
                        f"Agent said: {response_preview}",
                    )

                    # Build continuation message - focus on the file, not the tool
                    if required_file_path:
                        continuation_msg = (
                            f"You haven't completed the task yet. "
                            f"Please create the file `{required_file_path}` with the required content."
                        )
                    else:
                        continuation_msg = (
                            "You haven't completed the task yet. Please continue."
                        )
                    current_input = {"messages": [HumanMessage(content=continuation_msg)]}
                else:
                    break  # Done - required tool was called and file exists

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
            # Check for incomplete tasks in write_todos
            incomplete_tasks: list[str] = []
            if last_write_todos_input:
                todos = last_write_todos_input.get("todos", [])
                for todo in todos:
                    if isinstance(todo, dict) and todo.get("status") == "in_progress":
                        incomplete_tasks.append(todo.get("content", "unknown task"))

            # Log comprehensive summary
            logger.info(
                "API driver execution complete",
                total_tool_calls=tool_call_count,
                num_turns=num_turns,
                all_tool_names=all_tool_names,
                has_last_message=last_message is not None,
                incomplete_tasks_count=len(incomplete_tasks),
            )

            # Warn if agent terminated with incomplete tasks
            if incomplete_tasks:
                logger.warning(
                    "Agent terminated with in_progress tasks - possible premature termination",
                    incomplete_tasks=incomplete_tasks,
                    tool_sequence=all_tool_names[-10:] if len(all_tool_names) > 10 else all_tool_names,
                    model=self.model,
                )

            # Warn if no write_file call was made (common failure mode)
            if "write_file" not in all_tool_names:
                logger.warning(
                    "Agent completed without calling write_file - plan may not have been saved",
                    tool_sequence=all_tool_names,
                    model=self.model,
                )

            if last_message:
                final_content = ""
                if isinstance(last_message.content, str):
                    final_content = last_message.content
                elif isinstance(last_message.content, list):
                    for block in last_message.content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            final_content += block.get("text", "")

                # Log the model's final response to understand why it stopped
                preview = final_content[:500] if final_content else "EMPTY"
                logger.info(
                    "Agent final response",
                    length=len(final_content),
                    preview=preview,
                )

                yield AgenticMessage(
                    type=AgenticMessageType.RESULT,
                    content=final_content,
                    session_id=current_session_id,
                    model=self.model,
                )
            else:
                # Always yield RESULT per interface contract
                yield AgenticMessage(
                    type=AgenticMessageType.RESULT,
                    content="Agent produced no output",
                    session_id=current_session_id,
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

    def cleanup_session(self, session_id: str) -> bool:
        """Clean up session state from the class-level cache.

        Delegates to the classmethod to remove the MemorySaver
        checkpointer for the given session.

        Args:
            session_id: The driver session ID to clean up.

        Returns:
            True if session was found and removed, False otherwise.
        """
        return ApiDriver._sessions.pop(session_id, None) is not None
