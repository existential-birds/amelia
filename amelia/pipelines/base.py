"""Pipeline protocol and base state types.

This module defines the foundational abstractions for the pipeline system:
- PipelineMetadata: Immutable dataclass describing a pipeline
- HistoryEntry: Structured entry for agent action history
- BasePipelineState: Common fields shared across all pipelines
- Pipeline: Protocol that all workflow types implement
"""

import operator
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal, Protocol, TypeVar

from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, Field


if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


@dataclass(frozen=True)
class PipelineMetadata:
    """Immutable metadata describing a pipeline.

    Attributes:
        name: Machine-readable identifier (e.g., "implementation").
        display_name: Human-readable name (e.g., "Implementation").
        description: Brief description of the pipeline's purpose.
    """

    name: str
    display_name: str
    description: str


@dataclass(frozen=True)
class HistoryEntry:
    """Structured history entry for agent actions.

    Attributes:
        timestamp: When the action occurred.
        agent: Which agent performed the action (e.g., "architect", "developer").
        message: Description of the action.
    """

    timestamp: datetime
    agent: str
    message: str


class BasePipelineState(BaseModel):
    """Common state for all pipelines.

    This model is frozen (immutable) to support the stateless reducer pattern.
    Use model_copy(update={...}) to create modified copies.

    Attributes:
        workflow_id: Unique identifier for this workflow instance.
        pipeline_type: Type of pipeline (e.g., "implementation", "review").
        profile_id: ID of the active profile.
        created_at: When the workflow was created.
        status: Current workflow status.
        history: Append-only list of agent actions.
        pending_user_input: Whether waiting for user input.
        user_message: Message from user (e.g., approval feedback).
        driver_session_id: Session ID for driver continuity.
        final_response: Final response when workflow completes.
        error: Error message if status is 'failed'.
    """

    model_config = ConfigDict(frozen=True)

    # Identity (immutable, self-describing for serialization)
    workflow_id: str
    pipeline_type: str
    profile_id: str
    created_at: datetime

    # Lifecycle
    status: Literal["pending", "running", "paused", "completed", "failed"]

    # Observability (append-only via reducer)
    history: Annotated[list[HistoryEntry], operator.add] = Field(default_factory=list)

    # Human interaction
    pending_user_input: bool = False
    user_message: str | None = None

    # Agentic execution
    driver_session_id: str | None = None
    final_response: str | None = None
    error: str | None = None


StateT_co = TypeVar("StateT_co", bound=BasePipelineState, covariant=True)


class Pipeline(Protocol[StateT_co]):
    """Protocol that all pipelines must implement.

    Each pipeline provides:
    - Metadata describing the pipeline
    - A factory method to create the LangGraph state machine
    - A factory method to create initial state
    - Access to the state class for type information
    """

    @property
    def metadata(self) -> PipelineMetadata:
        """Return metadata describing this pipeline."""
        ...

    def create_graph(
        self,
        checkpointer: "BaseCheckpointSaver[Any] | None" = None,
    ) -> CompiledStateGraph[Any]:
        """Create and compile the LangGraph state machine."""
        ...

    def get_initial_state(self, **kwargs: object) -> StateT_co:
        """Create initial state for a new workflow."""
        ...

    def get_state_class(self) -> type[StateT_co]:
        """Return the state class used by this pipeline."""
        ...
