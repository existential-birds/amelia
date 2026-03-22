"""Graph construction for the PR auto-fix pipeline.

Builds a linear LangGraph state machine:
classify_node -> develop_node -> commit_push_node -> reply_resolve_node -> END
"""

from typing import TYPE_CHECKING, Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from amelia.pipelines.pr_auto_fix.nodes import (
    classify_node,
    commit_push_node,
    develop_node,
    reply_resolve_node,
)
from amelia.pipelines.pr_auto_fix.state import PRAutoFixState


if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


def create_pr_auto_fix_graph(
    checkpointer: "BaseCheckpointSaver[Any] | None" = None,
) -> CompiledStateGraph[Any]:
    """Create and compile the PR auto-fix pipeline graph.

    Flow: classify_node -> develop_node -> commit_push_node -> reply_resolve_node -> END

    Args:
        checkpointer: Optional checkpoint saver for persistence.

    Returns:
        Compiled LangGraph state graph ready for execution.
    """
    workflow = StateGraph(PRAutoFixState)

    workflow.add_node("classify_node", classify_node)
    workflow.add_node("develop_node", develop_node)
    workflow.add_node("commit_push_node", commit_push_node)
    workflow.add_node("reply_resolve_node", reply_resolve_node)

    workflow.set_entry_point("classify_node")

    workflow.add_edge("classify_node", "develop_node")
    workflow.add_edge("develop_node", "commit_push_node")
    workflow.add_edge("commit_push_node", "reply_resolve_node")
    workflow.add_edge("reply_resolve_node", END)

    return workflow.compile(checkpointer=checkpointer)
