"""Sandbox worker entrypoint — runs inside the container.

Receives a prompt, runs a DeepAgents agent or single-turn LLM call,
and streams AgenticMessage objects as JSON lines to stdout.

Usage:
    python -m amelia.sandbox.worker agentic --prompt-file /tmp/p.txt --cwd /workspace --model m
    python -m amelia.sandbox.worker generate --prompt-file /tmp/p.txt --model m [--schema mod:Cls]
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sys
import time
from typing import IO, Any, TextIO

from loguru import logger
from pydantic import BaseModel

from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverUsage,
)


def _emit_line(msg: AgenticMessage, file: TextIO = sys.stdout) -> None:
    """Write a single AgenticMessage as a JSON line to the given stream.

    Args:
        msg: Message to serialize.
        file: Output stream (default: stdout).
    """
    file.write(msg.model_dump_json() + "\n")
    file.flush()


def _emit_usage(usage: DriverUsage, file: TextIO = sys.stdout) -> None:
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
    return getattr(module, class_name)


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

    # Shared arguments
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--prompt-file", required=True, help="Path to prompt file")
    shared.add_argument("--model", required=True, help="LLM model identifier")

    # agentic subcommand
    agentic = sub.add_parser("agentic", parents=[shared])
    agentic.add_argument("--cwd", required=True, help="Working directory")
    agentic.add_argument("--instructions", help="System instructions")

    # generate subcommand
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
    with open(path) as f:
        return f.read()


def _create_worker_chat_model(model: str, base_url: str | None = None) -> Any:
    """Create a chat model for the worker, using proxy URL if available.

    Args:
        model: Model identifier.
        base_url: Optional proxy base URL.

    Returns:
        Configured LangChain chat model.
    """
    from langchain.chat_models import init_chat_model

    if base_url:
        # Route through proxy — use openai-compatible interface
        return init_chat_model(
            model=model,
            model_provider="openai",
            base_url=base_url,
            api_key="proxy-managed",
        )
    return init_chat_model(model)


async def _run_agentic(args: argparse.Namespace) -> None:
    """Run agentic mode — full tool-using agent execution.

    Args:
        args: Parsed CLI arguments.
    """
    from deepagents import create_deep_agent
    from deepagents.backends import FilesystemBackend
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from amelia.core.constants import normalize_tool_name

    prompt = _read_prompt(args.prompt_file)
    proxy_url = os.environ.get("LLM_PROXY_URL")
    base_url = proxy_url if proxy_url else None

    chat_model = _create_worker_chat_model(args.model, base_url=base_url)
    backend = FilesystemBackend(cwd=args.cwd)

    agent = create_deep_agent(
        chat_model=chat_model,
        backend=backend,
        instructions=args.instructions,
    )

    start_time = time.monotonic()
    total_input = 0
    total_output = 0
    num_turns = 0

    async for chunk in agent.astream(
        {"messages": [HumanMessage(content=prompt)]},
        stream_mode="values",
    ):
        messages = chunk.get("messages", [])
        if not messages:
            continue
        message = messages[-1]
        num_turns += 1

        # Track usage
        if hasattr(message, "usage_metadata") and message.usage_metadata:
            total_input += message.usage_metadata.get("input_tokens", 0)
            total_output += message.usage_metadata.get("output_tokens", 0)

        if isinstance(message, AIMessage):
            # Emit thinking for text content
            content = message.content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        _emit_line(AgenticMessage(
                            type=AgenticMessageType.THINKING,
                            content=block["text"],
                            model=args.model,
                        ))
            elif isinstance(content, str) and content:
                _emit_line(AgenticMessage(
                    type=AgenticMessageType.THINKING,
                    content=content,
                    model=args.model,
                ))

            # Emit tool calls
            for tc in message.tool_calls:
                _emit_line(AgenticMessage(
                    type=AgenticMessageType.TOOL_CALL,
                    tool_name=normalize_tool_name(tc["name"]),
                    tool_input=tc.get("args", {}),
                    tool_call_id=tc.get("id"),
                    model=args.model,
                ))

        elif isinstance(message, ToolMessage):
            _emit_line(AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name=normalize_tool_name(message.name or "unknown"),
                tool_output=str(message.content)[:10000],
                tool_call_id=message.tool_call_id,
                is_error=message.status == "error" if hasattr(message, "status") else False,
                model=args.model,
            ))

    # Final result — last AI message content
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
        model=args.model,
    ))

    duration_ms = int((time.monotonic() - start_time) * 1000)
    _emit_usage(DriverUsage(
        input_tokens=total_input or None,
        output_tokens=total_output or None,
        duration_ms=duration_ms,
        num_turns=num_turns,
        model=args.model,
    ))


async def _run_generate(args: argparse.Namespace) -> None:
    """Run generate mode — single-turn structured output.

    Args:
        args: Parsed CLI arguments.
    """
    prompt = _read_prompt(args.prompt_file)
    proxy_url = os.environ.get("LLM_PROXY_URL")
    base_url = proxy_url if proxy_url else None

    chat_model = _create_worker_chat_model(args.model, base_url=base_url)

    schema = _import_schema(args.schema) if args.schema else None

    start_time = time.monotonic()

    if schema:
        structured_model = chat_model.with_structured_output(schema)
        result = await structured_model.ainvoke(prompt)
        content = result.model_dump_json() if isinstance(result, BaseModel) else str(result)
    else:
        result = await chat_model.ainvoke(prompt)
        content = result.content if hasattr(result, "content") else str(result)

    # Track usage
    total_input = 0
    total_output = 0
    for msg in [result] if not isinstance(result, dict) else result.get("messages", []):
        if hasattr(msg, "usage_metadata") and msg.usage_metadata:
            total_input += msg.usage_metadata.get("input_tokens", 0)
            total_output += msg.usage_metadata.get("output_tokens", 0)

    _emit_line(AgenticMessage(
        type=AgenticMessageType.RESULT,
        content=content,
        model=args.model,
    ))

    duration_ms = int((time.monotonic() - start_time) * 1000)
    _emit_usage(DriverUsage(
        input_tokens=total_input or None,
        output_tokens=total_output or None,
        duration_ms=duration_ms,
        model=args.model,
    ))


async def _main() -> None:
    """Worker entrypoint."""
    # Route loguru to stderr so stdout is reserved for JSON lines
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")

    args = _parse_args()
    if args.mode == "agentic":
        await _run_agentic(args)
    elif args.mode == "generate":
        await _run_generate(args)


if __name__ == "__main__":
    asyncio.run(_main())
