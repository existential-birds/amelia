"""Pydantic models for API requests and responses."""
from datetime import datetime

from pydantic import BaseModel, Field


class CreateWorkflowRequest(BaseModel):
    """Request to create a new workflow.

    Attributes:
        issue_id: The issue identifier (e.g., PROJ-123).
        worktree_path: Absolute path to the git worktree directory.
        worktree_name: Optional human-readable name for the worktree.
        profile: Optional profile name from settings to use.
    """

    issue_id: str = Field(..., min_length=1, max_length=100)
    worktree_path: str = Field(..., min_length=1, max_length=4096)
    worktree_name: str | None = Field(default=None, max_length=255)
    profile: str | None = Field(default=None, max_length=64)


class RejectWorkflowRequest(BaseModel):
    """Request to reject a workflow plan.

    Attributes:
        feedback: Human-readable explanation for the rejection.
    """

    feedback: str = Field(..., min_length=1, max_length=1000)


class WorkflowResponse(BaseModel):
    """Workflow detail response.

    Attributes:
        id: Unique workflow identifier (UUID).
        issue_id: The issue identifier this workflow is processing.
        status: Current workflow status (pending, in_progress, completed, failed).
        worktree_path: Absolute path to the git worktree directory.
        worktree_name: Human-readable name for the worktree.
        profile: Profile name used for this workflow.
        started_at: Timestamp when the workflow started.
        completed_at: Timestamp when the workflow completed (if finished).
        error: Error message if the workflow failed.
    """

    id: str
    issue_id: str
    status: str
    worktree_path: str
    worktree_name: str | None = None
    profile: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class WorkflowSummary(BaseModel):
    """Workflow summary for list responses.

    Attributes:
        id: Unique workflow identifier (UUID).
        issue_id: The issue identifier this workflow is processing.
        status: Current workflow status.
        worktree_path: Absolute path to the git worktree directory.
        worktree_name: Human-readable name for the worktree.
        started_at: Timestamp when the workflow started.
        current_stage: Current stage in the workflow pipeline (if in progress).
    """

    id: str
    issue_id: str
    status: str
    worktree_path: str
    worktree_name: str | None = None
    started_at: datetime
    current_stage: str | None = None


class WorkflowListResponse(BaseModel):
    """Response for listing workflows.

    Attributes:
        workflows: List of workflow summaries.
        total: Total number of workflows matching the query.
        cursor: Pagination cursor for fetching the next page.
    """

    workflows: list[WorkflowSummary]
    total: int
    cursor: str | None = None
