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
        task_title: Optional task title for noop tracker (bypasses issue lookup).
        task_description: Optional task description (requires task_title).
    """

    issue_id: str = Field(..., min_length=1, max_length=100)
    worktree_path: str = Field(..., min_length=1, max_length=4096)
    worktree_name: str | None = Field(default=None, max_length=255)
    profile: str | None = Field(default=None, max_length=64)
    task_title: str | None = Field(default=None, max_length=500)
    task_description: str | None = Field(default=None, max_length=5000)


class CreateReviewWorkflowRequest(BaseModel):
    """Request to create a review workflow.

    Attributes:
        diff_content: Git diff content to review.
        worktree_path: Absolute path to the git worktree directory.
        worktree_name: Optional human-readable name for the worktree.
        profile: Optional profile name from settings to use.
    """

    diff_content: str = Field(..., min_length=1)
    worktree_path: str = Field(..., min_length=1, max_length=4096)
    worktree_name: str | None = Field(default=None, max_length=255)
    profile: str | None = Field(default=None, max_length=64)


class CreateWorkflowResponse(BaseModel):
    """Response from creating a new workflow.

    Attributes:
        id: Unique workflow identifier.
        status: Initial workflow status (typically 'pending').
        message: Human-readable status message.
    """

    id: str
    status: str
    message: str


class RejectWorkflowRequest(BaseModel):
    """Request to reject a workflow plan.

    Attributes:
        feedback: Human-readable explanation for the rejection.
    """

    feedback: str = Field(..., min_length=1, max_length=1000)


class WorkflowResponse(BaseModel):
    """Workflow detail response (aligned with server's WorkflowDetailResponse).

    Attributes:
        id: Unique workflow identifier (UUID).
        issue_id: The issue identifier this workflow is processing.
        status: Current workflow status (pending, in_progress, completed, failed).
        worktree_path: Absolute path to the git worktree directory.
        worktree_name: Human-readable name for the worktree.
        started_at: Timestamp when the workflow started (optional).
        completed_at: Timestamp when the workflow completed (if finished).
        failure_reason: Error message if the workflow failed.
        current_stage: Current agent stage in the workflow.
    """

    id: str
    issue_id: str
    status: str
    worktree_path: str
    worktree_name: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None
    current_stage: str | None = None


class WorkflowSummary(BaseModel):
    """Workflow summary for list responses.

    Attributes:
        id: Unique workflow identifier (UUID).
        issue_id: The issue identifier this workflow is processing.
        status: Current workflow status.
        worktree_name: Human-readable name for the worktree.
        started_at: Timestamp when the workflow started.
        current_stage: Current stage in the workflow pipeline (if in progress).
    """

    id: str
    issue_id: str
    status: str
    worktree_name: str
    started_at: datetime | None = None
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
