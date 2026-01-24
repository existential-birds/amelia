"""Implementation pipeline-specific routing functions.

This module contains routing logic specific to the implementation pipeline,
including approval routing and iteration limit checking.
"""

from typing import Literal

from loguru import logger

from amelia.core.types import Profile
from amelia.pipelines.implementation.state import ImplementationState


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
        "__end__" if all tasks complete or max iterations reached.
    """
    task_number = state.current_task_index + 1
    approved = state.last_review.approved if state.last_review else False

    if approved:
        # Task approved - check if more tasks remain
        if state.current_task_index + 1 >= state.total_tasks:
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

    # Not approved - check iteration limit from task_reviewer options, default to 5
    max_iterations = 5
    if "task_reviewer" in profile.agents:
        max_iterations = profile.agents["task_reviewer"].options.get("max_iterations", 5)
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
