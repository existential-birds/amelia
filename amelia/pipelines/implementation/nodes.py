"""Implementation pipeline-specific LangGraph node functions.

This module contains node functions specific to the implementation pipeline:
- call_architect_node: Generates implementation plan
- plan_validator_node: Validates and extracts structure from plan
- human_approval_node: Handles human approval of the plan
- next_task_node: Transitions to next task in multi-task execution
"""

import asyncio
from pathlib import Path
from typing import Any

import typer
from langchain_core.runnables.config import RunnableConfig
from loguru import logger

from amelia.agents.architect import Architect, MarkdownPlanOutput
from amelia.core.constants import ToolName, resolve_plan_path
from amelia.core.extraction import extract_structured
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.implementation.utils import (
    _extract_goal_from_plan,
    _extract_key_files_from_plan,
    _looks_like_plan,
    commit_task_changes,
    extract_task_count,
)
from amelia.pipelines.nodes import _save_token_usage
from amelia.pipelines.utils import extract_config_params


async def plan_validator_node(
    state: ImplementationState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Validate and extract structure from architect's plan file.

    Reads the plan file written by the architect and uses an LLM to extract
    structured fields (goal, plan_markdown, key_files) using the MarkdownPlanOutput schema.

    Args:
        state: Current execution state with raw_architect_output.
        config: RunnableConfig with profile in configurable.

    Returns:
        Partial state dict with goal, plan_markdown, plan_path, key_files.

    Raises:
        ValueError: If plan file not found or empty.
    """
    event_bus, workflow_id, profile = extract_config_params(config or {})

    if not state.issue:
        raise ValueError("Issue is required in state for plan validation")

    # Resolve plan path - use working_dir to match call_architect_node
    plan_rel_path = resolve_plan_path(profile.plan_path_pattern, state.issue.id)
    working_dir = Path(profile.working_dir) if profile.working_dir else Path(".")
    plan_path = working_dir / plan_rel_path

    logger.info(
        "Orchestrator: Validating plan structure",
        plan_path=str(plan_path),
        workflow_id=workflow_id,
    )

    # Read plan file - fail fast if not found
    if not plan_path.exists():
        raise ValueError(f"Plan file not found at {plan_path}")

    plan_content = await asyncio.to_thread(plan_path.read_text)
    if not plan_content.strip():
        raise ValueError(f"Plan file is empty at {plan_path}")

    # Extract structured fields using lightweight extraction (no tools needed)
    # The plan already exists - we just need to parse it into structured format
    # Use plan_validator agent config for structured extraction
    agent_config = profile.get_agent_config("plan_validator")
    prompt = f"""Extract the implementation plan structure from the following markdown plan.

<plan>
{plan_content}
</plan>

Return:
- goal: 1-2 sentence summary of what this plan accomplishes
- plan_markdown: The full plan content (preserve as-is)
- key_files: List of files that will be created or modified"""

    try:
        output = await extract_structured(
            prompt=prompt,
            schema=MarkdownPlanOutput,
            model=agent_config.model,
            driver_type=agent_config.driver,
        )
        goal = output.goal
        plan_markdown = output.plan_markdown
        key_files = output.key_files
    except RuntimeError as e:
        # Fallback: extract what we can from the plan content directly
        logger.warning(
            "Structured extraction failed, using fallback",
            error=str(e),
            workflow_id=workflow_id,
        )
        goal = _extract_goal_from_plan(plan_content)
        plan_markdown = plan_content
        key_files = _extract_key_files_from_plan(plan_content)

    # Parse task count from plan markdown
    total_tasks = extract_task_count(plan_content)

    logger.info(
        "Plan validated",
        goal=goal,
        key_files_count=len(key_files),
        total_tasks=total_tasks,
        workflow_id=workflow_id,
    )

    return {
        "goal": goal,
        "plan_markdown": plan_markdown,
        "plan_path": plan_path,
        "key_files": key_files,
        "total_tasks": total_tasks,
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
    issue_id_for_log = state.issue.id if state.issue else "No Issue Provided"
    logger.info(f"Orchestrator: Calling Architect for issue {issue_id_for_log}")

    if state.issue is None:
        raise ValueError("Cannot call Architect: no issue provided in state.")

    # Extract event_bus, workflow_id, and profile from config
    event_bus, workflow_id, profile = extract_config_params(config or {})

    config = config or {}
    configurable = config.get("configurable", {})
    repository = configurable.get("repository")
    prompts = configurable.get("prompts", {})

    agent_config = profile.get_agent_config("architect")
    architect = Architect(agent_config, event_bus=event_bus, prompts=prompts)

    # Ensure the plan directory exists before the architect runs
    plan_rel_path = resolve_plan_path(profile.plan_path_pattern, state.issue.id)
    working_dir = Path(profile.working_dir) if profile.working_dir else Path(".")
    plan_path = working_dir / plan_rel_path
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    logger.debug("Ensured plan directory exists", plan_dir=str(plan_path.parent))

    final_state = state
    async for new_state, event in architect.plan(
        state=state,
        profile=profile,
        workflow_id=workflow_id,
    ):
        final_state = new_state
        if event_bus:
            event_bus.emit(event)

    await _save_token_usage(architect.driver, workflow_id, "architect", repository)

    # Fallback: If plan file doesn't exist, write it from Write tool call content
    # This handles cases where Claude Code's Write tool didn't persist the file
    if not plan_path.exists():
        logger.warning(
            "Plan file not found after architect execution, attempting fallback",
            plan_path=str(plan_path),
            tool_calls_count=len(final_state.tool_calls),
        )

        # DEBUG: Log all tool calls for diagnosis
        logger.debug(
            "DEBUG: All tool calls from architect",
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

        # Look for Write tool call with plan content
        # Log all tool names explicitly for debugging
        tool_names = [tc.tool_name for tc in final_state.tool_calls]
        logger.debug(
            "Looking for write_file in tool calls",
            tool_names=tool_names,
        )
        for tc in final_state.tool_calls:
            input_keys = list(tc.tool_input.keys()) if tc.tool_input else []
            is_match = (
                tc.tool_name == ToolName.WRITE_FILE
                and tc.tool_input
                and "content" in tc.tool_input
            )
            logger.debug(
                "Checking tool call for write_file",
                tool_name=tc.tool_name,
                input_keys=input_keys,
                is_write_file=is_match,
            )
            if is_match:
                plan_content = tc.tool_input.get("content", "")
                if plan_content:
                    await asyncio.to_thread(plan_path.write_text, plan_content)
                    logger.info(
                        "Wrote plan file from Write tool call content",
                        plan_path=str(plan_path),
                        content_length=len(plan_content),
                    )
                    break
        else:
            # No Write tool call found - try to salvage plan from raw output
            # Some models output the plan as text instead of using the write tool
            raw_output = final_state.raw_architect_output or ""
            if raw_output and _looks_like_plan(raw_output):
                await asyncio.to_thread(plan_path.write_text, raw_output)
                logger.warning(
                    "Wrote plan file from raw output (model didn't use write tool)",
                    plan_path=str(plan_path),
                    content_length=len(raw_output),
                )
            else:
                logger.error(
                    "No Write tool call found and raw output doesn't look like a plan",
                    plan_path=str(plan_path),
                    tool_calls=[tc.tool_name for tc in final_state.tool_calls],
                    tool_calls_count=len(final_state.tool_calls),
                    raw_output_length=len(raw_output) if raw_output else 0,
                )

    logger.info(
        "Agent action completed",
        agent="architect",
        action="generated_plan",
        details={
            "raw_output_length": len(final_state.raw_architect_output) if final_state.raw_architect_output else 0,
            "tool_calls_count": len(final_state.tool_calls),
        },
    )

    return {
        "raw_architect_output": final_state.raw_architect_output,
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
    config = config or {}
    execution_mode = config.get("configurable", {}).get("execution_mode", "cli")

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
