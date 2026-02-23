"""Implementation pipeline-specific routing functions.

This module contains routing logic specific to the implementation pipeline,
including approval routing and iteration limit checking.
"""

from typing import Literal

from loguru import logger

from amelia.core.types import Profile
from amelia.pipelines.implementation.state import ImplementationState


def route_after_start(state: ImplementationState) -> Literal["architect", "plan_validator"]:
    """Route to architect or directly to validator based on external plan flag.

    Args:
        state: Current execution state with external_plan flag.

    Returns:
        'architect' if plan needs to be generated.
        'plan_validator' if external plan was provided.
    """
    if state.external_plan:
        return "plan_validator"
    return "architect"


def route_approval(state: ImplementationState) -> Literal["approve", "reject"]:
    """Route based on human approval status.

    Args:
        state: Current execution state containing human_approved flag.

    Returns:
        'approve' if approved (continue to developer).
        'reject' if not approved.
    """
    return "approve" if state.human_approved else "reject"


def route_after_task_review(
    state: ImplementationState,
    profile: Profile,
) -> Literal["developer", "next_task_node", "__end__"]:
    """Route after task review: next task, retry developer, or end.

    Args:
        state: Current execution state with task tracking fields.
        profile: Profile with agent configs. Uses task_reviewer.options.max_iterations.

    Returns:
        "next_task_node" if approved and more tasks remain.
        "developer" if not approved and iterations remain.
        "next_task_node" if max iterations on a non-final task (advance with warning).
        "__end__" if all tasks complete or max iterations on final task.
    """
    task_number = state.current_task_index + 1
    is_final_task = state.current_task_index + 1 >= state.total_tasks
    approved = state.last_review.approved if state.last_review else False

    if approved:
        if is_final_task:
            logger.debug(
                "Task routing decision",
                task=task_number,
                approved=True,
                route="__end__",
                reason="all_tasks_complete",
            )
            return "__end__"
        logger.debug(
            "Task routing decision",
            task=task_number,
            approved=True,
            route="next_task_node",
        )
        return "next_task_node"

    # Not approved - check iteration limit from task_reviewer options, default to 5
    max_iterations = 5
    if "task_reviewer" in profile.agents:
        max_iterations = profile.agents["task_reviewer"].options.get("max_iterations", 5)
    if state.task_review_iteration >= max_iterations:
        if is_final_task:
            logger.debug(
                "Task routing decision",
                task=task_number,
                approved=False,
                iteration=state.task_review_iteration,
                max_iterations=max_iterations,
                route="__end__",
                reason="max_iterations_on_final_task",
            )
            return "__end__"
        logger.warning(
            "Max review iterations reached on non-final task, advancing to next task",
            task=task_number,
            iteration=state.task_review_iteration,
            max_iterations=max_iterations,
            route="next_task_node",
        )
        return "next_task_node"

    logger.debug(
        "Task routing decision",
        task=task_number,
        approved=False,
        iteration=state.task_review_iteration,
        max_iterations=max_iterations,
        route="developer",
    )
    return "developer"


def route_after_plan_validation(
    state: ImplementationState,
    profile: Profile,
) -> Literal["approved", "revise", "escalate"]:
    """Route after plan validation: approve, revise, or escalate to human.

    Follows the same pattern as route_after_task_review:
    check result -> check iteration count -> route.

    Args:
        state: Current state with plan_validation_result and plan_revision_count.
        profile: Profile with plan_validator agent config for max_iterations.

    Returns:
        "approved" if valid (or no result for backward compat).
        "revise" if invalid and revisions remain.
        "escalate" if max revisions exhausted (let human decide).
    """
    result = state.plan_validation_result
    if result is None or result.valid:
        return "approved"

    max_iterations = 3
    if "plan_validator" in profile.agents:
        max_iterations = profile.agents["plan_validator"].options.get("max_iterations", 3)

    if state.plan_revision_count >= max_iterations:
        logger.warning(
            "Plan validation failed after max revisions, escalating to human",
            revision_count=state.plan_revision_count,
            max_iterations=max_iterations,
            issues=result.issues,
        )
        return "escalate"

    logger.debug(
        "Plan validation failed, routing to architect for revision",
        revision_count=state.plan_revision_count,
        max_iterations=max_iterations,
        issues=result.issues,
    )
    return "revise"
