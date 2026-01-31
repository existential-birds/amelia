"""Workflow state models and state machine validation."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


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
    WorkflowStatus.FAILED: {WorkflowStatus.IN_PROGRESS},  # Resumable via recovery
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


class PlanCache(BaseModel):
    """Cached plan data synced from LangGraph checkpoint.

    This model stores plan-related fields from ImplementationState
    for efficient access without deserializing the full checkpoint.

    Attributes:
        goal: The high-level goal for the implementation.
        plan_markdown: The full plan in markdown format.
        plan_path: Path to the plan file on disk.
        tool_calls: List of tool calls made during planning.
        tool_results: List of tool results from planning.
        total_tasks: Total number of tasks in the plan.
        current_task_index: Index of the current task being executed.
    """

    goal: str | None = None
    plan_markdown: str | None = None
    plan_path: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    total_tasks: int | None = None
    current_task_index: int | None = None

    @classmethod
    def from_checkpoint_values(cls, values: dict[str, Any]) -> PlanCache:
        """Create PlanCache from LangGraph checkpoint values.

        Args:
            values: Checkpoint values dict from graph.aget_state().

        Returns:
            PlanCache instance with extracted plan data.
        """
        tool_calls = values.get("tool_calls", [])
        plan_path: str | None = None

        # Extract plan_path from Write tool calls
        for tc in tool_calls:
            # Handle both dict and Pydantic model tool calls
            if isinstance(tc, dict):
                tool_name = tc.get("tool_name")
                tool_input = tc.get("tool_input", {})
            else:
                tool_name = getattr(tc, "tool_name", None)
                tool_input = getattr(tc, "tool_input", None) or {}

            if (
                tool_name == "write_file"
                and isinstance(tool_input, dict)
                and "file_path" in tool_input
            ):
                plan_path = str(tool_input["file_path"])
                break

        # Serialize tool_calls and tool_results to dicts if they're Pydantic models
        serialized_tool_calls = []
        for tc in tool_calls:
            if hasattr(tc, "model_dump"):
                serialized_tool_calls.append(tc.model_dump(mode="json"))
            elif isinstance(tc, dict):
                serialized_tool_calls.append(tc)

        tool_results = values.get("tool_results", [])
        serialized_tool_results = []
        for tr in tool_results:
            if hasattr(tr, "model_dump"):
                serialized_tool_results.append(tr.model_dump(mode="json"))
            elif isinstance(tr, dict):
                serialized_tool_results.append(tr)

        return cls(
            goal=values.get("goal"),
            plan_markdown=values.get("plan_markdown"),
            plan_path=plan_path,
            tool_calls=serialized_tool_calls,
            tool_results=serialized_tool_results,
            total_tasks=values.get("total_tasks"),
            current_task_index=values.get("current_task_index"),
        )


class ServerExecutionState(BaseModel):
    """Server-side workflow tracking state.

    This model stores workflow metadata for persistence and tracking.
    The actual ImplementationState lives in LangGraph checkpoints.

    Attributes:
        id: Unique workflow identifier (UUID).
        issue_id: Issue being worked on.
        worktree_path: Absolute path to git worktree root.
        workflow_status: Current workflow status.
        started_at: When workflow started.
        completed_at: When workflow ended (success or failure).
        failure_reason: Error message when status is "failed".
    """

    id: str = Field(..., description="Unique workflow identifier")
    issue_id: str = Field(..., description="Issue being worked on")
    worktree_path: str = Field(..., description="Absolute path to worktree")
    workflow_type: WorkflowType = Field(
        default=WorkflowType.FULL,
        description="Type of workflow: 'full' for standard, 'review' for review-only",
    )
    profile_id: str | None = Field(
        default=None,
        description="Profile ID used to configure the workflow",
    )
    plan_cache: PlanCache | None = Field(
        default=None,
        description="Cached plan data synced from LangGraph checkpoint",
    )
    issue_cache: str | None = Field(
        default=None,
        description="Serialized Issue JSON for reconstructing initial state",
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
                }
            ]
        }
    }
