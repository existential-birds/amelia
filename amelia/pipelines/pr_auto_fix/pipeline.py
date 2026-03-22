"""PR auto-fix pipeline implementation.

Provides the PRAutoFixPipeline class that implements the Pipeline protocol
for automatically fixing PR review comments.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from langgraph.graph.state import CompiledStateGraph

from amelia.pipelines.base import Pipeline, PipelineMetadata
from amelia.pipelines.pr_auto_fix.graph import create_pr_auto_fix_graph
from amelia.pipelines.pr_auto_fix.state import PRAutoFixState


if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


class PRAutoFixPipeline(Pipeline[PRAutoFixState]):
    """Pipeline for automatically fixing PR review comments.

    Implements the Pipeline protocol with a linear graph:
    classify_node -> develop_node -> commit_push_node -> reply_resolve_node -> END
    """

    @property
    def metadata(self) -> PipelineMetadata:
        """Return metadata describing this pipeline."""
        return PipelineMetadata(
            name="pr_auto_fix",
            display_name="PR Auto-Fix",
            description="Fix PR review comments automatically",
        )

    def create_graph(
        self,
        checkpointer: "BaseCheckpointSaver[Any] | None" = None,
    ) -> CompiledStateGraph[Any]:
        """Create and compile the LangGraph state machine."""
        return create_pr_auto_fix_graph(checkpointer=checkpointer)

    def get_initial_state(self, **kwargs: object) -> PRAutoFixState:
        """Create initial state for a new PR auto-fix workflow.

        Required kwargs: workflow_id, profile_id, pr_number, head_branch, repo.
        Optional: created_at (defaults to now).
        """
        if "workflow_id" not in kwargs:
            kwargs["workflow_id"] = uuid4()
        if "created_at" not in kwargs:
            kwargs["created_at"] = datetime.now(tz=UTC)
        return PRAutoFixState(**kwargs)  # type: ignore[arg-type]

    def get_state_class(self) -> type[PRAutoFixState]:
        """Return the state class used by this pipeline."""
        return PRAutoFixState
