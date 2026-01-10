"""Workflow state models and state machine validation."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from amelia.core.state import ExecutionState


# Type alias for workflow status
WorkflowStatus = Literal[
    "pending",  # Not yet started
    "in_progress",  # Currently executing
    "blocked",  # Awaiting human approval
    "completed",  # Successfully finished
    "failed",  # Error occurred
    "cancelled",  # Explicitly cancelled
]


# State machine validation - prevents invalid transitions
VALID_TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    "pending": {"in_progress", "cancelled", "failed"},  # Can fail during startup
    "in_progress": {"blocked", "completed", "failed", "cancelled"},
    "blocked": {"in_progress", "failed", "cancelled"},
    "completed": set(),  # Terminal state
    "failed": set(),  # Terminal state
    "cancelled": set(),  # Terminal state
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
        stage_timestamps: When each stage started.
        current_stage: Currently executing stage.
        failure_reason: Error message when status is "failed".
        consecutive_errors: Number of consecutive transient errors (resets on success).
        last_error_context: Context from the most recent error (for debugging).
    """

    id: str = Field(..., description="Unique workflow identifier")
    issue_id: str = Field(..., description="Issue being worked on")
    worktree_path: str = Field(..., description="Absolute path to worktree")
    workflow_type: Literal["full", "review"] = Field(
        default="full",
        description="Type of workflow: 'full' for standard, 'review' for review-only",
    )

    execution_state: ExecutionState | None = Field(
        default=None,
        description="Core orchestration state",
    )
    workflow_status: WorkflowStatus = Field(
        default="pending",
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
    planned_at: datetime | None = Field(
        default=None,
        description="When workflow planning (architect stage) completed",
    )
    stage_timestamps: dict[str, datetime] = Field(
        default_factory=dict,
        description="When each stage started",
    )
    current_stage: str | None = Field(
        default=None,
        description="Currently executing stage",
    )
    failure_reason: str | None = Field(
        default=None,
        description="Error message when failed",
    )
    consecutive_errors: int = Field(
        default=0,
        description="Number of consecutive transient errors (resets on success)",
    )
    last_error_context: str | None = Field(
        default=None,
        description="Context from the most recent error (for debugging)",
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

    @property
    def is_planned(self) -> bool:
        """Return True if the workflow has completed planning."""
        return self.planned_at is not None
