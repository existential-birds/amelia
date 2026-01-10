"""LangGraph state machine orchestrator for coordinating AI agents.

Implements the core agentic workflow: Issue -> Architect (analyze) -> Human Approval ->
Developer (execute agentically) <-> Reviewer (review) -> Done. Provides node functions for
the state machine and the create_orchestrator_graph() factory.
"""
import asyncio
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import typer
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from loguru import logger

from amelia.agents.architect import Architect, MarkdownPlanOutput
from amelia.agents.developer import Developer
from amelia.agents.evaluator import Evaluator
from amelia.agents.reviewer import Reviewer
from amelia.core.constants import ToolName, resolve_plan_path
from amelia.core.state import ExecutionState, rebuild_execution_state
from amelia.core.types import Profile
from amelia.drivers.factory import DriverFactory
from amelia.server.models.tokens import TokenUsage


# Resolve forward references in ExecutionState. Must be done after importing
# Reviewer and Evaluator since they define StructuredReviewResult and EvaluationResult.
rebuild_execution_state()


if TYPE_CHECKING:
    from amelia.server.database.repository import WorkflowRepository
    from amelia.server.events.bus import EventBus


def extract_task_count(plan_markdown: str) -> int | None:
    """Extract task count from plan markdown by counting ### Task N: patterns.

    Supports both simple numbering (### Task 1:) and hierarchical numbering
    (### Task 1.1:) formats.

    Args:
        plan_markdown: The markdown content of the plan.

    Returns:
        Number of tasks found, or None if no task patterns detected.
    """
    pattern = r"^### Task \d+(\.\d+)?:"
    matches = re.findall(pattern, plan_markdown, re.MULTILINE)
    return len(matches) if matches else None


def _extract_config_params(
    config: RunnableConfig | None,
) -> tuple["EventBus | None", str, Profile]:
    """Extract event_bus, workflow_id, and profile from config.

    Extracts values from config.configurable dictionary. workflow_id is required.

    Args:
        config: Optional RunnableConfig with configurable parameters.

    Returns:
        Tuple of (event_bus, workflow_id, profile).

    Raises:
        ValueError: If workflow_id (thread_id) or profile is not provided.
    """
    config = config or {}
    configurable = config.get("configurable", {})
    event_bus = configurable.get("event_bus")
    workflow_id = configurable.get("thread_id")
    profile = configurable.get("profile")

    if not workflow_id:
        raise ValueError("workflow_id (thread_id) is required in config.configurable")
    if not profile:
        raise ValueError("profile is required in config.configurable")

    return event_bus, workflow_id, profile


async def _save_token_usage(
    driver: Any,
    workflow_id: str,
    agent: str,
    repository: "WorkflowRepository | None",
) -> None:
    """Extract token usage from driver and save to repository.

    This is a best-effort operation - failures are logged but don't fail the workflow.
    Uses the driver-agnostic get_usage() method when available.

    Args:
        driver: The driver that was used for execution.
        workflow_id: Current workflow ID.
        agent: Agent name (architect, developer, reviewer).
        repository: Repository to save usage to (may be None in CLI mode).
    """
    if repository is None:
        return

    # Get usage via the driver-agnostic get_usage() method
    driver_usage = driver.get_usage() if hasattr(driver, "get_usage") else None
    if driver_usage is None:
        return

    try:
        usage = TokenUsage(
            workflow_id=workflow_id,
            agent=agent,
            model=driver_usage.model or getattr(driver, "model", "unknown"),
            input_tokens=driver_usage.input_tokens or 0,
            output_tokens=driver_usage.output_tokens or 0,
            cache_read_tokens=driver_usage.cache_read_tokens or 0,
            cache_creation_tokens=driver_usage.cache_creation_tokens or 0,
            cost_usd=driver_usage.cost_usd or 0.0,
            duration_ms=driver_usage.duration_ms or 0,
            num_turns=driver_usage.num_turns or 1,
            timestamp=datetime.now(UTC),
        )
        await repository.save_token_usage(usage)
        logger.debug(
            "Token usage saved",
            agent=agent,
            workflow_id=workflow_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd,
        )
    except Exception:
        # Best-effort - don't fail workflow on token tracking errors
        logger.exception(
            "Failed to save token usage",
            agent=agent,
            workflow_id=workflow_id,
        )


