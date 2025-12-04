"""Response schemas for REST API endpoints."""

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field

from amelia.server.models.state import WorkflowStatus


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
        worktree_name: Name of the worktree
        status: Current workflow status
        started_at: When the workflow was started (optional)
        current_stage: Current agent stage (optional)
    """

    id: Annotated[str, Field(description="Unique workflow identifier")]
    issue_id: Annotated[str, Field(description="Issue identifier")]
    worktree_name: Annotated[str, Field(description="Name of the worktree")]
    status: Annotated[WorkflowStatus, Field(description="Current workflow status")]
    started_at: Annotated[
        datetime | None,
        Field(default=None, description="When the workflow was started"),
    ] = None
    current_stage: Annotated[
        str | None,
        Field(default=None, description="Current agent stage"),
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


class TokenSummary(BaseModel):
    """Summary of token usage and costs.

    Attributes:
        total_tokens: Total tokens consumed
        total_cost_usd: Total cost in USD
    """

    total_tokens: Annotated[int, Field(description="Total tokens consumed")]
    total_cost_usd: Annotated[float, Field(description="Total cost in USD")]


class WorkflowDetailResponse(BaseModel):
    """Detailed workflow information.

    Attributes:
        id: Unique workflow identifier
        issue_id: Issue identifier
        worktree_name: Name of the worktree
        status: Current workflow status
        started_at: When the workflow was started (optional)
        current_stage: Current agent stage (optional)
        plan: Workflow plan/task DAG (optional)
        token_usage: Token usage summary (optional)
        recent_events: Recent workflow events
    """

    id: Annotated[str, Field(description="Unique workflow identifier")]
    issue_id: Annotated[str, Field(description="Issue identifier")]
    worktree_name: Annotated[str, Field(description="Name of the worktree")]
    status: Annotated[WorkflowStatus, Field(description="Current workflow status")]
    started_at: Annotated[
        datetime | None,
        Field(default=None, description="When the workflow was started"),
    ] = None
    current_stage: Annotated[
        str | None,
        Field(default=None, description="Current agent stage"),
    ] = None
    plan: Annotated[
        dict[str, Any] | None,
        Field(default=None, description="Workflow plan/task DAG"),
    ] = None
    token_usage: Annotated[
        TokenSummary | None,
        Field(default=None, description="Token usage summary"),
    ] = None
    recent_events: Annotated[
        list[dict[str, Any]],
        Field(description="Recent workflow events"),
    ]


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
