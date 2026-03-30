"""write_plan tool for structured plan generation.

Provides a LangChain-compatible tool that accepts structured plan input,
validates it, renders consistent markdown, and writes to the filesystem.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from loguru import logger
from pydantic import ValidationError

from amelia.tools.write_plan_renderer import render_plan_markdown
from amelia.tools.write_plan_schema import WritePlanInput


class WritePlanValidationError(Exception):
    """Raised when write_plan input fails schema validation."""

    def __init__(self, errors: str, original: ValidationError) -> None:
        self.errors = errors
        self.original = original
        super().__init__(errors)


@dataclass(frozen=True)
class WritePlanResult:
    """Typed success result from execute_write_plan."""

    path: Path
    task_count: int
    goal: str


async def execute_write_plan(
    tool_input: dict[str, Any],
    *,
    root_dir: str,
) -> WritePlanResult:
    """Execute the write_plan tool: validate, render, write.

    This is the core implementation used by both the LangChain tool wrapper
    and direct invocation from pipeline/CLI drivers.

    Args:
        tool_input: Raw dict from LLM tool call (matches WritePlanInput schema).
        root_dir: Root directory for resolving relative file paths.

    Returns:
        WritePlanResult on success.

    Raises:
        WritePlanValidationError: If tool_input fails schema validation.
        ValueError: If the resolved path escapes root_dir.
    """
    # Validate structured input
    try:
        plan = WritePlanInput(**tool_input)
    except ValidationError as exc:
        errors = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        logger.warning("write_plan validation failed", errors=errors)
        raise WritePlanValidationError(errors, exc) from exc

    # Render to markdown
    markdown = render_plan_markdown(plan)

    # Resolve file path
    file_path = Path(plan.file_path)
    root = Path(root_dir)
    if file_path.is_absolute() and file_path.is_relative_to(root):
        # Already an absolute path under root_dir — use as-is
        resolved = file_path
    elif file_path.is_absolute():
        # Virtual absolute path (e.g., /docs/plans/test.md) — resolve relative to root
        resolved = root / str(file_path).lstrip("/")
    else:
        resolved = root / file_path

    # Guard: resolved path must stay under root_dir
    resolved = resolved.resolve()
    root_resolved = root.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise ValueError(
            f"file_path {plan.file_path!r} resolves to {resolved}, "
            f"which is outside root_dir {root_resolved}"
        )

    # Ensure parent directory exists
    await asyncio.to_thread(resolved.parent.mkdir, parents=True, exist_ok=True)

    # Write markdown file
    await asyncio.to_thread(resolved.write_text, markdown, encoding="utf-8")
    logger.info(
        "write_plan: wrote plan file",
        path=str(resolved),
        tasks=len(plan.tasks),
        content_length=len(markdown),
    )

    # Write structured JSON sidecar for downstream consumers
    json_path = resolved.with_suffix(".json")
    await asyncio.to_thread(
        json_path.write_text, json.dumps(plan.model_dump(), indent=2), encoding="utf-8"
    )
    logger.debug("write_plan: wrote JSON sidecar", path=str(json_path))

    return WritePlanResult(
        path=resolved,
        task_count=len(plan.tasks),
        goal=plan.goal,
    )


def create_write_plan_tool(root_dir: str) -> StructuredTool:
    """Create a LangChain StructuredTool for write_plan.

    This tool is injected into the API driver's tool list so the LLM
    calls it instead of generic write_file for plan generation.

    Args:
        root_dir: Root directory for resolving file paths.

    Returns:
        Configured StructuredTool instance.
    """

    async def _invoke(
        goal: str,
        architecture_summary: str,
        tasks: list[dict[str, Any]],
        file_path: str,
        tech_stack: list[str] | None = None,
    ) -> str:
        tool_input = {
            "goal": goal,
            "architecture_summary": architecture_summary,
            "tech_stack": tech_stack or [],
            "tasks": tasks,
            "file_path": file_path,
        }
        try:
            result = await execute_write_plan(tool_input, root_dir=root_dir)
        except WritePlanValidationError as exc:
            return f"Validation error in write_plan input: {exc.errors}. Please fix and retry."
        return (
            f"Successfully wrote plan with {result.task_count} task(s) to {file_path}. "
            f"Goal: {result.goal}"
        )

    return StructuredTool.from_function(
        coroutine=_invoke,
        name="write_plan",
        description=(
            "Write a structured implementation plan to a markdown file. "
            "Use this tool instead of write_file when creating implementation plans. "
            "Provide structured task data and the tool will render consistent markdown "
            "with proper ### Task N: headers. The tool validates the input and returns "
            "errors if the plan structure is invalid."
        ),
        args_schema=WritePlanInput,
    )
