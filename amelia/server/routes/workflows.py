"""Workflow management routes and exception handlers."""

from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic_core import ValidationError

from amelia.server.database import WorkflowRepository
from amelia.server.dependencies import get_orchestrator, get_repository
from amelia.server.exceptions import (
    ConcurrencyLimitError,
    FileOperationError,
    InvalidStateError,
    InvalidWorktreeError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.server.models.requests import (
    BatchStartRequest,
    CreateReviewWorkflowRequest,
    CreateWorkflowRequest,
    RejectRequest,
    SetPlanRequest,
)
from amelia.server.models.responses import (
    ActionResponse,
    BatchStartResponse,
    CreateWorkflowResponse,
    ErrorResponse,
    SetPlanResponse,
    WorkflowDetailResponse,
    WorkflowListResponse,
    WorkflowSummary,
)
from amelia.server.models.state import WorkflowStatus
from amelia.server.orchestrator.service import OrchestratorService


# Create the workflows router
router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreateWorkflowResponse)
async def create_workflow(
    request: CreateWorkflowRequest,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> CreateWorkflowResponse:
    """Create a new workflow.

    Args:
        request: Workflow creation request.
        orchestrator: Orchestrator service dependency.

    Returns:
        CreateWorkflowResponse with workflow ID and initial status.

    Raises:
        WorkflowConflictError: If worktree is already in use.
        ConcurrencyLimitError: If concurrent workflow limit is reached.
    """
    # Let orchestrator handle everything - it will raise appropriate exceptions
    # Choose method based on start/plan_now flags
    if request.start:
        # Immediate execution (existing behavior)
        workflow_id = await orchestrator.start_workflow(
            issue_id=request.issue_id,
            worktree_path=request.worktree_path,
            profile=request.profile,
            driver=request.driver,
            task_title=request.task_title,
            task_description=request.task_description,
        )
    elif request.plan_now:
        # Queue with planning (run Architect, then queue)
        workflow_id = await orchestrator.queue_and_plan_workflow(request)
    else:
        # Queue without planning
        workflow_id = await orchestrator.queue_workflow(request)

    logger.info("Created workflow", workflow_id=workflow_id, issue_id=request.issue_id, start=request.start, plan_now=request.plan_now)

    return CreateWorkflowResponse(
        id=workflow_id,
        status=WorkflowStatus.PENDING,
        message=f"Workflow created for issue {request.issue_id}",
    )


@router.post("/review", status_code=status.HTTP_201_CREATED, response_model=CreateWorkflowResponse)
async def create_review_workflow(
    request: CreateReviewWorkflowRequest,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> CreateWorkflowResponse:
    """Create a review-fix workflow.

    Starts a review-fix loop that runs autonomously until approved
    or max iterations (3) reached.

    Args:
        request: Review workflow creation request with diff content.
        orchestrator: Orchestrator service dependency.

    Returns:
        CreateWorkflowResponse with workflow ID and initial status.
    """
    workflow_id = await orchestrator.start_review_workflow(
        diff_content=request.diff_content,
        worktree_path=request.worktree_path,
        profile=request.profile,
    )

    logger.info("Created review workflow", workflow_id=workflow_id)

    return CreateWorkflowResponse(
        id=workflow_id,
        status=WorkflowStatus.PENDING,
        message="Review workflow created",
    )


@router.get("", response_model=WorkflowListResponse)
async def list_workflows(
    status: WorkflowStatus | None = None,
    worktree: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    repository: WorkflowRepository = Depends(get_repository),
) -> WorkflowListResponse:
    """List workflows with optional filtering and pagination.

    Args:
        status: Filter by workflow status.
        worktree: Filter by worktree path.
        limit: Maximum number of results (1-100).
        cursor: Pagination cursor from previous response.
        repository: Workflow repository dependency.

    Returns:
        WorkflowListResponse with workflows, total count, and pagination info.

    Raises:
        HTTPException: 400 if cursor is invalid.
    """
    # Decode cursor
    after_started_at: datetime | None = None
    after_id: str | None = None
    if cursor:
        try:
            decoded = base64.b64decode(cursor).decode()
            after_started_at_str, after_id = decoded.split("|", 1)
            after_started_at = datetime.fromisoformat(after_started_at_str)
        except (ValueError, UnicodeDecodeError) as e:
            logger.warning("Invalid cursor", error=str(e))
            raise HTTPException(
                status_code=400,
                detail="Invalid cursor format",
            ) from e

    # Resolve worktree path to canonical form (e.g., /tmp -> /private/tmp on macOS)
    resolved_worktree = str(Path(worktree).resolve()) if worktree else None

    # Fetch limit+1 to detect has_more
    workflows = await repository.list_workflows(
        status=status,
        worktree_path=resolved_worktree,
        limit=limit + 1,
        after_started_at=after_started_at,
        after_id=after_id,
    )

    has_more = len(workflows) > limit
    if has_more:
        workflows = workflows[:limit]

    # Build next cursor
    next_cursor: str | None = None
    if has_more and workflows:
        last = workflows[-1]
        if last.started_at:
            cursor_data = f"{last.started_at.isoformat()}|{last.id}"
            next_cursor = base64.b64encode(cursor_data.encode()).decode()

    total = await repository.count_workflows(status=status, worktree_path=resolved_worktree)

    # Fetch all token summaries in a single batch query (solves N+1 problem)
    workflow_ids = [w.id for w in workflows]
    token_summaries = await repository.get_token_summaries_batch(workflow_ids)

    # Build workflow summaries with token data
    workflow_summaries = []
    for w in workflows:
        token_summary = token_summaries.get(w.id)
        # Extract profile from execution state if available
        profile = w.execution_state.profile_id if w.execution_state else None
        workflow_summaries.append(
            WorkflowSummary(
                id=w.id,
                issue_id=w.issue_id,
                worktree_path=w.worktree_path,
                profile=profile,
                status=w.workflow_status,
                created_at=w.created_at,
                started_at=w.started_at,
                current_stage=w.current_stage,
                total_cost_usd=token_summary.total_cost_usd if token_summary else None,
                total_tokens=(
                    token_summary.total_input_tokens + token_summary.total_output_tokens
                    if token_summary
                    else None
                ),
                total_duration_ms=token_summary.total_duration_ms if token_summary else None,
            )
        )

    return WorkflowListResponse(
        workflows=workflow_summaries,
        total=total,
        cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/active", response_model=WorkflowListResponse)
async def list_active_workflows(
    worktree: str | None = None,
    repository: WorkflowRepository = Depends(get_repository),
) -> WorkflowListResponse:
    """List all active workflows.

    Active workflows are those in pending, planning, in_progress, or blocked status.

    Args:
        worktree: Filter by worktree path.
        repository: Workflow repository dependency.

    Returns:
        WorkflowListResponse with active workflows.
    """
    # Resolve worktree path to canonical form (e.g., /tmp -> /private/tmp on macOS)
    resolved_worktree = str(Path(worktree).resolve()) if worktree else None

    workflows = await repository.list_active(worktree_path=resolved_worktree)

    # Fetch all token summaries in a single batch query (solves N+1 problem)
    workflow_ids = [w.id for w in workflows]
    token_summaries = await repository.get_token_summaries_batch(workflow_ids)

    # Build workflow summaries with token data
    workflow_summaries = []
    for w in workflows:
        token_summary = token_summaries.get(w.id)
        # Extract profile from execution state if available
        profile = w.execution_state.profile_id if w.execution_state else None
        workflow_summaries.append(
            WorkflowSummary(
                id=w.id,
                issue_id=w.issue_id,
                worktree_path=w.worktree_path,
                profile=profile,
                status=w.workflow_status,
                created_at=w.created_at,
                started_at=w.started_at,
                current_stage=w.current_stage,
                total_cost_usd=token_summary.total_cost_usd if token_summary else None,
                total_tokens=(
                    token_summary.total_input_tokens + token_summary.total_output_tokens
                    if token_summary
                    else None
                ),
                total_duration_ms=token_summary.total_duration_ms if token_summary else None,
            )
        )

    return WorkflowListResponse(
        workflows=workflow_summaries,
        total=len(workflows),
        has_more=False,
    )


@router.post("/start-batch", response_model=BatchStartResponse)
async def start_batch(
    request: BatchStartRequest,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> BatchStartResponse:
    """Start multiple pending workflows.

    Starts workflows sequentially, respecting concurrency limits.
    Partial success is possible.

    Args:
        request: Batch start request with optional workflow_ids filter.
        orchestrator: Orchestrator service dependency.

    Returns:
        BatchStartResponse with started IDs and errors.
    """
    return await orchestrator.start_batch_workflows(request)


@router.get("/{workflow_id}", response_model=WorkflowDetailResponse)
async def get_workflow(
    workflow_id: str,
    repository: WorkflowRepository = Depends(get_repository),
) -> WorkflowDetailResponse:
    """Get workflow by ID.

    Args:
        workflow_id: Unique workflow identifier.
        repository: Workflow repository dependency.

    Returns:
        WorkflowDetailResponse with full workflow details.

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist.
    """
    workflow = await repository.get(workflow_id)
    if workflow is None:
        raise WorkflowNotFoundError(workflow_id=workflow_id)

    # Fetch token usage summary
    token_usage = await repository.get_token_summary(workflow_id)

    # Fetch recent events from database
    events = await repository.get_recent_events(workflow_id, limit=50)
    recent_events = [event.model_dump(mode="json") for event in events]

    # Extract agentic execution fields from execution_state
    goal = workflow.execution_state.goal if workflow.execution_state else None
    plan_markdown = workflow.execution_state.plan_markdown if workflow.execution_state else None
    plan_path = str(workflow.execution_state.plan_path) if workflow.execution_state and workflow.execution_state.plan_path else None

    # DEBUG: Log what API sees from database
    logger.info(
        "API returning workflow detail",
        workflow_id=workflow_id,
        has_execution_state=workflow.execution_state is not None,
        goal=goal[:100] if goal else None,
        has_plan=plan_markdown is not None,
        plan_len=len(plan_markdown) if plan_markdown else 0,
    )
    tool_calls = []
    tool_results = []
    final_response = None

    if workflow.execution_state:
        tool_calls = [tc.model_dump(mode="json") for tc in workflow.execution_state.tool_calls]
        tool_results = [tr.model_dump(mode="json") for tr in workflow.execution_state.tool_results]
        final_response = workflow.execution_state.final_response

    return WorkflowDetailResponse(
        id=workflow.id,
        issue_id=workflow.issue_id,
        worktree_path=workflow.worktree_path,
        status=workflow.workflow_status,
        created_at=workflow.created_at,
        started_at=workflow.started_at,
        completed_at=workflow.completed_at,
        failure_reason=workflow.failure_reason,
        current_stage=workflow.current_stage,
        goal=goal,
        plan_markdown=plan_markdown,
        plan_path=plan_path,
        token_usage=token_usage,
        recent_events=recent_events,
        tool_calls=tool_calls,
        tool_results=tool_results,
        final_response=final_response,
    )


@router.post("/{workflow_id}/cancel", response_model=ActionResponse)
async def cancel_workflow(
    workflow_id: str,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> ActionResponse:
    """Cancel an active workflow.

    Args:
        workflow_id: Unique workflow identifier.
        orchestrator: Orchestrator service dependency.

    Returns:
        ActionResponse with status and workflow_id.

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist.
        InvalidStateError: If workflow is not in a cancellable state.
    """
    await orchestrator.cancel_workflow(workflow_id)
    logger.info("Cancelled workflow", workflow_id=workflow_id)
    return ActionResponse(status="cancelled", workflow_id=workflow_id)


@router.post("/{workflow_id}/approve", response_model=ActionResponse)
async def approve_workflow(
    workflow_id: str,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> ActionResponse:
    """Approve a blocked workflow's plan.

    Args:
        workflow_id: Unique workflow identifier.
        orchestrator: Orchestrator service dependency.

    Returns:
        ActionResponse with status and workflow_id.

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist.
        InvalidStateError: If workflow is not in blocked state.
    """
    await orchestrator.approve_workflow(workflow_id)
    logger.info("Approved workflow", workflow_id=workflow_id)
    return ActionResponse(status="approved", workflow_id=workflow_id)


@router.post("/{workflow_id}/reject", response_model=ActionResponse)
async def reject_workflow(
    workflow_id: str,
    request: RejectRequest,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> ActionResponse:
    """Reject a blocked workflow's plan.

    Args:
        workflow_id: Unique workflow identifier.
        request: Rejection request with feedback.
        orchestrator: Orchestrator service dependency.

    Returns:
        ActionResponse with status and workflow_id.

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist.
        InvalidStateError: If workflow is not in blocked state.
    """
    await orchestrator.reject_workflow(workflow_id, request.feedback)
    logger.info("Rejected workflow", workflow_id=workflow_id, feedback=request.feedback)
    return ActionResponse(status="rejected", workflow_id=workflow_id)


@router.post(
    "/{workflow_id}/start",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ActionResponse,
)
async def start_workflow(
    workflow_id: str,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> ActionResponse:
    """Start a pending workflow.

    Transitions a workflow from pending to in_progress state and
    spawns an execution task.

    Args:
        workflow_id: Unique workflow identifier.
        orchestrator: Orchestrator service dependency.

    Returns:
        202 Accepted with workflow_id and status.

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist (404).
        InvalidStateError: If workflow is not in pending state (422 via global handler).
        WorkflowConflictError: If worktree already has an active workflow (409).
    """
    try:
        await orchestrator.start_pending_workflow(workflow_id)
        logger.info("Started pending workflow", workflow_id=workflow_id)
        return ActionResponse(workflow_id=workflow_id, status="started")
    except WorkflowNotFoundError as e:
        raise HTTPException(status_code=404, detail="Workflow not found") from e
    except WorkflowConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/{workflow_id}/plan", response_model=SetPlanResponse)
async def set_workflow_plan(
    workflow_id: str,
    request: SetPlanRequest,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> SetPlanResponse:
    """Set or replace the plan for a queued workflow.

    Args:
        workflow_id: The workflow ID.
        request: Plan content or file path.
        orchestrator: Orchestrator service dependency.

    Returns:
        SetPlanResponse with extracted plan summary.

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist (404).
        InvalidStateError: If workflow not in pending/planning state (422).
        WorkflowConflictError: If plan exists and force=False (409).
    """
    result = await orchestrator.set_workflow_plan(
        workflow_id=workflow_id,
        plan_file=request.plan_file,
        plan_content=request.plan_content,
        force=request.force,
    )

    return SetPlanResponse(
        goal=result["goal"],
        key_files=result["key_files"],
        total_tasks=result["total_tasks"],
    )


@router.post("/{workflow_id}/replan", response_model=ActionResponse)
async def replan_workflow(
    workflow_id: str,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> ActionResponse:
    """Replan a blocked workflow by regenerating the Architect plan.

    Deletes the stale checkpoint, clears plan fields, and spawns a
    new planning task. The workflow transitions from blocked to planning.

    Args:
        workflow_id: Unique workflow identifier.
        orchestrator: Orchestrator service dependency.

    Returns:
        ActionResponse with status "planning" and workflow_id.

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist.
        InvalidStateError: If workflow is not in blocked state.
        WorkflowConflictError: If planning task is already running.
    """
    await orchestrator.replan_workflow(workflow_id)
    logger.info("Replan started", workflow_id=workflow_id)
    return ActionResponse(status="planning", workflow_id=workflow_id)


def configure_exception_handlers(app: FastAPI) -> None:
    """Configure exception handlers for the FastAPI application.

    Registers handlers for all custom exceptions to return appropriate
    HTTP status codes and error responses.

    Args:
        app: FastAPI application instance.
    """

    @app.exception_handler(WorkflowConflictError)
    async def workflow_conflict_handler(
        request: Request, exc: WorkflowConflictError
    ) -> JSONResponse:
        """Handle WorkflowConflictError with 409 Conflict.

        Args:
            request: The incoming request.
            exc: The exception instance.

        Returns:
            JSONResponse with 409 status code.
        """
        logger.warning("Workflow conflict", workflow_id=exc.workflow_id, worktree_path=exc.worktree_path)
        error = ErrorResponse(
            code="WORKFLOW_CONFLICT",
            error=str(exc),
            details={
                "workflow_id": exc.workflow_id,
                "worktree_path": exc.worktree_path,
            },
        )
        return JSONResponse(
            status_code=409,
            content=error.model_dump(),
        )

    @app.exception_handler(ConcurrencyLimitError)
    async def concurrency_limit_handler(
        request: Request, exc: ConcurrencyLimitError
    ) -> JSONResponse:
        """Handle ConcurrencyLimitError with 429 Too Many Requests.

        Args:
            request: The incoming request.
            exc: The exception instance.

        Returns:
            JSONResponse with 429 status code and Retry-After header.
        """
        logger.warning("Concurrency limit exceeded", current_count=exc.current_count, max_concurrent=exc.max_concurrent)
        error = ErrorResponse(
            code="CONCURRENCY_LIMIT",
            error=str(exc),
            details={
                "current": exc.current_count,
                "limit": exc.max_concurrent,
            },
        )
        return JSONResponse(
            status_code=429,
            content=error.model_dump(),
            headers={"Retry-After": "30"},
        )

    @app.exception_handler(InvalidStateError)
    async def invalid_state_handler(
        request: Request, exc: InvalidStateError
    ) -> JSONResponse:
        """Handle InvalidStateError with 422 Unprocessable Entity.

        Args:
            request: The incoming request.
            exc: The exception instance.

        Returns:
            JSONResponse with 422 status code.
        """
        logger.warning("Invalid state for workflow", workflow_id=exc.workflow_id, current_status=exc.current_status)
        error = ErrorResponse(
            code="INVALID_STATE",
            error=str(exc),
            details={
                "workflow_id": exc.workflow_id,
                "current_status": exc.current_status,
            },
        )
        return JSONResponse(
            status_code=422,
            content=error.model_dump(),
        )

    @app.exception_handler(WorkflowNotFoundError)
    async def workflow_not_found_handler(
        request: Request, exc: WorkflowNotFoundError
    ) -> JSONResponse:
        """Handle WorkflowNotFoundError with 404 Not Found.

        Args:
            request: The incoming request.
            exc: The exception instance.

        Returns:
            JSONResponse with 404 status code.
        """
        logger.warning("Workflow not found", workflow_id=exc.workflow_id)
        error = ErrorResponse(
            code="NOT_FOUND",
            error=str(exc),
            details={"workflow_id": exc.workflow_id},
        )
        return JSONResponse(
            status_code=404,
            content=error.model_dump(),
        )

    @app.exception_handler(FileOperationError)
    async def file_operation_handler(
        request: Request, exc: FileOperationError
    ) -> JSONResponse:
        """Handle FileOperationError with appropriate status code.

        Args:
            request: The incoming request.
            exc: The exception instance.

        Returns:
            JSONResponse with status code from the exception.
        """
        logger.warning("File operation error", code=exc.code, error=str(exc))
        error = ErrorResponse(code=exc.code, error=str(exc))
        return JSONResponse(
            status_code=exc.status_code,
            content=error.model_dump(),
        )

    @app.exception_handler(FileNotFoundError)
    async def file_not_found_handler(
        request: Request, exc: FileNotFoundError
    ) -> JSONResponse:
        """Handle FileNotFoundError with 404 Not Found.

        Args:
            request: The incoming request.
            exc: The exception instance.

        Returns:
            JSONResponse with 404 status code.
        """
        logger.warning("File not found", error=str(exc))
        error = ErrorResponse(
            code="FILE_NOT_FOUND",
            error=str(exc),
        )
        return JSONResponse(
            status_code=404,
            content=error.model_dump(),
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(
        request: Request, exc: ValueError
    ) -> JSONResponse:
        """Handle ValueError with 400 Bad Request.

        Args:
            request: The incoming request.
            exc: The exception instance.

        Returns:
            JSONResponse with 400 status code.
        """
        logger.warning("Value error", error=str(exc))
        error = ErrorResponse(
            code="INVALID_VALUE",
            error=str(exc),
        )
        return JSONResponse(
            status_code=400,
            content=error.model_dump(),
        )

    @app.exception_handler(InvalidWorktreeError)
    async def invalid_worktree_handler(
        request: Request, exc: InvalidWorktreeError
    ) -> JSONResponse:
        """Handle InvalidWorktreeError with 400 Bad Request.

        Args:
            request: The incoming request.
            exc: The exception instance.

        Returns:
            JSONResponse with 400 status code.
        """
        logger.warning("Invalid worktree", worktree_path=exc.worktree_path, reason=exc.reason)
        error = ErrorResponse(
            code="INVALID_WORKTREE",
            error=str(exc),
            details={
                "worktree_path": exc.worktree_path,
                "reason": exc.reason,
            },
        )
        return JSONResponse(
            status_code=400,
            content=error.model_dump(),
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        """Handle Pydantic ValidationError with 400 Bad Request.

        Args:
            request: The incoming request.
            exc: The exception instance.

        Returns:
            JSONResponse with 400 status code.
        """
        logger.warning("Validation error", error=str(exc))
        # Convert error objects to JSON-serializable format
        errors: list[dict[str, object]] = []
        for error in exc.errors():
            serializable_error: dict[str, object] = {
                "type": error["type"],
                "loc": list(error["loc"]),
                "msg": error["msg"],
            }
            # Add ctx if present
            if "ctx" in error:
                serializable_error["ctx"] = {
                    k: str(v) for k, v in error["ctx"].items()
                }
            errors.append(serializable_error)

        error_response = ErrorResponse(
            code="VALIDATION_ERROR",
            error="Validation failed",
            details={"errors": errors},
        )
        return JSONResponse(
            status_code=400,
            content=error_response.model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle generic exceptions with 500 Internal Server Error.

        Args:
            request: The incoming request.
            exc: The exception instance.

        Returns:
            JSONResponse with 500 status code.
        """
        logger.exception("Unhandled exception", error=str(exc))
        error = ErrorResponse(
            code="INTERNAL_ERROR",
            error=str(exc),
        )
        return JSONResponse(
            status_code=500,
            content=error.model_dump(),
        )
