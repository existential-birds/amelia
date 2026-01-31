"""Response schemas for REST API endpoints."""

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field

from amelia.server.models.state import WorkflowStatus
from amelia.server.models.tokens import TokenSummary


class CreateWorkflowResponse(BaseModel):
    """Response from creating a new workflow.

    Attributes:
        id: Unique workflow identifier
        status: Initial workflow status
        message: Human-readable status message
    """

    id: Annotated[str, Field(description="Unique workflow identifier")]
    status: Annotated[WorkflowStatus, Field(description="Initial workflow status")]
    message: Annotated[str, Field(description="Human-readable status message")]


class WorkflowSummary(BaseModel):
    """Summary of a workflow for list views.

    Attributes:
        id: Unique workflow identifier
        issue_id: Issue identifier
        worktree_path: Absolute path to worktree
        profile: Profile name used for this workflow (optional)
        status: Current workflow status
        started_at: When the workflow was started (optional)
        total_cost_usd: Total cost in USD (optional)
        total_tokens: Total tokens consumed (optional)
        total_duration_ms: Total execution duration in milliseconds (optional)
    """

    id: Annotated[str, Field(description="Unique workflow identifier")]
    issue_id: Annotated[str, Field(description="Issue identifier")]
    worktree_path: Annotated[str, Field(description="Absolute path to worktree")]
    profile: Annotated[
        str | None,
        Field(default=None, description="Profile name used for this workflow"),
    ] = None
    status: Annotated[WorkflowStatus, Field(description="Current workflow status")]
    created_at: Annotated[
        datetime,
        Field(description="When the workflow was created/queued"),
    ]
    started_at: Annotated[
        datetime | None,
        Field(default=None, description="When the workflow was started"),
    ] = None
    total_cost_usd: Annotated[
        float | None,
        Field(default=None, description="Total cost in USD"),
    ] = None
    total_tokens: Annotated[
        int | None,
        Field(
            default=None,
            description="Total combined tokens (sum of input_tokens + output_tokens)",
        ),
    ] = None
    total_duration_ms: Annotated[
        int | None,
        Field(default=None, description="Total execution duration in milliseconds"),
    ] = None


class WorkflowListResponse(BaseModel):
    """Response containing a list of workflows.

    Attributes:
        workflows: List of workflow summaries
        total: Total number of workflows matching query
        cursor: Pagination cursor for next page (optional)
        has_more: Whether more results are available
    """

    workflows: Annotated[
        list[WorkflowSummary],
        Field(description="List of workflow summaries"),
    ]
    total: Annotated[int, Field(description="Total number of workflows")]
    cursor: Annotated[
        str | None,
        Field(default=None, description="Pagination cursor for next page"),
    ] = None
    has_more: Annotated[
        bool,
        Field(default=False, description="Whether more results are available"),
    ] = False


class WorkflowDetailResponse(BaseModel):
    """Detailed workflow information.

    Attributes:
        id: Unique workflow identifier
        issue_id: Issue identifier
        worktree_path: Absolute path to worktree
        status: Current workflow status
        created_at: When the workflow was created/queued
        started_at: When the workflow was started (optional)
        completed_at: When the workflow ended (optional)
        failure_reason: Error message when failed (optional)
        goal: High-level goal for agentic execution (optional)
        plan_markdown: Full plan markdown content from Architect (optional)
        plan_path: Path where the plan markdown was saved (optional)
        token_usage: Token usage summary (optional)
        recent_events: Recent workflow events
        final_response: Final response from the agent when complete (optional)
    """

    id: Annotated[str, Field(description="Unique workflow identifier")]
    issue_id: Annotated[str, Field(description="Issue identifier")]
    worktree_path: Annotated[str, Field(description="Absolute path to worktree")]
    status: Annotated[WorkflowStatus, Field(description="Current workflow status")]
    created_at: Annotated[
        datetime,
        Field(description="When the workflow was created/queued"),
    ]
    started_at: Annotated[
        datetime | None,
        Field(default=None, description="When the workflow was started"),
    ] = None
    completed_at: Annotated[
        datetime | None,
        Field(default=None, description="When the workflow ended"),
    ] = None
    failure_reason: Annotated[
        str | None,
        Field(default=None, description="Error message when failed"),
    ] = None
    goal: Annotated[
        str | None,
        Field(default=None, description="High-level goal for agentic execution"),
    ] = None
    plan_markdown: Annotated[
        str | None,
        Field(default=None, description="Full plan markdown content from Architect"),
    ] = None
    plan_path: Annotated[
        str | None,
        Field(default=None, description="Path where the plan markdown was saved"),
    ] = None
    token_usage: Annotated[
        TokenSummary | None,
        Field(default=None, description="Token usage summary"),
    ] = None
    recent_events: Annotated[
        list[dict[str, Any]],
        Field(description="Recent workflow events"),
    ]
    final_response: Annotated[
        str | None,
        Field(default=None, description="Final response from the agent"),
    ] = None


class ActionResponse(BaseModel):
    """Response for workflow action endpoints (approve/reject/cancel).

    Attributes:
        status: Action status (approved, rejected, cancelled)
        workflow_id: ID of the affected workflow
    """

    status: Annotated[str, Field(description="Action status")]
    workflow_id: Annotated[str, Field(description="Workflow ID")]


class ErrorResponse(BaseModel):
    """Error response for failed requests.

    Attributes:
        error: Human-readable error message
        code: Machine-readable error code
        details: Optional additional error details
    """

    error: Annotated[str, Field(description="Human-readable error message")]
    code: Annotated[str, Field(description="Machine-readable error code")]
    details: Annotated[
        dict[str, Any] | None,
        Field(default=None, description="Optional additional error details"),
    ] = None


class BatchStartResponse(BaseModel):
    """Response from batch start operation.

    Attributes:
        started: Workflow IDs that were successfully started.
        errors: Map of workflow_id to error message for failures.
    """

    started: Annotated[
        list[str],
        Field(description="Workflow IDs that were successfully started"),
    ]
    errors: Annotated[
        dict[str, str],
        Field(description="Map of workflow_id to error message for failures"),
    ]


class SetPlanResponse(BaseModel):
    """Response from setting an external plan on a workflow.

    Attributes:
        goal: Extracted goal from the plan.
        key_files: List of key files from the plan.
        total_tasks: Number of tasks in the plan.
    """

    goal: Annotated[str, Field(description="Extracted goal from the plan")]
    key_files: Annotated[list[str], Field(description="List of key files from the plan")]
    total_tasks: Annotated[int, Field(description="Number of tasks in the plan")]
