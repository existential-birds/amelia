"""LangGraph state machine for the implementation pipeline.

This module creates and compiles the LangGraph state machine for the
Architect -> Developer <-> Reviewer flow.
"""

from typing import TYPE_CHECKING, Any, Literal

from langchain_core.runnables.config import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from amelia.pipelines.implementation.nodes import (
    call_architect_node,
    human_approval_node,
    next_task_node,
    plan_validator_node,
)
from amelia.pipelines.implementation.routing import (
    route_after_task_review,
    route_approval,
)
from amelia.pipelines.implementation.state import ImplementationState, rebuild_implementation_state
from amelia.pipelines.nodes import call_developer_node, call_reviewer_node
from amelia.pipelines.utils import extract_config_params


# Resolve forward references in ImplementationState. Must be done after importing
# Reviewer and Evaluator since they define StructuredReviewResult and EvaluationResult.
rebuild_implementation_state()


if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


def _route_after_review_or_task(
    state: ImplementationState, config: RunnableConfig
) -> Literal["developer", "next_task_node", "__end__"]:
    """Route after task review to next task, retry, or end.

    Args:
        state: Current execution state.
        config: Runnable config with profile.

    Returns:
        Routing target: developer (retry), next_task_node (task approved), or __end__.
    """
    _, _, profile = extract_config_params(config)
    return route_after_task_review(state, profile)


def create_implementation_graph(
    checkpointer: "BaseCheckpointSaver[Any] | None" = None,
    interrupt_before: list[str] | None = None,
) -> CompiledStateGraph[Any]:
    """Creates and compiles the LangGraph state machine for implementation.

    The graph flow:
    START -> architect_node -> plan_validator_node -> human_approval_node
          -> developer_node -> reviewer_node -> next_task_node -> developer_node
          (loops for each task until all complete or max iterations reached)

    Args:
        checkpointer: Optional checkpoint saver for state persistence.
        interrupt_before: List of node names to interrupt before executing.
            If None and checkpointer is provided, defaults to:
            ["human_approval_node"] for server-mode human-in-the-loop.

    Returns:
        Compiled StateGraph ready for execution.
    """
    workflow = StateGraph(ImplementationState)

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

    # Reviewer routing: developer (retry), next_task_node (task approved), or __end__ (all done)
    workflow.add_conditional_edges(
        "reviewer_node",
        _route_after_review_or_task,
        {
            "developer": "developer_node",
            "next_task_node": "next_task_node",
            "__end__": END,
        }
    )

    # next_task_node loops back to developer for the next task
    workflow.add_edge("next_task_node", "developer_node")

    # Set default interrupt_before only if checkpointer is provided and interrupt_before is None
    if interrupt_before is None and checkpointer is not None:
        interrupt_before = ["human_approval_node"]

    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )
