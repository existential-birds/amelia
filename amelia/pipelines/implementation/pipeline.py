"""Implementation pipeline for building features from issues."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from langgraph.graph.state import CompiledStateGraph

from amelia.pipelines.base import Pipeline, PipelineMetadata
from amelia.pipelines.implementation.graph import create_implementation_graph
from amelia.pipelines.implementation.state import ImplementationState


if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


class ImplementationPipeline(Pipeline[ImplementationState]):
    """Pipeline for implementing features from issues.

    Implements the Architect -> Developer <-> Reviewer flow.
    """

    @property
    def metadata(self) -> PipelineMetadata:
        """Return metadata describing this pipeline."""
        return PipelineMetadata(
            name="implementation",
            display_name="Implementation",
            description="Build features from issues using Architect, Developer, and Reviewer agents",
        )

    def create_graph(
        self,
        checkpointer: "BaseCheckpointSaver[Any] | None" = None,
    ) -> CompiledStateGraph[Any]:
        """Create and compile the LangGraph state machine."""
        return create_implementation_graph(checkpointer=checkpointer)

    def get_initial_state(self, **kwargs: object) -> ImplementationState:
        """Create initial state for a new workflow."""
        return ImplementationState(
            workflow_id=str(kwargs["workflow_id"]),
            profile_id=str(kwargs["profile_id"]),
            created_at=datetime.now(UTC),
            status="pending",
        )

    def get_state_class(self) -> type[ImplementationState]:
        """Return the state class used by this pipeline."""
        return ImplementationState