async def plan_validator_node(
    state: ExecutionState,
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
    event_bus, workflow_id, profile = _extract_config_params(config)

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

    # Emit start event to UI (trace level event not persisted)
    # Validator doesn't use event_bus directly for trace events

    # Read plan file - fail fast if not found
    if not plan_path.exists():
        raise ValueError(f"Plan file not found at {plan_path}")

    plan_content = await asyncio.to_thread(plan_path.read_text)
    if not plan_content.strip():
        raise ValueError(f"Plan file is empty at {plan_path}")

    # Get validator driver
    model = profile.validator_model or profile.model
    driver = DriverFactory.get_driver(profile.driver, model=model)

    # Extract structured fields using LLM
    prompt = f"""Extract the implementation plan structure from the following markdown plan.

<plan>
{plan_content}
</plan>

Return:
- goal: 1-2 sentence summary of what this plan accomplishes
- plan_markdown: The full plan content (preserve as-is)
- key_files: List of files that will be created or modified"""

    output, _session_id = await driver.generate(
        prompt=prompt,
        schema=MarkdownPlanOutput,
    )

    # Parse task count from plan markdown
    total_tasks = extract_task_count(plan_content)

    logger.info(
        "Plan validated",
        goal=output.goal,
        key_files_count=len(output.key_files),
        total_tasks=total_tasks,
        workflow_id=workflow_id,
    )

    return {
        "goal": output.goal,
        "plan_markdown": output.plan_markdown,
        "plan_path": plan_path,
        "key_files": output.key_files,
        "total_tasks": total_tasks,
    }


async def call_architect_node(
    state: ExecutionState,
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
    event_bus, workflow_id, profile = _extract_config_params(config)

    config = config or {}
    configurable = config.get("configurable", {})
    repository = configurable.get("repository")
    prompts = configurable.get("prompts", {})

    driver = DriverFactory.get_driver(profile.driver, model=profile.model)
    architect = Architect(driver, event_bus=event_bus, prompts=prompts)

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

    await _save_token_usage(driver, workflow_id, "architect", repository)

    # Fallback: If plan file doesn't exist, write it from Write tool call content
    # This handles cases where Claude Code's Write tool didn't persist the file
    if not plan_path.exists():
        logger.warning(
            "Plan file not found after architect execution, attempting fallback",
            plan_path=str(plan_path),
            tool_calls_count=len(final_state.tool_calls),
        )
        # Look for Write tool call with plan content
        for tc in final_state.tool_calls:
            if tc.tool_name == ToolName.WRITE_FILE and "content" in tc.tool_input:
                plan_content = tc.tool_input.get("content", "")
                if plan_content:
                    plan_path.write_text(plan_content)
                    logger.info(
                        "Wrote plan file from Write tool call content",
                        plan_path=str(plan_path),
                        content_length=len(plan_content),
                    )
                    break
        else:
            # No Write tool call found - this is a critical error
            logger.error(
                "No Write tool call found for plan file",
                plan_path=str(plan_path),
                tool_calls=[tc.tool_name for tc in final_state.tool_calls],
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
    state: ExecutionState,
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

    return {"human_approved": approved}


async def get_code_changes_for_review(state: ExecutionState, profile: Profile) -> str:
    """Retrieve code changes for review from state or git diff.

    Priority order:
    1. state.code_changes_for_review (explicit changes from driver)
    2. git diff against state.base_commit (workflow start commit)
    3. git diff against merge-base with main/master (feature branch changes)
    4. git diff HEAD (uncommitted changes only)

    Args:
        state: Current execution state that may contain code changes.
        profile: Profile containing the working directory for git operations.

    Returns:
        Code changes as a string, either from state or from git diff.
    """
    logger.debug(
        "get_code_changes_for_review called",
        base_commit=state.base_commit,
        has_code_changes_for_review=bool(state.code_changes_for_review),
        working_dir=profile.working_dir,
    )

    if state.code_changes_for_review:
        return state.code_changes_for_review

    cwd = profile.working_dir

    async def git_diff(ref: str) -> str | None:
        """Run git diff against a reference, return output or None if empty/failed."""
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", ref,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0 and stdout.decode().strip():
            return stdout.decode()
        return None

    try:
        # Priority 1: Diff against base_commit if available (workflow start)
        if state.base_commit:
            diff = await git_diff(state.base_commit)
            if diff:
                logger.debug("Using diff against base_commit", base_commit=state.base_commit[:8])
                return diff
            logger.debug(
                "base_commit diff was empty",
                base_commit=state.base_commit[:8] if state.base_commit else None,
            )
        else:
            logger.debug("No base_commit available in state")

        # Priority 2: Find merge-base with main/master for feature branch changes
        for base_branch in ["main", "master"]:
            proc = await asyncio.create_subprocess_exec(
                "git", "merge-base", base_branch, "HEAD",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                merge_base = stdout.decode().strip()
                diff = await git_diff(merge_base)
                if diff:
                    logger.debug("Using diff against merge-base", merge_base=merge_base[:8])
                    return diff
                logger.debug(
                    "merge-base diff was empty",
                    base_branch=base_branch,
                    merge_base=merge_base[:8] if merge_base else None,
                )
                break  # Found merge-base but no diff, continue to fallback
            else:
                logger.debug(
                    "merge-base lookup failed",
                    base_branch=base_branch,
                    stderr=stderr.decode().strip(),
                )

        # Priority 3: Uncommitted changes (git diff HEAD)
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        head_stdout, head_stderr = await proc.communicate()
        diff_output = head_stdout.decode()
        head_returncode = proc.returncode
        logger.debug(
            "git diff HEAD result",
            returncode=head_returncode,
            diff_length=len(diff_output),
            diff_empty=not diff_output.strip(),
        )
        if head_returncode == 0 and diff_output.strip():
            return diff_output

        # Priority 4: Recent commits (for when developer committed changes)
        # Try to find commits that aren't pushed yet to remote tracking branch
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-list", "--count", "@{upstream}..HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        count_stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            unpushed_count = int(count_stdout.decode().strip() or "0")
            if unpushed_count > 0:
                # Diff against HEAD~N where N is unpushed commits
                proc = await asyncio.create_subprocess_exec(
                    "git", "diff", f"HEAD~{unpushed_count}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                )
                stdout, _ = await proc.communicate()
                if proc.returncode == 0 and stdout.decode().strip():
                    logger.debug(
                        "Using diff of unpushed commits",
                        unpushed_count=unpushed_count,
                    )
                    return stdout.decode()
        else:
            # No upstream tracking branch - try to diff against last commit
            # This handles new branches without upstream
            proc = await asyncio.create_subprocess_exec(
                "git", "diff", "HEAD~1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout.decode().strip():
                logger.debug("Using diff of last commit (no upstream)")
                return stdout.decode()

        # Final fallback: return empty or whatever git diff HEAD gave us
        if head_returncode == 0:
            return diff_output
        else:
            return f"Error getting git diff: {head_stderr.decode()}"
    except (FileNotFoundError, OSError) as e:
        return f"Failed to execute git diff: {str(e)}"


async def call_developer_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Developer agent to execute agentically.

    Uses the new agentic execution model where the Developer autonomously
    decides what tools to use rather than following a step-by-step plan.

    For task-based execution (when total_tasks is set), this node:
    - Clears driver_session_id for fresh context per task
    - Injects task-scoped prompt pointing to the current task in the plan

    Args:
        state: Current execution state containing the goal.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with tool_calls, tool_results, and status.
    """
    logger.info("Orchestrator: Calling Developer to execute agentically.")
    logger.debug(
        "Developer node state",
        base_commit=state.base_commit,
        goal_length=len(state.goal) if state.goal else 0,
    )

    if not state.goal:
        raise ValueError("Developer node has no goal. The architect should have generated a goal first.")

    # Extract event_bus, workflow_id, and profile from config
    event_bus, workflow_id, profile = _extract_config_params(config)

    # Task-based execution: clear session and inject task-scoped prompt
    if state.total_tasks is not None:
        task_number = state.current_task_index + 1  # 1-indexed for display
        task_prompt = f"Execute Task {task_number} from plan at {state.plan_path}"
        logger.info(
            "Starting task execution",
            task=task_number,
            total_tasks=state.total_tasks,
            fresh_session=True,
        )
        state = state.model_copy(update={
            "driver_session_id": None,  # Fresh session for each task
            "goal": f"{state.goal}\n\n**Current Task:** {task_prompt}",
        })

    config = config or {}
    repository = config.get("configurable", {}).get("repository")

    driver = DriverFactory.get_driver(profile.driver, model=profile.model)
    developer = Developer(driver)

    final_state = state
    async for new_state, event in developer.run(state, profile):
        final_state = new_state
        # Stream events are emitted via event_bus if provided
        if event_bus:
            event_bus.emit(event)

    await _save_token_usage(driver, workflow_id, "developer", repository)

    logger.info(
        "Agent action completed",
        agent="developer",
        action="agentic_execution",
        details={
            "tool_calls_count": len(final_state.tool_calls),
            "agentic_status": final_state.agentic_status,
        },
    )

    return {
        "tool_calls": list(final_state.tool_calls),
        "tool_results": list(final_state.tool_results),
        "agentic_status": final_state.agentic_status,
        "final_response": final_state.final_response,
        "error": final_state.error,
        "driver_session_id": final_state.driver_session_id,
    }


async def call_reviewer_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Reviewer agent to review code changes.

    Uses agentic review when a base_commit is available, which allows the
    reviewer agent to fetch the diff using git tools. This avoids the
    "Argument list too long" error that can occur with large diffs.

    Args:
        state: Current execution state containing issue and goal information.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with review results.
    """
    logger.info(f"Orchestrator: Calling Reviewer for issue {state.issue.id if state.issue else 'N/A'}")
    logger.debug(
        "Reviewer node state",
        base_commit=state.base_commit,
        has_code_changes_for_review=bool(state.code_changes_for_review),
    )

    # Extract event_bus, workflow_id, and profile from config
    event_bus, workflow_id, profile = _extract_config_params(config)

    config = config or {}
    configurable = config.get("configurable", {})
    repository = configurable.get("repository")
    prompts = configurable.get("prompts", {})

    driver = DriverFactory.get_driver(profile.driver, model=profile.model)
    # Use "task_reviewer" only for non-final tasks in task-based execution
    is_non_final_task = state.total_tasks is not None and state.current_task_index + 1 < state.total_tasks
    agent_name = "task_reviewer" if is_non_final_task else "reviewer"
    reviewer = Reviewer(driver, event_bus=event_bus, prompts=prompts, agent_name=agent_name)

    if state.base_commit:
        logger.info(
            "Using agentic review with base_commit",
            agent=agent_name,
            base_commit=state.base_commit,
        )
        review_result, new_session_id = await reviewer.agentic_review(
            state, state.base_commit, profile, workflow_id=workflow_id
        )
    else:
        code_changes = await get_code_changes_for_review(state, profile)
        review_result, new_session_id = await reviewer.review(
            state, code_changes, profile, workflow_id=workflow_id
        )

    await _save_token_usage(driver, workflow_id, agent_name, repository)

    next_iteration = state.review_iteration + 1
    logger.info(
        "Agent action completed",
        agent=agent_name,
        action="review_completed",
        details={
            "severity": review_result.severity,
            "approved": review_result.approved,
            "issue_count": len(review_result.comments),
            "review_iteration": next_iteration,
        },
    )

    # Build return dict
    result_dict = {
        "last_review": review_result,
        "driver_session_id": new_session_id,
        "review_iteration": next_iteration,
    }

    # Increment task review iteration for task-based execution
    if state.total_tasks is not None:
        result_dict["task_review_iteration"] = state.task_review_iteration + 1

    return result_dict


async def call_evaluation_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Node that evaluates review feedback.

    Calls the Evaluator agent to process review results and
    apply the decision matrix for each item.

    Args:
        state: Current execution state containing the review feedback.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with evaluation_result, approved_items, and driver_session_id.
    """
    event_bus, workflow_id, profile = _extract_config_params(config)

    config = config or {}
    configurable = config.get("configurable", {})
    prompts = configurable.get("prompts", {})

    driver = DriverFactory.get_driver(profile.driver, model=profile.model)
    evaluator = Evaluator(driver=driver, event_bus=event_bus, prompts=prompts)

    evaluation_result, new_session_id = await evaluator.evaluate(
        state, profile, workflow_id=workflow_id
    )

    approved_items: list[int] = []
    if state.auto_approve:
        approved_items = [item.number for item in evaluation_result.items_to_implement]

    logger.info(
        "Agent action completed",
        agent="evaluator",
        action="evaluation_completed",
        details={
            "items_to_implement": len(evaluation_result.items_to_implement),
            "items_rejected": len(evaluation_result.items_rejected),
            "items_deferred": len(evaluation_result.items_deferred),
            "auto_approved_count": len(approved_items),
        },
    )

    return {
        "evaluation_result": evaluation_result,
        "approved_items": approved_items,
        "driver_session_id": new_session_id,
    }


async def review_approval_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Node for human approval of which review items to fix.

    In server mode, this interrupts for human input.
    In CLI mode, this prompts interactively.

    Args:
        state: Current execution state containing the evaluation result.
        config: Optional RunnableConfig with execution_mode in configurable.

    Returns:
        Partial state dict with approved_items (CLI mode) or empty dict (server mode).
    """
    config = config or {}
    execution_mode = config.get("configurable", {}).get("execution_mode", "cli")

    if execution_mode == "server":
        return {}

    # CLI mode: prompt user (this would use typer.confirm or similar)
    # For now, auto-approve all items marked for implementation
    return {}


def route_approval(state: ExecutionState) -> Literal["approve", "reject"]:
    """Route based on human approval status.

    Args:
        state: Current execution state containing human_approved flag.

    Returns:
        'approve' if approved (continue to developer).
        'reject' if not approved.
    """
    return "approve" if state.human_approved else "reject"


def route_after_review(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> Literal["developer", "__end__"]:
    """Route after review based on approval and iteration count.

    Args:
        state: Current execution state with last_review and review_iteration.
        config: Optional RunnableConfig with profile in configurable.

    Returns:
        "developer" if review rejected and under max iterations,
        "__end__" if approved or max iterations reached.
    """
    logger.debug(
        "route_after_review decision",
        has_last_review=state.last_review is not None,
        approved=state.last_review.approved if state.last_review else None,
        review_iteration=state.review_iteration,
    )
    if state.last_review and state.last_review.approved:
        return "__end__"

    _, _, profile = _extract_config_params(config)
    max_iterations = profile.max_review_iterations

    if state.review_iteration >= max_iterations:
        logger.warning(
            "Max review iterations reached, terminating loop",
            max_iterations=max_iterations,
        )
        return "__end__"

    return "developer"


async def next_task_node(
    state: ExecutionState, config: RunnableConfig
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
        "Transitioning to next task",
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
    }


async def commit_task_changes(state: ExecutionState, config: RunnableConfig) -> bool:
    """Commit changes for completed task.

    Args:
        state: Current execution state.
        config: Runnable config with profile.

    Returns:
        True if commit succeeded or no changes to commit, False if commit failed.
    """
    profile: Profile | None = config.get("configurable", {}).get("profile")
    if not profile:
        raise ValueError("profile is required in config.configurable")
    working_dir = Path(profile.working_dir) if profile.working_dir else Path.cwd()

    task_number = state.current_task_index + 1

    # Disable git prompts to prevent hangs in headless/server contexts
    git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    timeout_seconds = 60

    # Stage all changes
    proc = await asyncio.create_subprocess_exec(
        "git", "add", "-A",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=working_dir,
        env=git_env,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        logger.warning("Timeout staging changes for task commit", task=task_number)
        proc.kill()
        return False
    if proc.returncode != 0:
        logger.warning(
            "Failed to stage changes for task commit",
            error=stderr.decode(),
        )
        return False

    # Check if there are staged changes
    proc = await asyncio.create_subprocess_exec(
        "git", "diff", "--cached", "--quiet",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=working_dir,
        env=git_env,
    )
    try:
        await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        logger.warning("Timeout checking staged changes for task", task=task_number)
        proc.kill()
        return False
    if proc.returncode == 0:
        # Exit code 0 means no changes (diff is quiet/empty)
        logger.info("No changes to commit for task", task=task_number)
        return True
    if proc.returncode != 1:
        # Exit code 1 means changes exist; any other code is an error
        logger.warning(
            "Failed to check staged diff for task commit",
            returncode=proc.returncode,
            task=task_number,
        )
        return False

    # Commit with task reference
    issue_key = state.issue.id if state.issue else "unknown"
    commit_msg = f"feat({issue_key}): complete task {task_number}"

    proc = await asyncio.create_subprocess_exec(
        "git", "commit", "-m", commit_msg,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=working_dir,
        env=git_env,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        logger.warning("Timeout committing task changes", task=task_number)
        proc.kill()
        return False
    if proc.returncode == 0:
        logger.info("Committed task changes", task=task_number, message=commit_msg)
        return True
    else:
        logger.warning("Failed to commit task changes", error=stderr.decode())
        return False


def route_after_task_review(
    state: ExecutionState, config: RunnableConfig
) -> Literal["developer", "next_task_node", "__end__"]:
    """Route after task review: next task, retry developer, or end.

    Args:
        state: Current execution state with task tracking fields.
        config: Runnable config with profile.

    Returns:
        "next_task_node" if approved and more tasks remain.
        "developer" if not approved and iterations remain.
        "__end__" if all tasks complete or max iterations reached.
    """
    profile: Profile | None = config.get("configurable", {}).get("profile")
    if not profile:
        raise ValueError("profile is required in config.configurable")

    task_number = state.current_task_index + 1
    approved = state.last_review.approved if state.last_review else False

    if approved:
        # Task approved - check if more tasks remain
        # total_tasks should always be set when using task-based routing,
        # but handle None for safety (treat as single task complete)
        if state.total_tasks is None or state.current_task_index + 1 >= state.total_tasks:
            logger.debug(
                "Task routing decision",
                task=task_number,
                approved=True,
                route="__end__",
                reason="all_tasks_complete",
            )
            return "__end__"  # All tasks complete
        logger.debug(
            "Task routing decision",
            task=task_number,
            approved=True,
            route="next_task_node",
        )
        return "next_task_node"  # Move to next task

    # Not approved - check iteration limit
    max_iterations = profile.max_task_review_iterations
    if state.task_review_iteration >= max_iterations:
        logger.debug(
            "Task routing decision",
            task=task_number,
            approved=False,
            iteration=state.task_review_iteration,
            max_iterations=max_iterations,
            route="__end__",
            reason="max_iterations_reached",
        )
        return "__end__"  # Halt on repeated failure

    logger.debug(
        "Task routing decision",
        task=task_number,
        approved=False,
        iteration=state.task_review_iteration,
        max_iterations=max_iterations,
        route="developer",
    )
    return "developer"  # Retry with feedback


def route_after_review_or_task(
    state: ExecutionState, config: RunnableConfig
) -> Literal["developer", "developer_node", "next_task_node", "__end__"]:
    """Route after review: handles both legacy and task-based execution.

    For task-based execution (total_tasks is set), uses route_after_task_review.
    For legacy execution (total_tasks is None), uses route_after_review.

    Args:
        state: Current execution state.
        config: Runnable config with profile.

    Returns:
        Routing target: developer_node (legacy), developer (task retry),
        next_task_node (task approved), or __end__.
    """
    if state.total_tasks is not None:
        return route_after_task_review(state, config)
    # Legacy mode: route_after_review returns "developer" but graph uses "developer_node"
    result = route_after_review(state, config)
    return "developer_node" if result == "developer" else result


def route_after_evaluation(state: ExecutionState) -> str:
    """Route after evaluation node.

    If auto_approve is set, skip to developer.
    Otherwise, go to human approval.

    Args:
        state: Current execution state with auto_approve flag.

    Returns:
        "developer_node" if auto_approve is set, otherwise "review_approval_node".
    """
    if state.auto_approve:
        return "developer_node"
    return "review_approval_node"


def route_after_fixes(state: ExecutionState) -> str:
    """Route after developer fixes.

    Check if there are still critical/major items to fix.
    If auto_approve, loop back for another review pass.
    Otherwise, go to end approval.

    Args:
        state: Current execution state with review_pass and evaluation_result.

    Returns:
        "reviewer_node" to loop back, "end_approval_node" for human approval, or END.
    """
    max_passes = state.max_review_passes

    if state.review_pass >= max_passes:
        logger.warning(
            "Max review passes reached",
            review_pass=state.review_pass,
            max_passes=max_passes,
        )
        return END

    if state.auto_approve:
        if state.evaluation_result and state.evaluation_result.items_to_implement:
            return "reviewer_node"
        return END

    return "end_approval_node"


def route_after_end_approval(state: ExecutionState) -> str:
    """Route after end approval.

    If human approves, end. Otherwise, loop back to reviewer.

    Args:
        state: Current execution state with human_approved flag.

    Returns:
        END if human approved, otherwise "reviewer_node".
    """
    if state.human_approved:
        return END
    return "reviewer_node"


def create_orchestrator_graph(
    checkpoint_saver: BaseCheckpointSaver[Any] | None = None,
    interrupt_before: list[str] | None = None,
) -> CompiledStateGraph[Any]:
    """Creates and compiles the LangGraph state machine for agentic orchestration.

    The graph flow supports both legacy and task-based execution:

    Legacy flow (total_tasks is None):
    START -> architect_node -> plan_validator_node -> human_approval_node
          -> developer_node <-> reviewer_node -> END

    Task-based flow (total_tasks is set):
    START -> architect_node -> plan_validator_node -> human_approval_node
          -> developer_node -> reviewer_node -> next_task_node -> developer_node
          (loops for each task until all complete or max iterations reached)

    Args:
        checkpoint_saver: Optional checkpoint saver for state persistence.
        interrupt_before: List of node names to interrupt before executing.
            If None and checkpoint_saver is provided, defaults to:
            ["human_approval_node"] for server-mode human-in-the-loop.

    Returns:
        Compiled StateGraph ready for execution.
    """
    workflow = StateGraph(ExecutionState)

    # Add nodes
    workflow.add_node("architect_node", call_architect_node)
    workflow.add_node("plan_validator_node", plan_validator_node)
    workflow.add_node("human_approval_node", human_approval_node)
    workflow.add_node("developer_node", call_developer_node)
    workflow.add_node("reviewer_node", call_reviewer_node)
    workflow.add_node("next_task_node", next_task_node)  # Task-based execution

    # Set entry point
    workflow.set_entry_point("architect_node")

    # Define edges
    # Architect -> Plan Validator -> Human approval
    workflow.add_edge("architect_node", "plan_validator_node")
    workflow.add_edge("plan_validator_node", "human_approval_node")

    # Conditional edge from human_approval_node:
    # - approve: continue to developer_node
    # - reject: go to END
    workflow.add_conditional_edges(
        "human_approval_node",
        route_approval,
        {
            "approve": "developer_node",
            "reject": END
        }
    )

    # Developer -> Reviewer
    workflow.add_edge("developer_node", "reviewer_node")

    # Reviewer routing: handles both legacy and task-based execution
    # - Legacy: developer_node (retry) or __end__ (approved)
    # - Task-based: developer (retry), next_task_node (task approved), or __end__ (all done)
    workflow.add_conditional_edges(
        "reviewer_node",
        route_after_review_or_task,
        {
            "developer": "developer_node",
            "developer_node": "developer_node",
            "next_task_node": "next_task_node",
            "__end__": END,
        }
    )

    # next_task_node loops back to developer for the next task
    workflow.add_edge("next_task_node", "developer_node")

    # Set default interrupt_before only if checkpoint_saver is provided and interrupt_before is None
    if interrupt_before is None and checkpoint_saver is not None:
        interrupt_before = ["human_approval_node"]

    return workflow.compile(
        checkpointer=checkpoint_saver,
        interrupt_before=interrupt_before,
    )


def create_review_graph(
    checkpoint_saver: BaseCheckpointSaver[Any] | None = None,
    interrupt_before: list[str] | None = None,
) -> CompiledStateGraph[Any]:
    """Creates review-fix workflow graph.

    Flow: reviewer -> evaluation -> [approval] -> developer -> [end_approval] -> END

    The workflow loops between reviewer and developer until:
    - No more critical/major items (auto mode), OR
    - Human approves the fixes (manual mode), OR
    - Max review passes reached

    Args:
        checkpoint_saver: Optional checkpoint saver for persistence.
        interrupt_before: Optional list of nodes to interrupt before.
            Defaults to ["review_approval_node", "end_approval_node"] when
            checkpoint_saver is provided.

    Returns:
        Compiled LangGraph state graph ready for execution.
    """
    workflow = StateGraph(ExecutionState)

    # Add nodes
    workflow.add_node("reviewer_node", call_reviewer_node)
    workflow.add_node("evaluation_node", call_evaluation_node)
    workflow.add_node("review_approval_node", review_approval_node)
    workflow.add_node("developer_node", call_developer_node)
    workflow.add_node("end_approval_node", review_approval_node)  # Reuse approval node

    # Set entry point
    workflow.set_entry_point("reviewer_node")

    # Add edges
    workflow.add_edge("reviewer_node", "evaluation_node")
    workflow.add_conditional_edges(
        "evaluation_node",
        route_after_evaluation,
        {"developer_node": "developer_node", "review_approval_node": "review_approval_node"},
    )
    workflow.add_edge("review_approval_node", "developer_node")
    workflow.add_conditional_edges(
        "developer_node",
        route_after_fixes,
        {"reviewer_node": "reviewer_node", "end_approval_node": "end_approval_node", END: END},
    )
    workflow.add_conditional_edges(
        "end_approval_node",
        route_after_end_approval,
        {"reviewer_node": "reviewer_node", END: END},
    )

    # Set default interrupt_before for server mode
    if interrupt_before is None and checkpoint_saver is not None:
        interrupt_before = ["review_approval_node", "end_approval_node"]

    return workflow.compile(
        checkpointer=checkpoint_saver,
        interrupt_before=interrupt_before,
    )
