"""Implementation pipeline for building features from issues."""

from typing import TYPE_CHECKING, Any

from langgraph.graph.state import CompiledStateGraph

from amelia.pipelines.base import Pipeline, PipelineMetadata
from amelia.pipelines.implementation.graph import create_implementation_graph
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.mixins import ImplementationStateMixin


if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


class ImplementationPipeline(ImplementationStateMixin, Pipeline[ImplementationState]):
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
