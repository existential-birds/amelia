"""Shared routing functions for pipelines.

This module contains routing logic extracted from the orchestrator that can be
shared across different pipeline implementations.
"""

from typing import Literal

from loguru import logger

from amelia.pipelines.implementation.state import ImplementationState


def route_after_review_or_task(
    state: ImplementationState,
) -> Literal["developer", "next_task_node", "__end__"]:
    """Route after review: handles both legacy and task-based execution.

    For task-based execution (total_tasks is set), routes based on task completion.
    For legacy execution (total_tasks is None), routes based on review approval.

    This is a simplified routing function that doesn't check iteration limits.
    For iteration limit checking, use the full routing functions in the orchestrator.

    Args:
        state: Current implementation state with review and task tracking fields.

    Returns:
        "developer" if review rejected (retry).
        "next_task_node" if task approved and more tasks remain.
        "__end__" if all tasks complete or review approved in legacy mode.
    """
    approved = state.last_review.approved if state.last_review else False

    if state.total_tasks is not None:
        # Task mode
        if approved:
            # Check if more tasks remain
            if state.current_task_index + 1 >= state.total_tasks:
                logger.debug(
                    "route_after_review_or_task: task mode, all tasks complete",
                    current_task_index=state.current_task_index,
                    total_tasks=state.total_tasks,
                )
                return "__end__"
            logger.debug(
                "route_after_review_or_task: task mode, moving to next task",
                current_task_index=state.current_task_index,
                total_tasks=state.total_tasks,
            )
            return "next_task_node"
        # Not approved - retry
        logger.debug(
            "route_after_review_or_task: task mode, task rejected",
            current_task_index=state.current_task_index,
            total_tasks=state.total_tasks,
        )
        return "developer"

    # Legacy mode
    if approved:
        logger.debug("route_after_review_or_task: legacy mode, approved")
        return "__end__"

    logger.debug("route_after_review_or_task: legacy mode, rejected")
    return "developer"
