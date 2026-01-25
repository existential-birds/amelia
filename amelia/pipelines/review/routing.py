"""Review pipeline routing functions.

This module contains routing functions specific to the review pipeline
that determine transitions between nodes in the review-fix workflow.
"""

from langgraph.graph import END
from loguru import logger

from amelia.pipelines.implementation.state import ImplementationState


def route_after_evaluation(state: ImplementationState) -> str:
    """Route after evaluation based on items to implement.

    Args:
        state: Current execution state with evaluation_result.

    Returns:
        END if no issues to fix, "developer_node" if there are items to implement.
    """
    if not state.evaluation_result or not state.evaluation_result.items_to_implement:
        logger.info("No items to implement, ending workflow")
        return END

    logger.info(
        "Items to implement, routing to developer",
        count=len(state.evaluation_result.items_to_implement),
    )
    return "developer_node"


def route_after_fixes(state: ImplementationState) -> str:
    """Route after developer fixes.

    Check if max passes reached, otherwise loop back to reviewer.

    Args:
        state: Current execution state with review_pass.

    Returns:
        "reviewer_node" to continue review loop, or END if max passes reached.
    """
    max_passes = state.max_review_passes

    if state.review_pass >= max_passes:
        logger.warning(
            "Max review passes reached",
            review_pass=state.review_pass,
            max_passes=max_passes,
        )
        return END

    return "reviewer_node"
