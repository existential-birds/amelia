"""LangGraph state machine for the implementation pipeline.

This module creates and compiles the LangGraph state machine for the
Architect -> Developer <-> Reviewer flow.
"""

from typing import TYPE_CHECKING, Any, Literal

from langchain_core.runnables.config import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from loguru import logger

from amelia.core.state import ExecutionState, rebuild_execution_state
from amelia.pipelines.implementation.nodes import (
    call_architect_node,
    human_approval_node,
    next_task_node,
    plan_validator_node,
)
from amelia.pipelines.implementation.routing import (
    route_after_review,
    route_after_task_review,
    route_approval,
)
from amelia.pipelines.nodes import call_developer_node, call_reviewer_node
from amelia.pipelines.utils import extract_config_params


# Resolve forward references in ExecutionState. Must be done after importing
# Reviewer and Evaluator since they define StructuredReviewResult and EvaluationResult.
rebuild_execution_state()


if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


def _route_after_review_or_task(
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
    _, _, profile = extract_config_params(config)

    if state.total_tasks is not None:
        result = route_after_task_review(state, profile)
        logger.debug(
            "_route_after_review_or_task: task mode",
            route=result,
            current_task_index=state.current_task_index,
            total_tasks=state.total_tasks,
        )
        return result

    # Legacy mode: route_after_review returns "developer" but graph uses "developer_node"
    result = route_after_review(state, profile)
    final_result: Literal["developer_node", "__end__"] = (
        "developer_node" if result == "developer" else "__end__"
    )
    logger.debug(
        "_route_after_review_or_task: legacy mode",
        inner_result=result,
        final_route=final_result,
    )
    return final_result


def create_implementation_graph(
    checkpointer: "BaseCheckpointSaver[Any] | None" = None,
    interrupt_before: list[str] | None = None,
) -> CompiledStateGraph[Any]:
    """Creates and compiles the LangGraph state machine for implementation.

    The graph flow supports both legacy and task-based execution:

    Legacy flow (total_tasks is None):
    START -> architect_node -> plan_validator_node -> human_approval_node
          -> developer_node <-> reviewer_node -> END

    Task-based flow (total_tasks is set):
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
        _route_after_review_or_task,
        {
            "developer": "developer_node",
            "developer_node": "developer_node",
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
