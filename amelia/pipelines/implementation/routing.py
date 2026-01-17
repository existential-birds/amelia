"""Implementation pipeline-specific routing functions.

This module contains routing logic specific to the implementation pipeline,
including approval routing and iteration limit checking.
"""

from typing import Literal

from loguru import logger

from amelia.core.state import ExecutionState
from amelia.core.types import Profile


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
    profile: Profile,
) -> Literal["developer", "__end__"]:
    """Route after review based on approval and iteration count (legacy mode).

    Args:
        state: Current execution state with last_review and review_iteration.
        profile: Profile containing max_review_iterations.

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

    max_iterations = profile.max_review_iterations

    if state.review_iteration >= max_iterations:
        logger.warning(
            "Max review iterations reached, terminating loop",
            max_iterations=max_iterations,
        )
        return "__end__"

    return "developer"


def route_after_task_review(
    state: ExecutionState,
    profile: Profile,
) -> Literal["developer", "next_task_node", "__end__"]:
    """Route after task review: next task, retry developer, or end.

    Args:
        state: Current execution state with task tracking fields.
        profile: Profile containing max_task_review_iterations.

    Returns:
        "next_task_node" if approved and more tasks remain.
        "developer" if not approved and iterations remain.
        "__end__" if all tasks complete or max iterations reached.
    """
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
