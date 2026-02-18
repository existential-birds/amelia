"""DeepAgents-based API driver for LLM generation and agentic execution."""
import asyncio
import functools
import os
import subprocess
import threading
import time
from collections.abc import AsyncIterator
from typing import Any, ClassVar
from uuid import uuid4
from weakref import WeakKeyDictionary

import httpx
import openai
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
from amelia.core.exceptions import ModelProviderError
from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverInterface,
    DriverUsage,
    GenerateResult,
)
from amelia.logging import log_claude_result, log_todos


# Maximum output size before truncation (100KB)
_MAX_OUTPUT_SIZE = 100_000
# Default command timeout in seconds
_DEFAULT_TIMEOUT = 300

# Patterns in ValueError messages that indicate a model provider error (not Amelia's fault).
#
# These patterns are matched case-insensitively against the exception message.
# When a ValueError contains any of these patterns, it's wrapped in ModelProviderError
# instead of being raised directly, providing better error UX for transient LLM issues.
#
# To add a new pattern:
# 1. Identify the error message substring from the LLM provider SDK (usually langchain_openai)
# 2. Add a lowercase pattern that uniquely identifies the provider error
# 3. Test by triggering the error and verifying ModelProviderError is raised
#
# Configurable via AMELIA_PROVIDER_ERROR_PATTERNS env var (comma-separated, lowercase).
_DEFAULT_PROVIDER_ERROR_PATTERNS = (
    "midstream error",  # OpenRouter/provider streaming failures
    "invalid function arguments",  # Bad tool call JSON from provider
    "provider returned error",  # Generic provider-side errors
)


@functools.lru_cache(maxsize=1)
def _get_provider_error_patterns() -> tuple[str, ...]:
    """Get provider error patterns from environment or defaults.

    Reads AMELIA_PROVIDER_ERROR_PATTERNS environment variable dynamically
    to support runtime configuration and testing with mocked environments.

    Returns:
        Tuple of lowercase pattern strings to match against error messages.
    """
    patterns_str = os.environ.get(
        "AMELIA_PROVIDER_ERROR_PATTERNS",
        ",".join(_DEFAULT_PROVIDER_ERROR_PATTERNS),
    )
    return tuple(p.strip().lower() for p in patterns_str.split(",") if p.strip())


def _is_model_provider_error(exc: ValueError) -> bool:
    """Check if a ValueError originates from a model provider rather than Amelia validation.

    langchain_openai raises ValueError with a dict arg when the provider returns
    an error (e.g. bad JSON from Minimax). Amelia's own validation uses string args.

    Args:
        exc: The ValueError to inspect.

    Returns:
        True if this looks like a model provider error.
    """
    # langchain_openai pattern: ValueError({"error": {...}, "provider": "..."})
    if exc.args and isinstance(exc.args[0], dict):
        return True
    # String-based detection for known provider error patterns
    msg = str(exc).lower()
    return any(pattern in msg for pattern in _get_provider_error_patterns())


def _extract_provider_info(exc: ValueError) -> tuple[str | None, str]:
    """Extract provider name and error message from a model provider ValueError.

    Args:
        exc: The ValueError to extract info from.

    Returns:
        Tuple of (provider_name, error_message). provider_name may be None.
    """
    if exc.args and isinstance(exc.args[0], dict):
        err_dict = exc.args[0]
        error_obj = err_dict.get("error", {})
        provider = err_dict.get("provider")

        # Handle unexpected dict structures with explicit logging
        if not isinstance(error_obj, dict):
            logger.debug(
                "Unexpected error_obj type in provider error",
                error_obj_type=type(error_obj).__name__,
                error_obj_value=str(error_obj)[:200],
                err_dict_keys=list(err_dict.keys()),
            )

        message = (
            error_obj.get("message", str(err_dict))
            if isinstance(error_obj, dict)
            else str(error_obj)
        )
        return provider, message
    return None, str(exc)


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
        except OSError as e:
            return ExecuteResponse(
                output=f"Command execution failed: {e}",
                exit_code=1,
                truncated=False,
            )

    async def aexecute(self, command: str) -> ExecuteResponse:
        """Async wrapper for execute (runs in thread pool)."""
        return await asyncio.to_thread(self.execute, command)


