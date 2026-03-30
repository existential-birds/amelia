"""Implementation pipeline-specific LangGraph node functions.

This module contains node functions specific to the implementation pipeline:
- call_architect_node: Generates implementation plan
- plan_validator_node: Validates and extracts structure from plan
- human_approval_node: Handles human approval of the plan
- next_task_node: Transitions to next task in multi-task execution
"""

import asyncio
import json as _json
from pathlib import Path
from typing import Any

import typer
from langchain_core.runnables.config import RunnableConfig
from loguru import logger
from pydantic import ValidationError

from amelia.agents.architect import Architect
from amelia.core.constants import ToolName, resolve_plan_path
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.implementation.utils import (
    _extract_goal_from_plan,
    _extract_key_files_from_plan,
    _looks_like_plan,
    commit_task_changes,
    extract_task_count,
    validate_plan_structure,
)
from amelia.pipelines.nodes import _save_token_usage
from amelia.pipelines.utils import extract_node_config
from amelia.tools.write_plan import execute_write_plan
from amelia.tools.write_plan_schema import WritePlanInput


async def _resolve_plan_from_tool_calls(
    tool_calls: list[Any],
    plan_path: Path,
    working_dir: Path,
    raw_output: str | None = None,
) -> bool:
    """Try to write the plan file from tool calls or raw output.

    Iterates tool calls looking for write_plan (preferred) or write_file.
    Falls back to raw output if no tool call succeeds.

    Args:
        tool_calls: List of ToolCall objects from the architect run.
        plan_path: Target path for the plan file.
        working_dir: Repository root for resolving relative paths.
        raw_output: Raw text output from the architect (last-resort fallback).

    Returns:
        True if the plan was written successfully, False otherwise.
    """
    tool_names = [tc.tool_name for tc in tool_calls]
    logger.debug(
        "Looking for write_plan/write_file in tool calls",
        tool_names=tool_names,
    )
    # Track the last successful write so we replay the final version, not the first draft.
    last_successful_tc: Any | None = None
    last_successful_kind: str | None = None  # "write_plan" or "write_file"

    for tc in tool_calls:
        # Handle write_plan tool calls (structured format — preferred)
        if tc.tool_name == ToolName.WRITE_PLAN and tc.tool_input:
            # Override LLM-provided file_path with the authoritative plan_path
            overridden_input = {**tc.tool_input, "file_path": str(plan_path)}
            logger.info(
                "Found write_plan tool call, rendering and writing",
                plan_path=str(plan_path),
                original_file_path=tc.tool_input.get("file_path"),
            )
            try:
                result = await execute_write_plan(
                    overridden_input,
                    root_dir=str(working_dir),
                )
            except Exception:
                logger.exception(
                    "write_plan execution raised, skipping this tool call",
                    plan_path=str(plan_path),
                )
                continue
            if plan_path.exists():
                last_successful_tc = tc
                last_successful_kind = "write_plan"
            else:
                logger.warning(
                    "write_plan did not produce a file, trying next tool call",
                    result=result,
                )
            continue

        # Handle legacy write_file tool calls
        is_write = (
            tc.tool_name == ToolName.WRITE_FILE
            and tc.tool_input
            and "content" in tc.tool_input
        )
        if is_write:
            plan_content = tc.tool_input.get("content", "")
            if plan_content:
                await asyncio.to_thread(plan_path.parent.mkdir, parents=True, exist_ok=True)
                await asyncio.to_thread(plan_path.write_text, plan_content, encoding="utf-8")
                logger.info(
                    "Wrote plan file from Write tool call content (legacy fallback)",
                    plan_path=str(plan_path),
                    content_length=len(plan_content),
                )
                last_successful_tc = tc
                last_successful_kind = "write_file"

    if last_successful_tc is not None:
        # Re-apply the *last* successful write so the final version wins.
        if last_successful_kind == "write_plan":
            overridden_input = {**last_successful_tc.tool_input, "file_path": str(plan_path)}
            try:
                await execute_write_plan(overridden_input, root_dir=str(working_dir))
            except Exception:
                logger.exception("Failed to re-apply final write_plan call")
        elif last_successful_kind == "write_file":
            content = last_successful_tc.tool_input.get("content", "")
            if content:
                await asyncio.to_thread(plan_path.parent.mkdir, parents=True, exist_ok=True)
                await asyncio.to_thread(plan_path.write_text, content, encoding="utf-8")
        if plan_path.exists():
            return True

    # No tool call succeeded; try salvaging from raw output
    # Some models output the plan as text instead of using the write tool
    raw = raw_output or ""
    if raw and _looks_like_plan(raw):
        await asyncio.to_thread(plan_path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(plan_path.write_text, raw, encoding="utf-8")
        logger.warning(
            "FALLBACK: Wrote plan from raw output - may be incomplete or malformed (model didn't use write tool)",
            plan_path=str(plan_path),
            content_length=len(raw),
            tool_sequence=tool_names[-5:],
        )
        return True
    logger.error(
        "No Write tool call found and raw output doesn't look like a plan",
        plan_path=str(plan_path),
        tool_calls=[tc.tool_name for tc in tool_calls],
        tool_calls_count=len(tool_calls),
        raw_output_length=len(raw),
    )
    return False


async def plan_validator_node(
    state: ImplementationState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Validate and extract structure from plan file using regex.

    Reads the plan file and extracts structured fields (goal, key_files)
    using pattern matching. Runs structural validation to check for
    required headers and minimum content.

    Args:
        state: Current execution state.
        config: RunnableConfig with profile in configurable.

    Returns:
        Partial state dict with goal, plan_markdown, plan_path, key_files,
        total_tasks, plan_validation_result, plan_revision_count.

    Raises:
        ValueError: If plan file not found or empty.
    """
    nc = extract_node_config(config)

    if not state.issue:
        raise ValueError("Issue is required in state for plan validation")

    # Resolve plan path - use state.plan_path for external plans, otherwise construct from pattern
    if state.external_plan and state.plan_path is not None:
        plan_path = state.plan_path
    else:
        plan_rel_path = resolve_plan_path(nc.profile.plan_path_pattern, state.issue.id)
        working_dir = Path(nc.profile.repo_root)
        plan_path = working_dir / plan_rel_path

    logger.info(
        "Orchestrator: Validating plan structure",
        plan_path=str(plan_path),
        workflow_id=nc.workflow_id,
    )

    # Read plan file - fail fast if not found
    if not plan_path.exists():
        raise ValueError(f"Plan file not found at {plan_path}")

    plan_content = await asyncio.to_thread(plan_path.read_text)
    if not plan_content.strip():
        raise ValueError(f"Plan file is empty at {plan_path}")

    # Check for structured plan data (JSON sidecar from write_plan tool)
    json_sidecar = plan_path.with_suffix(".json")
    parsed_sidecar: WritePlanInput | None = None
    if json_sidecar.exists():
        try:
            raw_json = await asyncio.to_thread(json_sidecar.read_text)
            parsed_sidecar = WritePlanInput.model_validate_json(raw_json)
            logger.info(
                "Found structured plan data from write_plan tool",
                json_path=str(json_sidecar),
                task_count=len(parsed_sidecar.tasks),
            )
        except ValidationError as exc:
            logger.warning(
                "Plan JSON sidecar failed schema validation, falling back to regex",
                json_path=str(json_sidecar),
                error=str(exc),
            )
        except (_json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read/parse plan JSON sidecar", error=str(exc))

    # Extract fields — prefer validated structured data, fall back to regex
    if parsed_sidecar is not None and parsed_sidecar.tasks:
        goal = parsed_sidecar.goal or _extract_goal_from_plan(plan_content)
        total_tasks = len(parsed_sidecar.tasks)
        seen: set[str] = set()
        key_files_from_structured: list[str] = []
        for task in parsed_sidecar.tasks:
            for f in (*task.files_to_create, *task.files_to_modify):
                if f not in seen:
                    seen.add(f)
                    key_files_from_structured.append(f)
        key_files = key_files_from_structured
    else:
        goal = _extract_goal_from_plan(plan_content)
        key_files = _extract_key_files_from_plan(plan_content)
        total_tasks = extract_task_count(plan_content)

    # Run structural validation
    validation_result = validate_plan_structure(goal, plan_content)

    revision_count = state.plan_revision_count
    if not validation_result.valid:
        revision_count += 1
        logger.warning(
            "Plan structural validation failed",
            issues=validation_result.issues,
            severity=validation_result.severity.value,
            revision_count=revision_count,
            workflow_id=nc.workflow_id,
        )

    logger.info(
        "Plan validated",
        goal=goal,
        key_files_count=len(key_files),
        total_tasks=total_tasks,
        workflow_id=nc.workflow_id,
    )

    return {
        "goal": goal,
        "plan_markdown": plan_content,
        "plan_path": plan_path,
        "key_files": key_files,
        "total_tasks": total_tasks,
        "plan_validation_result": validation_result,
        "plan_revision_count": revision_count,
        "plan_structured": parsed_sidecar,
    }


async def call_architect_node(
    state: ImplementationState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Architect agent to generate an implementation plan.

    Consumes the Architect's async generator, streaming events and collecting
    the final state. The plan_validator_node handles extracting structured
    fields (goal, plan_markdown, key_files) from the written plan file.

    Args:
        state: Current execution state containing the issue and profile.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with raw_architect_output, tool_calls, and tool_results.

    Raises:
        ValueError: If no issue is provided in the state.
    """
    logger.info(
        "Orchestrator: Calling Architect",
        issue_id=state.issue.id if state.issue else "No Issue Provided",
    )

    if state.issue is None:
        raise ValueError("Cannot call Architect: no issue provided in state.")

    # Extract all config params in one call
    nc = extract_node_config(config)

    agent_config = nc.profile.get_agent_config("architect")
    architect = Architect(agent_config, prompts=nc.prompts, sandbox_provider=nc.sandbox_provider)

    # Ensure the plan directory exists before the architect runs
    plan_rel_path = resolve_plan_path(nc.profile.plan_path_pattern, state.issue.id)
    working_dir = Path(nc.profile.repo_root)
    plan_path = working_dir / plan_rel_path
    await asyncio.to_thread(plan_path.parent.mkdir, parents=True, exist_ok=True)
    logger.debug("Ensured plan directory exists", plan_dir=str(plan_path.parent))

    final_state = state
    async for new_state, event in architect.plan(
        state=state,
        profile=nc.profile,
        workflow_id=nc.workflow_id,
    ):
        final_state = new_state
        if nc.event_bus:
            nc.event_bus.emit(event)

    await _save_token_usage(architect.driver, nc.workflow_id, "architect", nc.repository)

    # Fallback: If plan file doesn't exist, write it from Write tool call content
    # This handles cases where Claude Code's Write tool didn't persist the file
    plan_written = plan_path.exists()
    if not plan_written:
        logger.warning(
            "Plan file not found after architect execution, attempting fallback",
            plan_path=str(plan_path),
            tool_calls_count=len(final_state.tool_calls),
        )

        # Log all tool calls for diagnosis
        logger.debug(
            "All tool calls from architect",
            tool_calls_detail=[
                {
                    "tool_name": tc.tool_name,
                    "tool_name_type": type(tc.tool_name).__name__,
                    "input_keys": list(tc.tool_input.keys()) if tc.tool_input else [],
                    "has_content": "content" in tc.tool_input if tc.tool_input else False,
                    "has_file_path": "file_path" in tc.tool_input if tc.tool_input else False,
                }
                for tc in final_state.tool_calls
            ],
            expected_write_file=ToolName.WRITE_FILE,
            expected_write_file_value=str(ToolName.WRITE_FILE),
        )

        plan_written = await _resolve_plan_from_tool_calls(
            tool_calls=final_state.tool_calls,
            plan_path=plan_path,
            working_dir=working_dir,
            raw_output=final_state.raw_architect_output,
        )

    if plan_written:
        logger.info(
            "Agent action completed",
            agent="architect",
            action="generated_plan",
            details={
                "raw_output_length": len(final_state.raw_architect_output) if final_state.raw_architect_output else 0,
                "tool_calls_count": len(final_state.tool_calls),
            },
        )
    else:
        logger.warning(
            "Agent action completed with failure",
            agent="architect",
            action="generated_plan",
            success=False,
            details={
                "raw_output_length": len(final_state.raw_architect_output) if final_state.raw_architect_output else 0,
                "tool_calls_count": len(final_state.tool_calls),
            },
        )

    return {
        "raw_architect_output": final_state.raw_architect_output,
        "architect_error": final_state.architect_error,
        "tool_calls": list(final_state.tool_calls),
        "tool_results": list(final_state.tool_results),
    }


async def human_approval_node(
    state: ImplementationState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Node to prompt for human approval before proceeding.

    Behavior depends on execution mode:
    - CLI mode: Blocking prompt via typer.confirm
    - Server mode: Returns empty dict (interrupt mechanism handles pause)

    Args:
        state: Current execution state containing the goal and plan to be reviewed.
        config: Optional RunnableConfig with execution_mode in configurable.

    Returns:
        Partial state dict with approval status, or empty dict for server mode.
    """
    resolved_config = config or {}
    execution_mode = resolved_config.get("configurable", {}).get("execution_mode", "cli")

    if execution_mode == "server":
        # Server mode: approval comes from resumed state after interrupt
        # If human_approved is already set (from resume), use it
        # Otherwise, just return empty dict - the interrupt mechanism will pause here
        return {}

    # CLI mode: blocking prompt
    typer.secho("\n--- HUMAN APPROVAL REQUIRED ---", fg=typer.colors.BRIGHT_YELLOW)
    typer.echo("Review the generated plan before proceeding.")
    if state.goal:
        typer.echo(f"\nGoal: {state.goal}")
    if state.plan_path:
        typer.echo(f"\nPlan saved to: {state.plan_path}")

    approved = typer.confirm("Do you approve this plan to proceed with development?", default=True)
    comment = typer.prompt("Add an optional comment for the audit log (press Enter to skip)", default="")

    # Log the approval decision
    logger.info(
        "Human approval received",
        approved=approved,
        comment=comment,
    )

    return {
        "human_approved": approved,
        "human_feedback": comment if comment else None,
    }


async def next_task_node(
    state: ImplementationState, config: RunnableConfig
) -> dict[str, Any]:
    """Transition to next task: commit changes, increment index, reset iteration.

    Args:
        state: Current execution state with task tracking.
        config: Runnable config.

    Returns:
        State update with incremented task index, reset iteration, cleared session.

    Raises:
        RuntimeError: If commit fails, halting the workflow to preserve
            one-commit-per-task semantics per issue #188.
    """
    completed_task = state.current_task_index + 1
    next_task = state.current_task_index + 2

    logger.info(
        "NEXT_TASK_NODE: Transitioning to next task",
        completed=completed_task,
        next=next_task,
        total_tasks=state.total_tasks,
    )

    # Commit current task changes - halt on failure to preserve clean commit history
    commit_success = await commit_task_changes(state, config)
    if not commit_success:
        logger.error(
            "Cannot proceed to next task: commit failed",
            completed_task=completed_task,
        )
        raise RuntimeError(
            f"Failed to commit changes for task {completed_task}. "
            "Halting workflow to preserve one-commit-per-task semantics."
        )

    return {
        "current_task_index": state.current_task_index + 1,
        "task_review_iteration": 0,
        "driver_session_id": None,  # Fresh session for next task
        "total_tasks": state.total_tasks,  # Pass through for TASK_COMPLETED event
    }
