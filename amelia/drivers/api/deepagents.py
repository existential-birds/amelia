"""DeepAgents-based API driver for LLM generation and agentic execution."""
import asyncio
import json
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
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from loguru import logger
from pydantic import BaseModel

from amelia.core.constants import normalize_tool_name
from amelia.core.exceptions import ModelProviderError, SchemaValidationError
from amelia.drivers.api.chat_model import (
    _create_chat_model,
    _extract_provider_info,
    _is_model_provider_error,
)
from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverInterface,
    DriverUsage,
    GenerateResult,
    SubmitToolDef,
)
from amelia.logging import log_claude_result, log_todos


__all__ = ["ApiDriver", "LocalSandbox"]

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
        except OSError as e:
            return ExecuteResponse(
                output=f"Command execution failed: {e}",
                exit_code=1,
                truncated=False,
            )

    async def aexecute(self, command: str) -> ExecuteResponse:
        """Async entry point for shell execution.

        The blocking ``subprocess.run(..., shell=True)`` in ``execute`` must
        never run on the event loop, so it is offloaded to a worker thread via
        ``asyncio.to_thread``. The deepagents tool layer awaits this method
        (not the sync ``execute``), keeping the loop responsive during long or
        slow commands.
        """
        return await asyncio.to_thread(self.execute, command)


def _extract_text_content(content: str | list[str | dict[str, Any]]) -> str:
    """Extract plain text from an AI message's content field.

    Handles both string content and list-of-blocks content (where text
    is found in dicts with type='text').

    Args:
        content: Either a plain string or a list of content block dicts.

    Returns:
        The extracted text as a single string.
    """
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "") if isinstance(block, dict) else str(block)
        for block in content
    )