def _create_chat_model(
    model: str,
    provider: str | None = None,
    base_url: str | None = None,
) -> BaseChatModel:
    """Create a LangChain chat model, handling provider configuration.

    Args:
        model: Model identifier (e.g., 'minimax/minimax-m2').
        provider: Optional provider name. If 'openrouter', configures OpenRouter API.
        base_url: Optional base URL override. Used for proxy routing when running
            in sandboxed environments. Only applies to OpenRouter provider.

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

        resolved_url = base_url or "https://openrouter.ai/api/v1"

        return init_chat_model(
            model=model,
            model_provider="openai",
            base_url=resolved_url,
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

    # Maximum number of sessions to retain before evicting oldest
    # Configurable via AMELIA_DRIVER_MAX_SESSIONS environment variable
    _MAX_SESSIONS: ClassVar[int] = max(
        1, int(os.environ.get("AMELIA_DRIVER_MAX_SESSIONS", "100"))
    )

    # Class-level session storage for conversation continuity
    # Maps session_id -> MemorySaver checkpointer
    # Least recently used sessions are evicted when _MAX_SESSIONS is exceeded (LRU).
    # On eviction, adelete_thread() is called to clear the checkpointer's internal
    # storage, then the checkpointer is garbage-collected (no callback mechanism).
    _sessions: ClassVar[dict[str, MemorySaver]] = {}

    # Per-loop lock storage using WeakKeyDictionary pattern:
    # - asyncio.Lock is bound to a specific event loop and cannot be shared across loops
    # - WeakKeyDictionary uses the event loop as key, so each loop gets its own lock
    # - When an event loop is garbage collected, its lock entry is automatically removed
    # - This enables safe concurrent access in multi-loop scenarios (e.g., pytest-asyncio)
    _sessions_lock_by_loop: ClassVar[
        WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]
    ] = WeakKeyDictionary()
    # Threading lock to protect _sessions_lock_by_loop mutations (check-then-act pattern)
    _sessions_lock_by_loop_guard: ClassVar[threading.Lock] = threading.Lock()

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

    @classmethod
    def _sessions_lock_for_loop(cls) -> asyncio.Lock:
        """Get or create an asyncio.Lock for the current event loop.

        Uses WeakKeyDictionary with the event loop as key to provide per-loop locks.
        This is necessary because asyncio.Lock is bound to a specific event loop and
        cannot be shared across loops (e.g., in pytest-asyncio where each test may
        run in a different loop). When a loop is garbage collected, its lock entry
        is automatically removed.

        Returns:
            The asyncio.Lock associated with the current running event loop.
        """
        loop = asyncio.get_running_loop()
        with cls._sessions_lock_by_loop_guard:
            lock = cls._sessions_lock_by_loop.get(loop)
            if lock is None:
                lock = asyncio.Lock()
                cls._sessions_lock_by_loop[loop] = lock
                logger.debug(
                    "Created new per-loop lock",
                    loop_id=id(loop),
                    total_locks=len(cls._sessions_lock_by_loop),
                )
            return lock

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

        except ValueError as e:
            if _is_model_provider_error(e):
                provider_name, raw_msg = _extract_provider_info(e)
                raise ModelProviderError(
                    f"Model provider error ({provider_name or 'unknown'}): {raw_msg}. "
                    "This is a temporary issue with the AI provider, not a bug in Amelia.",
                    provider_name=provider_name,
                    original_message=raw_msg,
                ) from e
            raise
        except (httpx.TransportError, openai.APIConnectionError) as e:
            raise ModelProviderError(
                f"Transient connection error: {e}",
                provider_name="openai-compatible",
                original_message=str(e),
            ) from e
        except Exception as e:
            raise RuntimeError(f"ApiDriver generation failed: {e}") from e

    async def execute_agentic(
        self,
        prompt: str,
        cwd: str,
        session_id: str | None = None,
        instructions: str | None = None,
        schema: type[BaseModel] | None = None,
        allowed_tools: list[str] | None = None,
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
            allowed_tools: Not supported. Raises NotImplementedError if set.
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

        if allowed_tools is not None:
            raise NotImplementedError(
                "allowed_tools is not supported by ApiDriver. "
                "Use ClaudeCliDriver for tool-restricted execution."
            )

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

            async with ApiDriver._sessions_lock_for_loop():
                if current_session_id in ApiDriver._sessions:
                    checkpointer = ApiDriver._sessions[current_session_id]
                    # Move to end for LRU eviction (re-insert to update order)
                    del ApiDriver._sessions[current_session_id]
                    ApiDriver._sessions[current_session_id] = checkpointer
                    logger.debug(
                        "Resuming existing session",
                        session_id=current_session_id,
                    )
                else:
                    checkpointer = MemorySaver()
                    # Evict least recently used sessions if at capacity (LRU via dict order)
                    while len(ApiDriver._sessions) >= ApiDriver._MAX_SESSIONS:
                        oldest_id = next(iter(ApiDriver._sessions))
                        evicted_checkpointer = ApiDriver._sessions.pop(oldest_id)
                        # Clean up checkpointer's internal storage to prevent memory leak
                        await evicted_checkpointer.adelete_thread(oldest_id)
                        logger.debug("Evicted oldest session", session_id=oldest_id)
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
                                    log_claude_result(result_type="assistant", content=thinking_text)
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
                                    log_claude_result(result_type="assistant", content=thinking_text)

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
                                todos = tool_args.get("todos", [])
                                logger.info(
                                    "Agent called write_todos",
                                    todo_count=len(todos),
                                )
                                log_todos(todos)

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
                            log_claude_result(result_type="tool_use", tool_name=tool_normalized, tool_input=tool_args)

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
                            tool_sequence=", ".join(all_tool_names),
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
                tool_names=", ".join(all_tool_names[-10:]),
                has_last_message=last_message is not None,
                incomplete_tasks_count=len(incomplete_tasks),
            )

            # Warn if agent terminated with incomplete tasks
            if incomplete_tasks:
                logger.warning(
                    "Agent terminated with in_progress tasks - possible premature termination",
                    incomplete_tasks=", ".join(incomplete_tasks),
                    tool_sequence=", ".join(all_tool_names[-10:]),
                    model=self.model,
                )

            # Warn if no write_file call was made (common failure mode)
            if "write_file" not in all_tool_names:
                logger.warning(
                    "Agent completed without calling write_file - plan may not have been saved",
                    tool_sequence=", ".join(all_tool_names),
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
                log_claude_result(
                    result_type="result",
                    result_text=final_content,
                    session_id=current_session_id,
                    duration_ms=duration_ms,
                    cost_usd=total_cost if total_cost > 0 else None,
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
                log_claude_result(result_type="error", content="Agent produced no output")

        except ValueError as e:
            if _is_model_provider_error(e):
                provider_name, raw_msg = _extract_provider_info(e)
                raise ModelProviderError(
                    f"Model provider error ({provider_name or 'unknown'}): {raw_msg}. "
                    "This is a temporary issue with the AI provider, not a bug in Amelia.",
                    provider_name=provider_name,
                    original_message=raw_msg,
                ) from e
            raise
        except (httpx.TransportError, openai.APIConnectionError) as e:
            raise ModelProviderError(
                f"Transient connection error: {e}",
                provider_name="openai-compatible",
                original_message=str(e),
            ) from e
        except Exception as e:
            raise RuntimeError(f"Agentic execution failed: {e}") from e

    def get_usage(self) -> DriverUsage | None:
        """Return accumulated usage from last execution.

        Returns:
            DriverUsage with accumulated totals, or None if no execution occurred.
        """
        return self._usage

    async def cleanup_session(self, session_id: str) -> bool:
        """Clean up session state from the class-level cache.

        Delegates to the classmethod to remove the MemorySaver
        checkpointer for the given session.

        Args:
            session_id: The driver session ID to clean up.

        Returns:
            True if session was found and removed, False otherwise.
        """
        async with ApiDriver._sessions_lock_for_loop():
            checkpointer = ApiDriver._sessions.pop(session_id, None)
            if checkpointer is not None:
                # Clean up checkpointer's internal storage to prevent memory leak
                await checkpointer.adelete_thread(session_id)
                return True
            return False

    @classmethod
    async def clear_all_sessions(cls) -> int:
        """Clear all session state from the class-level cache.

        Useful for cleanup on server shutdown or testing.

        Returns:
            Number of sessions that were cleared.
        """
        async with cls._sessions_lock_for_loop():
            sessions = list(cls._sessions.items())
            cls._sessions.clear()

        for session_id, checkpointer in sessions:
            await checkpointer.adelete_thread(session_id)

        count = len(sessions)
        if count > 0:
            logger.debug("Cleared all sessions", count=count)
        return count
