"""Sandbox worker entrypoint — runs inside the container.

Receives a prompt, runs a DeepAgents agent or single-turn LLM call,
and streams AgenticMessage objects as JSON lines to stdout.

Two run modes:

``serve`` (long-lived, preferred):
    python -m amelia.sandbox.worker serve
    Imports the heavy LangChain/deepagents stack ONCE at startup, then reads
    length-prefixed JSON requests from stdin and services many commands over
    its lifetime. The driver keeps one ``serve`` process per sandbox so the
    import cost is paid once per sandbox, not once per agent call.

``agentic`` / ``generate`` (one-shot, legacy/fallback):
    python -m amelia.sandbox.worker agentic --prompt-file /tmp/p.txt --cwd /workspace --model m
    python -m amelia.sandbox.worker generate --prompt-file /tmp/p.txt --model m [--schema mod:Cls]
    Spawns a fresh process per call and pays the import cost each time. Kept
    for transports (e.g. Daytona) that cannot hold a long-lived stdin pipe.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sys
import tempfile
import time
from enum import StrEnum
from typing import Any, Protocol, cast

from loguru import logger
from pydantic import BaseModel, ValidationError


class _LineSink(Protocol):
    """Minimal write target for emitted JSON lines.

    Satisfied by ``sys.stdout``, ``io.StringIO``, and the serve-mode framing
    writer, so the run functions can emit to any of them.
    """

    def write(self, data: str, /) -> int: ...

    def flush(self) -> None: ...


# --- Inlined types (standalone: no amelia imports in the container) --------

class DriverUsage(BaseModel):
    """Token usage data returned by drivers.

    All fields optional - drivers populate what they can.
    """

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None
    num_turns: int | None = None
    model: str | None = None


class AgenticMessageType(StrEnum):
    """Types of messages yielded during agentic execution."""

    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    RESULT = "result"
    USAGE = "usage"


class AgenticMessage(BaseModel):
    """Unified message type for agentic execution across all drivers."""

    type: AgenticMessageType
    content: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: str | None = None
    tool_call_id: str | None = None
    session_id: str | None = None
    is_error: bool = False
    model: str | None = None
    usage: DriverUsage | None = None


# Mapping of CLI-specific tool names to normalized canonical names.
TOOL_NAME_ALIASES: dict[str, str] = {
    "Read": "read_file",
    "Write": "write_file",
    "Edit": "edit_file",
    "NotebookEdit": "notebook_edit",
    "Glob": "glob",
    "Grep": "grep",
    "Bash": "run_shell_command",
    "Task": "task",
    "TaskOutput": "task_output",
    "TaskStop": "task_stop",
    "EnterPlanMode": "enter_plan_mode",
    "ExitPlanMode": "exit_plan_mode",
    "AskUserQuestion": "ask_user_question",
    "Skill": "skill",
    "TaskCreate": "task_create",
    "TaskGet": "task_get",
    "TaskUpdate": "task_update",
    "TaskList": "task_list",
    "WebFetch": "web_fetch",
    "WebSearch": "web_search",
    "KnowledgeSearch": "knowledge_search",
}


def normalize_tool_name(raw_name: str) -> str:
    """Normalize driver-specific tool name to standard tool name.

    Args:
        raw_name: The raw tool name from a driver (e.g., "Write", "Bash").

    Returns:
        The normalized tool name (e.g., "write_file"), or raw_name if no alias exists.
    """
    return TOOL_NAME_ALIASES.get(raw_name, raw_name)


def _emit_line(msg: AgenticMessage, file: _LineSink = sys.stdout) -> None:
    """Write a single AgenticMessage as a JSON line to the given stream.

    Args:
        msg: Message to serialize.
        file: Output stream (default: stdout).
    """
    file.write(msg.model_dump_json() + "\n")
    file.flush()


def _emit_usage(usage: DriverUsage, file: _LineSink = sys.stdout) -> None:
    """Emit the final USAGE message.

    Args:
        usage: Accumulated usage data.
        file: Output stream.
    """
    msg = AgenticMessage(type=AgenticMessageType.USAGE, usage=usage)
    _emit_line(msg, file=file)


def _import_schema(schema_path: str) -> type[BaseModel]:
    """Dynamically import a schema class from a 'module:ClassName' path.

    Args:
        schema_path: Fully qualified path like 'amelia.agents.schemas.evaluator:EvaluationOutput'.

    Returns:
        The imported Pydantic model class.

    Raises:
        ValueError: If format is not 'module:ClassName'.
        ImportError: If module cannot be imported.
        AttributeError: If class doesn't exist in the module.
    """
    if ":" not in schema_path:
        raise ValueError(
            f"Schema path must be 'module:ClassName', got: '{schema_path}'"
        )
    module_path, class_name = schema_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    return cast(type[BaseModel], getattr(module, class_name))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse worker CLI arguments.

    Args:
        argv: Argument list (default: sys.argv[1:]).

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Amelia sandbox worker",
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    # Long-lived mode: import once, read length-prefixed requests from stdin.
    sub.add_parser("serve")

    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--prompt-file", required=True, help="Path to prompt file")
    shared.add_argument("--model", required=True, help="LLM model identifier")

    agentic = sub.add_parser("agentic", parents=[shared])
    agentic.add_argument("--cwd", required=True, help="Working directory")
    agentic.add_argument("--instructions", help="System instructions")

    generate = sub.add_parser("generate", parents=[shared])
    generate.add_argument("--schema", help="Schema as module:ClassName")

    return parser.parse_args(argv)


def _read_prompt(path: str) -> str:
    """Read prompt from file.

    Args:
        path: Path to the prompt file.

    Returns:
        Prompt text content.
    """
    with open(path, encoding="utf-8") as f:
        return f.read()


def _create_worker_chat_model(model: str, base_url: str | None = None) -> Any:
    """Create a chat model for the worker, using proxy URL if available.

    Args:
        model: Model identifier.
        base_url: Optional proxy base URL.

    Returns:
        Configured LangChain chat model.
    """
    from langchain.chat_models import init_chat_model  # noqa: PLC0415

    if base_url:
        # Route through proxy or direct API — use openai-compatible interface.
        # When going through the local proxy, api_key is "proxy-managed".
        # When calling the LLM API directly (e.g. Daytona), use OPENAI_API_KEY.
        api_key = os.environ.get("OPENAI_API_KEY", "proxy-managed")
        profile = os.environ.get("AMELIA_PROFILE", "")
        headers: dict[str, str] = {}
        if profile:
            headers["X-Amelia-Profile"] = profile
        proxy_token = os.environ.get("AMELIA_PROXY_TOKEN", "")
        if proxy_token:
            headers["X-Amelia-Proxy-Token"] = proxy_token

        # Inject OpenRouter app attribution headers so requests from
        # Daytona sandbox workers show "Amelia" instead of "unknown".
        if "openrouter.ai" in base_url:
            headers["HTTP-Referer"] = os.environ.get(
                "OPENROUTER_SITE_URL",
                "https://github.com/existential-birds/amelia",
            )
            headers["X-Title"] = os.environ.get("OPENROUTER_SITE_NAME", "Amelia")

        return init_chat_model(
            model=model,
            model_provider="openai",
            base_url=base_url,
            api_key=api_key,
            default_headers=headers,
        )
    return init_chat_model(model)


def _import_stack() -> None:
    """Import the heavy LangChain/deepagents stack.

    In ``serve`` mode this is called ONCE at startup so subsequent commands
    pay no import cost. In one-shot mode it is called per process (the cost
    the long-lived worker exists to eliminate). Imports are deferred here
    rather than at module top so the lightweight protocol path (and the
    standalone Daytona upload) does not drag in the stack unnecessarily.
    """
    import deepagents  # noqa: F401, PLC0415
    import deepagents.backends  # noqa: F401, PLC0415
    import langchain.agents.structured_output  # noqa: F401, PLC0415
    import langchain.chat_models  # noqa: F401, PLC0415
    import langchain_core.messages  # noqa: F401, PLC0415


async def _run_agentic(
    *,
    prompt: str,
    model: str,
    cwd: str,
    instructions: str | None,
    file: _LineSink = sys.stdout,
) -> None:
    """Run agentic mode — full tool-using agent execution.

    Args:
        prompt: The task prompt.
        model: LLM model identifier.
        cwd: Working directory for the filesystem backend.
        instructions: Optional system instructions.
        file: Output stream for emitted JSON-line messages.
    """
    from deepagents import create_deep_agent  # noqa: PLC0415
    from deepagents.backends import FilesystemBackend  # noqa: PLC0415
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: PLC0415

    base_url = os.environ.get("LLM_PROXY_URL")

    chat_model = _create_worker_chat_model(model, base_url=base_url)
    backend = FilesystemBackend(root_dir=cwd, virtual_mode=True)

    agent = create_deep_agent(
        model=chat_model,
        system_prompt=instructions or "",
        backend=backend,
    )

    start_time = time.monotonic()
    total_input = 0
    total_output = 0
    num_turns = 0
    chunk: dict[str, Any] = {}  # Initialize to avoid UnboundLocalError if agent yields nothing

    async for chunk in agent.astream(
        {"messages": [HumanMessage(content=prompt)]},
        stream_mode="values",
    ):
        messages = chunk.get("messages", [])
        if not messages:
            continue
        message = messages[-1]
        num_turns += 1

        if hasattr(message, "usage_metadata") and message.usage_metadata:
            total_input += message.usage_metadata.get("input_tokens", 0)
            total_output += message.usage_metadata.get("output_tokens", 0)

        if isinstance(message, AIMessage):
            content = message.content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        _emit_line(AgenticMessage(
                            type=AgenticMessageType.THINKING,
                            content=block["text"],
                            model=model,
                        ), file=file)
            elif isinstance(content, str) and content:
                _emit_line(AgenticMessage(
                    type=AgenticMessageType.THINKING,
                    content=content,
                    model=model,
                ), file=file)

            for tc in message.tool_calls:
                _emit_line(AgenticMessage(
                    type=AgenticMessageType.TOOL_CALL,
                    tool_name=normalize_tool_name(tc["name"]),
                    tool_input=tc.get("args", {}),
                    tool_call_id=tc.get("id"),
                    model=model,
                ), file=file)

        elif isinstance(message, ToolMessage):
            _emit_line(AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name=normalize_tool_name(message.name or "unknown"),
                tool_output=str(message.content)[:10000],
                tool_call_id=message.tool_call_id,
                is_error=getattr(message, "status", None) == "error",
                model=model,
            ), file=file)

    if num_turns == 0:
        raise RuntimeError("Agent stream yielded no messages")

    final_content = ""
    for msg in reversed(chunk.get("messages", [])):
        if isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, str):
                final_content = content
            elif isinstance(content, list):
                final_content = " ".join(
                    b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text"
                )
            break

    _emit_line(AgenticMessage(
        type=AgenticMessageType.RESULT,
        content=final_content,
        model=model,
    ), file=file)

    duration_ms = int((time.monotonic() - start_time) * 1000)
    _emit_usage(DriverUsage(
        input_tokens=total_input or None,
        output_tokens=total_output or None,
        duration_ms=duration_ms,
        num_turns=num_turns,
        model=model,
    ), file=file)


async def _run_generate(
    *,
    prompt: str,
    model: str,
    schema_path: str | None,
    file: _LineSink = sys.stdout,
) -> None:
    """Run generate mode — single-turn structured output.

    Args:
        prompt: The generation prompt.
        model: LLM model identifier.
        schema_path: Optional ``module:ClassName`` schema path.
        file: Output stream for emitted JSON-line messages.
    """
    from deepagents import create_deep_agent  # noqa: PLC0415
    from deepagents.backends import FilesystemBackend  # noqa: PLC0415
    from langchain.agents.structured_output import ToolStrategy  # noqa: PLC0415
    from langchain_core.messages import HumanMessage  # noqa: PLC0415

    base_url = os.environ.get("LLM_PROXY_URL")

    chat_model = _create_worker_chat_model(model, base_url=base_url)

    schema = _import_schema(schema_path) if schema_path else None

    start_time = time.monotonic()

    if schema:
        agent = create_deep_agent(
            model=chat_model,
            backend=FilesystemBackend(root_dir=tempfile.gettempdir(), virtual_mode=True),
            response_format=ToolStrategy(schema=schema),
        )
        result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})

        structured = result.get("structured_response")
        if structured is not None:
            content = structured.model_dump_json() if isinstance(structured, BaseModel) else str(structured)
        else:
            # Fallback: extract from last AI message
            content = ""
            for msg in reversed(result.get("messages", [])):
                if hasattr(msg, "content") and msg.content:
                    raw = msg.content if isinstance(msg.content, str) else str(msg.content)
                    try:
                        parsed = schema.model_validate_json(raw)
                        content = parsed.model_dump_json()
                    except ValidationError:
                        content = raw
                    break
    else:
        result = await chat_model.ainvoke([HumanMessage(content=prompt)])
        content = result.content if hasattr(result, "content") else str(result)

    total_input = 0
    total_output = 0
    for msg in result.get("messages", []) if isinstance(result, dict) else [result]:
        if hasattr(msg, "usage_metadata") and msg.usage_metadata:
            total_input += msg.usage_metadata.get("input_tokens", 0)
            total_output += msg.usage_metadata.get("output_tokens", 0)

    _emit_line(AgenticMessage(
        type=AgenticMessageType.RESULT,
        content=content,
        model=model,
    ), file=file)

    duration_ms = int((time.monotonic() - start_time) * 1000)
    _emit_usage(DriverUsage(
        input_tokens=total_input or None,
        output_tokens=total_output or None,
        duration_ms=duration_ms,
        model=model,
    ), file=file)


async def _dispatch_request(request: Any, file: _LineSink) -> None:
    """Run a single decoded request, writing JSON-line messages to ``file``.

    Args:
        request: A WorkerRequest with mode/prompt/model and mode-specific fields.
        file: Output stream for the command's messages.
    """
    if request.mode == "agentic":
        await _run_agentic(
            prompt=request.prompt,
            model=request.model,
            cwd=request.cwd or os.getcwd(),
            instructions=request.instructions,
            file=file,
        )
    elif request.mode == "generate":
        await _run_generate(
            prompt=request.prompt,
            model=request.model,
            schema_path=request.schema_path,
            file=file,
        )
    else:  # pragma: no cover - guarded by WorkerRequest validation
        raise ValueError(f"Unknown request mode: {request.mode!r}")


async def _serve(stdin: Any = None, stdout: _LineSink = sys.stdout) -> None:
    """Long-lived serve loop — import once, dispatch many commands.

    Reads length-prefixed JSON requests from ``stdin`` (binary) and writes
    newline-delimited response frames to ``stdout``. Each command is
    terminated with a ``done`` frame; a failing command emits an ``error``
    frame (followed by ``done``) but does NOT kill the worker, so the next
    command is still served. A clean EOF on stdin ends the loop.

    Commands are serviced strictly sequentially: the loop awaits each
    dispatch fully (including its ``done`` frame) before reading the next
    request, so concurrent commands from the driver are serialized on the
    wire by construction.

    Args:
        stdin: Binary input stream (defaults to ``sys.stdin.buffer``).
        stdout: Text output stream for response frames.
    """
    from amelia.sandbox.protocol import (  # noqa: PLC0415
        done_frame,
        error_frame,
        msg_frame_raw,
        read_request,
    )

    if stdin is None:
        stdin = sys.stdin.buffer

    # Pay the heavy import cost ONCE, before serving any command.
    _import_stack()
    logger.info("Sandbox worker ready (stack imported once)")

    while True:
        request = read_request(stdin)
        if request is None:
            logger.info("Worker stdin closed, shutting down")
            return

        # The run functions emit plain AgenticMessage JSON lines; this adapter
        # re-wraps each complete line as a ``msg`` response frame so serve-mode
        # output is framed without changing the run functions.
        framed = _FramingWriter(stdout, msg_frame_raw)
        try:
            await _dispatch_request(request, framed)
            framed.flush()
            stdout.write(done_frame())
            stdout.flush()
        except Exception as exc:  # noqa: BLE001 - report, survive, keep serving
            logger.exception("Command failed")
            framed.flush()
            stdout.write(error_frame(str(exc)))
            stdout.write(done_frame())
            stdout.flush()


class _FramingWriter:
    """File-like adapter that re-frames each written AgenticMessage line.

    The run functions call ``_emit_line`` which does ``file.write(json + "\\n")``
    then ``file.flush()``. This adapter intercepts those writes, wraps each
    complete JSON line in a ``msg`` response frame via ``frame_fn``, and
    forwards it to the real stdout.
    """

    def __init__(self, out: _LineSink, frame_fn: Any) -> None:
        self._out = out
        self._frame_fn = frame_fn
        self._partial = ""

    def write(self, data: str) -> int:
        self._partial += data
        while "\n" in self._partial:
            line, self._partial = self._partial.split("\n", 1)
            if line:
                self._out.write(self._frame_fn(line))
        return len(data)

    def flush(self) -> None:
        if self._partial.strip():
            self._out.write(self._frame_fn(self._partial))
        self._partial = ""
        self._out.flush()


async def _main() -> None:
    """Worker entrypoint."""
    # Route loguru to stderr so stdout is reserved for JSON lines
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")

    args = _parse_args()
    if args.mode == "serve":
        await _serve()
    elif args.mode == "agentic":
        await _run_agentic(
            prompt=_read_prompt(args.prompt_file),
            model=args.model,
            cwd=args.cwd,
            instructions=args.instructions,
        )
    elif args.mode == "generate":
        await _run_generate(
            prompt=_read_prompt(args.prompt_file),
            model=args.model,
            schema_path=args.schema,
        )


if __name__ == "__main__":
    asyncio.run(_main())