class ApiDriver(DriverInterface):
    """DeepAgents-based driver for LLM generation and agentic execution.

    Uses LangGraph-based autonomous agent via the deepagents library.
    Supports any model available through langchain's init_chat_model.

    Attributes:
        model: The model identifier (e.g., 'minimax/minimax-m2').
        provider: The provider name (e.g., 'openrouter').
        base_url: Optional base URL override for the provider's OpenAI-compatible
            endpoint (required for custom, non-preset providers).
        api_key_env_var: Optional name of the environment variable holding the API
            key (required for custom, non-preset providers).
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
        base_url: str | None = None,
        api_key_env_var: str | None = None,
    ):
        """Initialize the API driver.

        Args:
            model: Model identifier for langchain (e.g., 'minimax/minimax-m2').
            cwd: Working directory for agentic execution. Required for execute_agentic().
            provider: Provider name (e.g., 'openrouter'). Defaults to 'openrouter'.
            base_url: Optional base URL override for the provider's OpenAI-compatible
                endpoint. Required for custom (non-preset) providers.
            api_key_env_var: Optional name of the environment variable holding the API
                key. Required for custom (non-preset) providers; presets supply their own.
        """
        self.model = model or self.DEFAULT_MODEL
        self.provider = provider
        self.base_url = base_url
        self.api_key_env_var = api_key_env_var
        self.cwd = cwd
        self._usage: DriverUsage | None = None
        # Cached chat model (and its underlying httpx/openai client) built once
        # per (provider, model, base_url, api_key_env_var) so back-to-back calls
        # reuse the HTTP connection instead of doing a fresh TCP+TLS handshake.
        self._chat_model: BaseChatModel | None = None
        # Memoized non-agentic generate() agents keyed by (system_prompt, schema, backend_root).
        # The generate() tool set is fixed, so the LangGraph graph is built once
        # per distinct generate backend config rather than rebuilt on every call.
        self._generate_agents: dict[
            tuple[str, type[BaseModel] | None, str], Any
        ] = {}

    def _get_chat_model(self) -> BaseChatModel:
        """Return the cached chat model, building it once on first use.

        Reuses the underlying HTTP client across calls. The missing-API-key
        error still surfaces on first construction; the key rarely changes
        within a process, so caching the model afterward is safe.

        Returns:
            The cached :class:`BaseChatModel` for this driver's provider config.
        """
        if self._chat_model is None:
            self._chat_model = _create_chat_model(
                self.model,
                provider=self.provider,
                base_url=self.base_url,
                api_key_env_var=self.api_key_env_var,
            )
        return self._chat_model

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
            chat_model = self._get_chat_model()

            # The generate() tool set is fixed, so memoize the built agent per
            # (system_prompt, schema, backend root) instead of rebuilding the LangGraph graph
            # (and rebinding tools) on every call.
            effective_system_prompt = system_prompt or ""
            backend_root = self.cwd or "."
            agent_key = (effective_system_prompt, schema, backend_root)
            agent = self._generate_agents.get(agent_key)
            if agent is None:
                # Use FilesystemBackend for non-agentic generation - no shell execution needed
                backend = FilesystemBackend(root_dir=backend_root, virtual_mode=False)

                agent_kwargs: dict[str, Any] = {
                    "model": chat_model,
                    "system_prompt": effective_system_prompt,
                    "backend": backend,
                }
                if schema:
                    agent_kwargs["response_format"] = ToolStrategy(schema=schema)

                agent = create_deep_agent(**agent_kwargs)
                self._generate_agents[agent_key] = agent

            result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})

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
                    messages = result.get("messages", [])
                    last_msg_type = type(messages[-1]).__name__ if messages else "None"
                    logger.warning(
                        "ToolStrategy did not populate structured_response",
                        schema=schema.__name__,
                        message_count=len(messages),
                        last_message_type=last_msg_type,
                    )
                    raise SchemaValidationError(
                        f"Model did not call the {schema.__name__} tool to return structured output. "
                        f"Got {len(messages)} messages, last was {last_msg_type}. "
                        "Ensure the model supports tool calling and the prompt instructs it to use the schema tool.",
                        provider_name="api",
                        original_message=f"Last message type: {last_msg_type}",
                    )
            else:
                messages = result.get("messages", [])
                if not messages:
                    raise RuntimeError("No response messages from agent")

                final_message = messages[-1]
                output = _extract_text_content(final_message.content)

            logger.debug(
                "DeepAgents generate completed",
                model=self.model,
                prompt_length=len(prompt),
            )

            return (output, None)

        except json.JSONDecodeError as e:
            # JSONDecodeError (subclass of ValueError) means the API returned
            # non-JSON (HTML error page, truncated response, etc.) — transient.
            raise ModelProviderError(
                f"API returned invalid JSON response: {e}",
                provider_name="openai-compatible",
                original_message=str(e),
            ) from e
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

    def _resolve_allowed(
        self,
        allowed_tools: list[str],
        ctx: Any | None,
    ) -> tuple[list[Any], set[str]]:
        """Resolve an allowed_tools list into rendered tools + a policy allow-set.

        For each canonical name:

        * **Unknown name** — skipped (logged at debug).
        * **Factory tool** — rendered only when ``ctx`` can supply its deps. If
          the factory returns ``None`` (deps missing) the tool is omitted
          entirely so the policy middleware refuses any model attempt to call it.
        * **Handler tool** — rendered to a LangChain ``StructuredTool`` and added
          to the allow-set.
        * **Stub** (no handler, no factory — e.g. library-injected
          ``read_file``) — added to the allow-set only; the deepagents
          ``FilesystemMiddleware`` injects the actual implementation.

        Args:
            allowed_tools: Canonical tool names requested by the caller.
            ctx: Optional ``ToolContext`` for factory tools.

        Returns:
            ``(custom_tools, allow_set)`` where ``custom_tools`` is the list of
            rendered LangChain tools and ``allow_set`` is the set of canonical
            names the ``ToolPolicyMiddleware`` will permit.
        """
        from amelia.tools.registry import registry  # noqa: PLC0415
        from amelia.tools.registry.adapters import to_langchain  # noqa: PLC0415

        custom_tools: list[Any] = []
        allow_set: set[str] = set()

        for name in allowed_tools:
            spec = registry.get(name)
            if spec is None:
                logger.debug("allowed_tools: skipping unknown tool", name=name)
                continue

            if spec.factory is not None:
                # Factory tools need a ToolContext; without one (or when the
                # factory reports the deps unavailable) skip entirely.
                if ctx is None:
                    logger.debug(
                        "allowed_tools: omitting factory tool (no context)",
                        name=name,
                    )
                    continue
                try:
                    handler = spec.factory(ctx)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "allowed_tools: factory raised, omitting tool",
                        name=name,
                    )
                    continue
                if handler is None:
                    logger.debug(
                        "allowed_tools: factory returned None, omitting",
                        name=name,
                    )
                    continue
                bound = spec.model_copy(update={"handler": handler, "factory": None})
                custom_tools.append(to_langchain(bound))
                allow_set.add(name)
            elif spec.handler is not None:
                custom_tools.append(to_langchain(spec))
                allow_set.add(name)
            else:
                # Stub (library-provided) — FilesystemMiddleware injects it.
                allow_set.add(name)

        return custom_tools, allow_set

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
            allowed_tools: Optional list of canonical tool names to allow. When
                set, the driver renders custom tools for specs that carry a real
                handler (or a factory + runtime context) and inserts a
                ``ToolPolicyMiddleware`` that vetoes any tool not in the resolved
                allow-set. When ``None`` (default), no restriction is applied.
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

        tools: list[Any] | None = kwargs.get("tools")
        middleware: list[AgentMiddleware] | None = kwargs.get("middleware")
        required_tool: str | None = kwargs.get("required_tool")
        required_file_path: str | None = kwargs.get("required_file_path")
        max_continuations: int = kwargs.get("max_continuations", 10)

        # Convert SubmitToolDef instances to LangChain StructuredTools and
        # set required_tool so the agent is prompted to call at least one.
        # Done before allowed_tools resolution so submit tool names can be
        # merged into the policy allow-set (they must never be vetoed).
        submit_tools: list[SubmitToolDef] | None = kwargs.get("submit_tools")
        lc_submit_tools: list[Any] = []
        if submit_tools:
            from langchain_core.tools import StructuredTool  # noqa: PLC0415

            def _make_lc_tool(td: SubmitToolDef) -> Any:
                async def _invoke(**tool_kwargs: Any) -> str:
                    await td.on_call(tool_kwargs)
                    return "Submitted successfully."

                return StructuredTool.from_function(
                    coroutine=_invoke,
                    name=td.name,
                    description=td.description,
                    args_schema=td.schema,
                )

            lc_submit_tools = [_make_lc_tool(td) for td in submit_tools]
            tools = lc_submit_tools + (tools or [])
            if required_tool is None and lc_submit_tools:
                required_tool = submit_tools[0].name

        # Resolve allowed_tools: render custom tools from the registry and
        # install a ToolPolicyMiddleware that vetoes anything outside the
        # resolved allow-set. When allowed_tools is None, behavior is unchanged.
        if allowed_tools is not None:
            ctx = kwargs.get("tool_context")
            custom_tools, allow_set = self._resolve_allowed(allowed_tools, ctx)
            if custom_tools:
                tools = (tools or []) + custom_tools
            # Submit tools are always permitted — they're agent-controlled
            # structured output, not user-facing capabilities.
            allow_set.update(td.name for td in (submit_tools or []))
            if allow_set:
                from amelia.tools.registry import ToolPolicy, ToolPolicyMiddleware  # noqa: PLC0415

                policy_mw = ToolPolicyMiddleware(
                    policy=ToolPolicy(allowed=frozenset(allow_set))
                )
                middleware = [policy_mw, *(middleware or [])]

        start_time = time.perf_counter()
        total_input = 0
        total_output = 0
        total_cost = 0.0
        num_turns = 0
        seen_message_ids: set[int] = set()

        try:
            chat_model = self._get_chat_model()
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
            tool_call_count = 0
            last_write_todos_input: dict[str, Any] | None = None
            all_tool_names: list[str] = []
            continuation_count = 0

            config = {"configurable": {"thread_id": thread_id}}

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

                needs_continuation = False
                continuation_reason = ""

                if required_tool and required_tool not in all_tool_names:
                    needs_continuation = True
                    continuation_reason = "required tool not called"

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

                    agent_response = _extract_text_content(last_message.content) if last_message else ""

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

            duration_ms = int((time.perf_counter() - start_time) * 1000)
            self._usage = DriverUsage(
                input_tokens=total_input if total_input > 0 else None,
                output_tokens=total_output if total_output > 0 else None,
                cost_usd=total_cost if total_cost > 0 else None,
                duration_ms=duration_ms,
                num_turns=num_turns if num_turns > 0 else None,
                model=self.model,
            )

            incomplete_tasks: list[str] = []
            if last_write_todos_input:
                todos = last_write_todos_input.get("todos", [])
                for todo in todos:
                    if isinstance(todo, dict) and todo.get("status") == "in_progress":
                        incomplete_tasks.append(todo.get("content", "unknown task"))

            logger.info(
                "API driver execution complete",
                total_tool_calls=tool_call_count,
                num_turns=num_turns,
                tool_names=", ".join(all_tool_names[-10:]),
                has_last_message=last_message is not None,
                incomplete_tasks_count=len(incomplete_tasks),
            )

            if incomplete_tasks:
                logger.warning(
                    "Agent terminated with in_progress tasks - possible premature termination",
                    incomplete_tasks=", ".join(incomplete_tasks),
                    tool_sequence=", ".join(all_tool_names[-10:]),
                    model=self.model,
                )

            # Warn if no file-writing call was made (common failure mode)
            write_tools = {"write_file", "write_plan"}
            if not write_tools.intersection(all_tool_names):
                logger.warning(
                    "Agent completed without calling write_file/write_plan - plan may not have been saved",
                    tool_sequence=", ".join(all_tool_names),
                    model=self.model,
                )

            if last_message:
                final_content = _extract_text_content(last_message.content)

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

        except json.JSONDecodeError as e:
            raise ModelProviderError(
                f"API returned invalid JSON response: {e}",
                provider_name="openai-compatible",
                original_message=str(e),
            ) from e
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
        except openai.APIStatusError as e:
            raise ModelProviderError(
                f"API error (status {e.status_code}): {e.message}",
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
