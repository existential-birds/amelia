"""Response schemas for REST API endpoints."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from amelia.server.models.state import WorkflowStatus
from amelia.server.models.tokens import TokenSummary


class PRCommentResponse(BaseModel):
    """Resolution status of a single PR review comment."""

    comment_id: int = Field(description="GitHub comment ID")
    file_path: str | None = Field(default=None, description="File path the comment references")
    line: int | None = Field(default=None, description="Line number the comment references")
    body: str = Field(default="", description="Truncated comment body (max 200 chars)")
    author: str | None = Field(default=None, description="Comment author login")
    status: str = Field(default="skipped", description="Fix status: fixed, failed, or skipped")
    status_reason: str | None = Field(default=None, description="Reason for the status")
    resolved: bool = Field(default=False, description="Whether the GitHub thread was resolved")
    replied: bool = Field(default=False, description="Whether the bot replied to the thread")


class CreateWorkflowResponse(BaseModel):
    """Response from creating a new workflow."""

    id: uuid.UUID = Field(description="Unique workflow identifier")
    status: WorkflowStatus = Field(description="Initial workflow status")
    message: str = Field(description="Human-readable status message")


class WorkflowSummary(BaseModel):
    """Summary of a workflow for list views."""

    id: uuid.UUID = Field(description="Unique workflow identifier")
    issue_id: str = Field(description="Issue identifier")
    worktree_path: str = Field(description="Absolute path to worktree")
    profile: str | None = Field(default=None, description="Profile name used for this workflow")
    status: WorkflowStatus = Field(description="Current workflow status")
    created_at: datetime = Field(description="When the workflow was created/queued")
    started_at: datetime | None = Field(default=None, description="When the workflow was started")
    total_cost_usd: float | None = Field(default=None, description="Total cost in USD")
    total_tokens: int | None = Field(
        default=None,
        description="Total combined tokens (sum of input_tokens + output_tokens)",
    )
    total_duration_ms: int | None = Field(
        default=None, description="Total execution duration in milliseconds"
    )
    pipeline_type: str | None = Field(
        default=None, description="Pipeline type (e.g. full, review, pr_auto_fix)"
    )
    pr_number: int | None = Field(default=None, description="PR number for PR Fix workflows")
    pr_title: str | None = Field(default=None, description="PR title for PR Fix workflows")
    pr_comment_count: int | None = Field(
        default=None, description="Comment count for PR Fix workflows"
    )


class WorkflowListResponse(BaseModel):
    """Response containing a list of workflows."""

    workflows: list[WorkflowSummary] = Field(description="List of workflow summaries")
    total: int = Field(description="Total number of workflows")
    cursor: str | None = Field(default=None, description="Pagination cursor for next page")
    has_more: bool = Field(default=False, description="Whether more results are available")


class WorkflowDetailResponse(BaseModel):
    """Detailed workflow information."""

    id: uuid.UUID = Field(description="Unique workflow identifier")
    issue_id: str = Field(description="Issue identifier")
    worktree_path: str = Field(description="Absolute path to worktree")
    status: WorkflowStatus = Field(description="Current workflow status")
    created_at: datetime = Field(description="When the workflow was created/queued")
    started_at: datetime | None = Field(default=None, description="When the workflow was started")
    completed_at: datetime | None = Field(default=None, description="When the workflow ended")
    failure_reason: str | None = Field(default=None, description="Error message when failed")
    goal: str | None = Field(default=None, description="High-level goal for agentic execution")
    plan_markdown: str | None = Field(
        default=None, description="Full plan markdown content from Architect"
    )
    plan_path: str | None = Field(
        default=None, description="Path where the plan markdown was saved"
    )
    token_usage: TokenSummary | None = Field(default=None, description="Token usage summary")
    recent_events: list[dict[str, Any]] = Field(description="Recent workflow events")
    final_response: str | None = Field(
        default=None, description="Final response from the agent"
    )
    pipeline_type: str | None = Field(
        default=None, description="Pipeline type (e.g. full, review, pr_auto_fix)"
    )
    pr_number: int | None = Field(default=None, description="PR number for PR Fix workflows")
    pr_title: str | None = Field(default=None, description="PR title for PR Fix workflows")
    pr_comment_count: int | None = Field(
        default=None, description="Comment count for PR Fix workflows"
    )
    pr_comments: list[PRCommentResponse] | None = Field(
        default=None, description="PR comment resolution data from issue_cache"
    )


class ActionResponse(BaseModel):
    """Response for workflow action endpoints (approve/reject/cancel)."""

    status: str = Field(description="Action status")
    workflow_id: uuid.UUID = Field(description="Workflow ID")


class ErrorResponse(BaseModel):
    """Error response for failed requests."""

    error: str = Field(description="Human-readable error message")
    code: str = Field(description="Machine-readable error code")
    details: dict[str, Any] | None = Field(
        default=None, description="Optional additional error details"
    )


class BatchStartResponse(BaseModel):
    """Response from batch start operation."""

    started: list[str] = Field(description="Workflow IDs that were successfully started")
    errors: dict[str, str] = Field(
        description="Map of workflow_id to error message for failures"
    )


class FileEntry(BaseModel):
    """A file entry in a directory listing."""

    name: str = Field(description="Filename")
    relative_path: str = Field(description="Path relative to working_dir")
    size_bytes: int = Field(description="File size in bytes")
    modified_at: str = Field(description="ISO 8601 modification timestamp")


class FileListResponse(BaseModel):
    """Response from listing files in a directory."""

    files: list[FileEntry] = Field(description="List of files")
    directory: str = Field(description="Relative directory that was listed")


class SetPlanResponse(BaseModel):
    """Response from setting an external plan on a workflow."""

    status: Literal["ready", "invalid"] = Field(
        description="'ready' when valid, 'invalid' when validation fails"
    )
    total_tasks: int = Field(description="Number of tasks in the plan")
    goal: str = Field(description="Extracted goal from the plan")
    key_files: list[str] = Field(
        default_factory=list, description="Key files found in the plan"
    )
    validation_issues: list[str] | None = Field(
        default=None, description="Validation issues (present when status='invalid')"
    )
