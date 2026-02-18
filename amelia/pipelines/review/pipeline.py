"""Review pipeline for code review workflows.

This module provides the ReviewPipeline class that implements the Pipeline
protocol for code review workflows.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from langgraph.graph.state import CompiledStateGraph

from amelia.pipelines.base import Pipeline, PipelineMetadata
from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)
from amelia.pipelines.review.graph import create_review_graph


# Resolve forward references in ImplementationState. Must be done after importing
# StructuredReviewResult and EvaluationResult (via the rebuild function).
rebuild_implementation_state()


if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


class ReviewPipeline(Pipeline[ImplementationState]):
    """Pipeline for code review workflows.

    Implements the Reviewer -> Evaluator -> Developer cycle.
    Uses ImplementationState as it shares state with the implementation pipeline.

    The review pipeline flow:
    1. Reviewer: Reviews code changes and provides feedback
    2. Evaluator: Evaluates feedback and applies decision matrix
    3. Developer: Implements approved fixes
    4. (Loop) Back to Reviewer until approved or max passes reached
    """

    @property
    def metadata(self) -> PipelineMetadata:
        """Return metadata describing this pipeline."""
        return PipelineMetadata(
            name="review",
            display_name="Review",
            description="Review code changes using Reviewer, Evaluator, and Developer agents",
        )

    def create_graph(
        self,
        checkpointer: "BaseCheckpointSaver[Any] | None" = None,
    ) -> CompiledStateGraph[Any]:
        """Create and compile the LangGraph state machine."""
        return create_review_graph(checkpointer=checkpointer)

    def get_initial_state(self, **kwargs: object) -> ImplementationState:
        """Create initial state for a new workflow.

        Args:
            **kwargs: Must include:
                - workflow_id: Unique identifier for the workflow
                - profile_id: ID of the active profile

        Returns:
            ImplementationState configured for a review workflow.
        """
        return ImplementationState(
            workflow_id=uuid.UUID(str(kwargs["workflow_id"])),
            profile_id=str(kwargs["profile_id"]),
            created_at=datetime.now(UTC),
            status="pending",
        )

    def get_state_class(self) -> type[ImplementationState]:
        """Return the state class used by this pipeline."""
        return ImplementationState
