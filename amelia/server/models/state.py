"""Workflow state models and state machine validation."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field


if TYPE_CHECKING:
    from amelia.pipelines.implementation.state import ImplementationState


class WorkflowStatus(StrEnum):
    """Status for server workflow execution."""

    PENDING = "pending"  # Not yet started
    IN_PROGRESS = "in_progress"  # Currently executing
    BLOCKED = "blocked"  # Awaiting human approval
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"  # Error occurred
    CANCELLED = "cancelled"  # Explicitly cancelled


class WorkflowType(StrEnum):
    """Type of workflow execution."""

    FULL = "full"  # Standard full workflow
    REVIEW = "review"  # Review-only workflow


# State machine validation - prevents invalid transitions
VALID_TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    WorkflowStatus.PENDING: {WorkflowStatus.BLOCKED, WorkflowStatus.IN_PROGRESS, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED},
    WorkflowStatus.IN_PROGRESS: {WorkflowStatus.BLOCKED, WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED},
    WorkflowStatus.BLOCKED: {WorkflowStatus.PENDING, WorkflowStatus.IN_PROGRESS, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED},
    WorkflowStatus.COMPLETED: set(),  # Terminal state
    WorkflowStatus.FAILED: set(),  # Terminal state
    WorkflowStatus.CANCELLED: set(),  # Terminal state
}


class InvalidStateTransitionError(ValueError):
    """Raised when attempting an invalid workflow state transition.

    Attributes:
        current: The current workflow status.
        target: The attempted target status.
    """

    def __init__(self, current: WorkflowStatus, target: WorkflowStatus):
        """Initialize InvalidStateTransitionError.

        Args:
            current: The current workflow status.
            target: The target status that is not allowed from current state.
        """
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition from '{current}' to '{target}'")


def validate_transition(current: WorkflowStatus, target: WorkflowStatus) -> None:
    """Validate that a state transition is allowed.

    Args:
        current: The current workflow status.
        target: The desired new status.

    Raises:
        InvalidStateTransitionError: If the transition is not allowed.
    """
    if target not in VALID_TRANSITIONS[current]:
        raise InvalidStateTransitionError(current, target)


class ServerExecutionState(BaseModel):
    """Extended ExecutionState for server-side workflow tracking.

    This model extends the core ExecutionState with server-specific fields
    for persistence and tracking.

    Attributes:
        id: Unique workflow identifier (UUID).
        issue_id: Issue being worked on.
        worktree_path: Absolute path to git worktree root.
        execution_state: Core orchestration state.
        workflow_status: Current workflow status.
        started_at: When workflow started.
        completed_at: When workflow ended (success or failure).
        current_stage: Currently executing stage.
        failure_reason: Error message when status is "failed".
    """

    id: str = Field(..., description="Unique workflow identifier")
    issue_id: str = Field(..., description="Issue being worked on")
    worktree_path: str = Field(..., description="Absolute path to worktree")
    workflow_type: WorkflowType = Field(
        default=WorkflowType.FULL,
        description="Type of workflow: 'full' for standard, 'review' for review-only",
    )

    execution_state: ImplementationState | None = Field(
        default=None,
        description="Core orchestration state",
    )
    workflow_status: WorkflowStatus = Field(
        default=WorkflowStatus.PENDING,
        description="Current workflow status",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When workflow was created/queued",
    )
    started_at: datetime | None = Field(
        default=None,
        description="When workflow started",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="When workflow ended",
    )
    current_stage: str | None = Field(
        default=None,
        description="Currently executing stage",
    )
    failure_reason: str | None = Field(
        default=None,
        description="Error message when failed",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "wf-123",
                    "issue_id": "ISSUE-456",
                    "worktree_path": "/home/user/project",
                    "workflow_status": "in_progress",
                    "started_at": "2025-01-01T12:00:00Z",
                    "current_stage": "development",
                }
            ]
        }
    }


def rebuild_server_execution_state() -> None:
    """Rebuild ServerExecutionState to resolve forward references.

    Must be called after the application has finished importing to enable
    Pydantic validation of ImplementationState in execution_state field.

    This function imports ImplementationState and its TYPE_CHECKING dependencies,
    then calls model_rebuild() to refresh Pydantic's type resolution.

    Example:
        from amelia.server.models.state import rebuild_server_execution_state
        rebuild_server_execution_state()
    """
    import sys  # noqa: PLC0415

    from amelia.agents.evaluator import EvaluationResult  # noqa: PLC0415
    from amelia.pipelines.implementation.state import ImplementationState  # noqa: PLC0415

    # Inject types into this module's namespace for get_type_hints() compatibility
    module = sys.modules[__name__]
    module.ImplementationState = ImplementationState  # type: ignore[attr-defined]  # Dynamic module injection for LangGraph
    module.EvaluationResult = EvaluationResult  # type: ignore[attr-defined]  # Dynamic module injection for LangGraph

    ServerExecutionState.model_rebuild(
        _types_namespace={
            "ImplementationState": ImplementationState,
            "EvaluationResult": EvaluationResult,
        }
    )
