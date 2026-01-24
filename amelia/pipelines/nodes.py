"""Shared LangGraph node functions for pipeline infrastructure.

This module contains reusable node functions extracted from the orchestrator
that can be used across multiple pipelines. These nodes handle common agentic
operations like developer execution and code review.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from langchain_core.runnables.config import RunnableConfig
from loguru import logger

from amelia.agents.developer import Developer
from amelia.agents.reviewer import Reviewer
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.utils import extract_config_params
from amelia.server.models.tokens import TokenUsage
from amelia.tools.git_utils import get_current_commit


if TYPE_CHECKING:
    from amelia.server.database.repository import WorkflowRepository


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

    # Extract event_bus, workflow_id, and profile from config
    event_bus, workflow_id, profile = extract_config_params(config or {})

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

    config = config or {}
    repository = config.get("configurable", {}).get("repository")

    agent_config = profile.get_agent_config("developer")
    developer = Developer(agent_config)

    final_state = state
    async for new_state, event in developer.run(state, profile):
        final_state = new_state
        # Stream events are emitted via event_bus if provided
        if event_bus:
            event_bus.emit(event)

    await _save_token_usage(developer.driver, workflow_id, "developer", repository)

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

    # Extract event_bus, workflow_id, and profile from config
    event_bus, workflow_id, profile = extract_config_params(config or {})

    config = config or {}
    configurable = config.get("configurable", {})
    repository = configurable.get("repository")
    prompts = configurable.get("prompts", {})

    # Use "task_reviewer" only for non-final tasks in task-based execution
    is_non_final_task = state.current_task_index + 1 < state.total_tasks
    agent_name = "task_reviewer" if is_non_final_task else "reviewer"
    # Fall back to "reviewer" config if "task_reviewer" not configured
    try:
        agent_config = profile.get_agent_config(agent_name)
    except ValueError:
        agent_config = profile.get_agent_config("reviewer")
    reviewer = Reviewer(agent_config, event_bus=event_bus, prompts=prompts, agent_name=agent_name)

    # Compute base_commit if not in state
    base_commit = state.base_commit
    if not base_commit:
        computed_commit = await get_current_commit(cwd=profile.working_dir)
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

    # Always use agentic review - it fetches the diff via git tools
    review_result, new_session_id = await reviewer.agentic_review(
        state, base_commit, profile, workflow_id=workflow_id
    )

    await _save_token_usage(reviewer.driver, workflow_id, agent_name, repository)

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
    result_dict["task_review_iteration"] = state.task_review_iteration + 1

    # Debug: Log the full state update being returned
    logger.debug(
        "call_reviewer_node returning state update",
        last_review_approved=review_result.approved,
        last_review_severity=review_result.severity,
        last_review_persona=review_result.reviewer_persona,
        last_review_comment_count=len(review_result.comments),
        review_iteration=next_iteration,
        task_review_iteration=result_dict.get("task_review_iteration"),
        total_tasks=state.total_tasks,
        current_task_index=state.current_task_index,
    )

    return result_dict
