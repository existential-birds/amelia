"""Review pipeline graph construction.

This module provides the factory function to create the LangGraph
state machine for the review-fix workflow.
"""

from typing import TYPE_CHECKING, Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.nodes import call_developer_node, call_reviewer_node
from amelia.pipelines.review.nodes import call_evaluation_node
from amelia.pipelines.review.routing import (
    route_after_evaluation,
    route_after_fixes,
)


if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


def create_review_graph(
    checkpointer: "BaseCheckpointSaver[Any] | None" = None,
    interrupt_before: list[str] | None = None,
) -> CompiledStateGraph[Any]:
    """Creates review-fix workflow graph.

    Flow: reviewer -> evaluation -> developer -> reviewer (loop) -> END

    The workflow loops between reviewer and developer until:
    - No more items to implement (evaluation finds no issues), OR
    - Max review passes reached

    Args:
        checkpointer: Optional checkpoint saver for persistence.
        interrupt_before: Optional list of nodes to interrupt before.

    Returns:
        Compiled LangGraph state graph ready for execution.
    """
    workflow = StateGraph(ImplementationState)

    # Add nodes
    workflow.add_node("reviewer_node", call_reviewer_node)
    workflow.add_node("evaluation_node", call_evaluation_node)
    workflow.add_node("developer_node", call_developer_node)

    # Set entry point
    workflow.set_entry_point("reviewer_node")

    # Add edges
    workflow.add_edge("reviewer_node", "evaluation_node")
    workflow.add_conditional_edges(
        "evaluation_node",
        route_after_evaluation,
        {"developer_node": "developer_node", END: END},
    )
    workflow.add_conditional_edges(
        "developer_node",
        route_after_fixes,
        {"reviewer_node": "reviewer_node", END: END},
    )

    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )
