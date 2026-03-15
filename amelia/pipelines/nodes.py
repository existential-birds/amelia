"""Shared LangGraph node functions for pipeline infrastructure.

This module contains reusable node functions extracted from the orchestrator
that can be used across multiple pipelines. These nodes handle common agentic
operations like developer execution and code review.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from langchain_core.runnables.config import RunnableConfig
from loguru import logger

from amelia.agents.developer import Developer
from amelia.agents.reviewer import Reviewer
from amelia.core.types import ReviewResult
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.utils import extract_node_config
from amelia.server.models.tokens import TokenUsage, calculate_token_cost
from amelia.skills.review import REVIEW_TYPE_SKILLS, detect_stack, load_skills
from amelia.tools.git_utils import get_current_commit


if TYPE_CHECKING:
    from amelia.sandbox.provider import SandboxProvider
    from amelia.server.database.repository import WorkflowRepository


async def _resolve_commit(
    profile_repo_root: str,
    sandbox_provider: "SandboxProvider | None" = None,
) -> str | None:
    """Resolve the current HEAD commit, preferring the sandbox repo when available."""
    sha = (
        await _run_git_command(
            ["git", "rev-parse", "HEAD"],
            profile_repo_root,
            sandbox_provider,
        )
    ).strip()
    if sha:
        return sha
    return await get_current_commit(cwd=profile_repo_root)


async def _run_git_command(
    cmd: list[str],
    repo_root: str,
    sandbox_provider: "SandboxProvider | None" = None,
) -> str:
    """Run a git command, preferring sandbox when available.

    Falls back to local subprocess if sandbox fails or is unavailable.

    Args:
        cmd: Git command as list of args.
        repo_root: Local repo root for host fallback.
        sandbox_provider: Optional sandbox for remote execution.

    Returns:
        Raw stdout output as string.
    """
    if sandbox_provider is not None:
        try:
            lines: list[str] = []
            async for line in sandbox_provider.exec_stream(cmd):
                lines.append(line)
            return "".join(lines)
        except (OSError, RuntimeError):
            logger.warning(
                "Failed to run git command in sandbox, falling back to host",
                cmd=cmd[:3],
            )

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=repo_root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if stderr:
        logger.warning(
            "Git command produced stderr output",
            cmd=cmd[:3],
            stderr=stderr.decode().strip()[:500],
        )
    return stdout.decode()


async def _save_token_usage(
    driver: Any,
    workflow_id: uuid.UUID,
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
        cost = driver_usage.cost_usd or 0.0

        # Compute cost from cached pricing if driver didn't provide it
        if not cost:
            model = driver_usage.model or getattr(driver, "model", "unknown")
            cost = await calculate_token_cost(
                model=model,
                input_tokens=driver_usage.input_tokens or 0,
                output_tokens=driver_usage.output_tokens or 0,
                cache_read_tokens=driver_usage.cache_read_tokens or 0,
                cache_creation_tokens=driver_usage.cache_creation_tokens or 0,
            )

        usage = TokenUsage(
            workflow_id=workflow_id,
            agent=agent,
            model=driver_usage.model or getattr(driver, "model", "unknown"),
            input_tokens=driver_usage.input_tokens or 0,
            output_tokens=driver_usage.output_tokens or 0,
            cache_read_tokens=driver_usage.cache_read_tokens or 0,
            cache_creation_tokens=driver_usage.cache_creation_tokens or 0,
            cost_usd=cost,
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


async def call_developer_node(
    state: ImplementationState,
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

    # Extract all config params in one call
    nc = extract_node_config(config)

    # Capture current HEAD so the next reviewer only diffs against this point
    pre_dev_commit = await _resolve_commit(nc.profile.repo_root, nc.sandbox_provider)

    # Task-based execution: clear session and inject task-scoped context
    task_number = state.current_task_index + 1  # 1-indexed for display
    logger.info(
        "Starting task execution",
        task=task_number,
        total_tasks=state.total_tasks,
        fresh_session=True,
    )
    state = state.model_copy(update={
        "driver_session_id": None,  # Fresh session for each task
        # plan_markdown stays intact - extraction happens in Developer._build_prompt
    })

    agent_config = nc.profile.get_agent_config("developer")
    developer = Developer(agent_config, prompts=nc.prompts, sandbox_provider=nc.sandbox_provider)

    final_state = state
    try:
        async for new_state, event in developer.run(state, nc.profile, workflow_id=nc.workflow_id):
            final_state = new_state
            if nc.event_bus and event is not None:
                nc.event_bus.emit(event)
    except Exception:
        logger.exception(
            "Developer execution failed",
            task=task_number,
            total_tasks=state.total_tasks,
            workflow_id=str(nc.workflow_id),
        )
        raise

    await _save_token_usage(developer.driver, nc.workflow_id, "developer", nc.repository)

    logger.info(
        "Agent action completed",
        agent="developer",
        action="agentic_execution",
        tool_calls_count=len(final_state.tool_calls),
        agentic_status=str(final_state.agentic_status),
    )

    return {
        "tool_calls": list(final_state.tool_calls),
        "tool_results": list(final_state.tool_results),
        "agentic_status": final_state.agentic_status,
        "final_response": final_state.final_response,
        "error": final_state.error,
        "driver_session_id": final_state.driver_session_id,
        "base_commit": pre_dev_commit or state.base_commit,
    }


async def call_reviewer_node(
    state: ImplementationState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Reviewer agent to review code changes.

    Always uses agentic review which fetches the diff via git tools. This avoids
    the "Argument list too long" error that can occur with large diffs.

    If base_commit is not set in state, computes it using get_current_commit().

    Args:
        state: Current execution state containing issue and goal information.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with review results.
    """
    logger.info(f"Orchestrator: Calling Reviewer for issue {state.issue.id if state.issue else 'N/A'}")

    # Extract all config params in one call
    nc = extract_node_config(config)

    # Use "task_reviewer" only for non-final tasks in task-based execution
    is_non_final_task = state.current_task_index + 1 < state.total_tasks
    agent_name = "task_reviewer" if is_non_final_task else "reviewer"
    # Fall back to "reviewer" config if "task_reviewer" not configured
    try:
        agent_config = nc.profile.get_agent_config(agent_name)
    except ValueError:
        agent_config = nc.profile.get_agent_config("reviewer")
    # Compute base_commit if not in state
    base_commit = state.base_commit
    if not base_commit:
        computed_commit = await _resolve_commit(nc.profile.repo_root, nc.sandbox_provider)
        if computed_commit:
            base_commit = computed_commit
            logger.info(
                "Computed base_commit for agentic review",
                agent=agent_name,
                base_commit=base_commit,
            )
        else:
            # Fallback to HEAD if get_current_commit fails
            base_commit = "HEAD"
            logger.warning(
                "Could not compute base_commit, falling back to HEAD",
                agent=agent_name,
            )
    else:
        logger.debug(
            "Using existing base_commit for agentic review",
            agent=agent_name,
            base_commit=base_commit,
        )

    # Detect stack and load review skills
    config_review_types = (config or {}).get("configurable", {}).get("review_types")
    raw_review_types = config_review_types or agent_config.options.get("review_types", ["general"])
    if not isinstance(raw_review_types, list) or not raw_review_types:
        logger.warning(
            "Invalid review_types in agent options, falling back to ['general']",
            raw_review_types=raw_review_types,
        )
        raw_review_types = ["general"]
    review_types: list[str] = [str(rt) for rt in raw_review_types]

    # Warn about unknown review types
    unknown_types = [rt for rt in review_types if rt not in REVIEW_TYPE_SKILLS]
    if unknown_types:
        logger.warning(
            "Unknown review_types will have no base skills",
            unknown_types=unknown_types,
            known_types=list(REVIEW_TYPE_SKILLS.keys()),
            agent=agent_name,
        )

    changed_files_raw, diff_content = await asyncio.gather(
        _run_git_command(
            ["git", "diff", "--name-only", base_commit, "HEAD"],
            nc.profile.repo_root,
            nc.sandbox_provider,
        ),
        _run_git_command(
            ["git", "diff", base_commit, "HEAD"],
            nc.profile.repo_root,
            nc.sandbox_provider,
        ),
    )
    changed_files = [f for f in changed_files_raw.splitlines() if f.strip()]
    tags = detect_stack(changed_files, diff_content)

    logger.info(
        "Detected stack for review",
        agent=agent_name,
        tags=sorted(tags),
        review_types=review_types,
    )

    # Run a separate reviewer for each review type
    reviews: list[ReviewResult] = []
    new_session_id: str | None = None

    for review_type in review_types:
        guidelines = load_skills(tags, [review_type])
        logger.info(
            "Running review pass",
            agent=agent_name,
            review_type=review_type,
            guidelines_length=len(guidelines),
        )

        reviewer = Reviewer(
            agent_config,
            event_bus=nc.event_bus,
            prompts=nc.prompts,
            agent_name=agent_name,
            sandbox_provider=nc.sandbox_provider,
            review_guidelines=guidelines,
        )

        review_result, session_id = await reviewer.agentic_review(
            state, base_commit, nc.profile, workflow_id=nc.workflow_id
        )

        await _save_token_usage(reviewer.driver, nc.workflow_id, agent_name, nc.repository)

        # Tag result with the review type as reviewer_persona
        review_result = review_result.model_copy(update={"reviewer_persona": review_type})
        reviews.append(review_result)
        new_session_id = session_id

        logger.info(
            "Review pass completed",
            agent=agent_name,
            review_type=review_type,
            severity=str(review_result.severity),
            approved=review_result.approved,
            issue_count=len(review_result.comments),
        )

    next_iteration = state.review_iteration + 1

    # Build return dict with all review results
    result_dict: dict[str, Any] = {
        "last_reviews": reviews,
        "driver_session_id": new_session_id,
        "review_iteration": next_iteration,
        "task_review_iteration": state.task_review_iteration + 1,
    }

    # Debug: Log the full state update being returned
    logger.debug(
        "call_reviewer_node returning state update",
        review_count=len(reviews),
        all_approved=all(r.approved for r in reviews),
        review_types=[r.reviewer_persona for r in reviews],
        review_iteration=next_iteration,
        task_review_iteration=result_dict["task_review_iteration"],
        total_tasks=state.total_tasks,
        current_task_index=state.current_task_index,
    )

    return result_dict
