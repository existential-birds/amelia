# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
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
    InvalidStateError,
    InvalidWorktreeError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.server.models.requests import CreateWorkflowRequest, RejectRequest
from amelia.server.models.responses import (
    ActionResponse,
    CreateWorkflowResponse,
    ErrorResponse,
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
    workflow_id = await orchestrator.start_workflow(
        issue_id=request.issue_id,
        worktree_path=request.worktree_path,
        worktree_name=request.worktree_name,
        profile=request.profile,
        driver=request.driver,
    )

    logger.info(f"Created workflow {workflow_id} for issue {request.issue_id}")

    return CreateWorkflowResponse(
        id=workflow_id,
        status="pending",
        message=f"Workflow created for issue {request.issue_id}",
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
            logger.warning(f"Invalid cursor: {e}")
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

    return WorkflowListResponse(
        workflows=[
            WorkflowSummary(
                id=w.id,
                issue_id=w.issue_id,
                worktree_name=w.worktree_name,
                status=w.workflow_status,
                started_at=w.started_at,
                current_stage=w.current_stage,
            )
            for w in workflows
        ],
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

    Active workflows are those in pending, in_progress, or blocked status.

    Args:
        worktree: Filter by worktree path.
        repository: Workflow repository dependency.

    Returns:
        WorkflowListResponse with active workflows.
    """
    # Resolve worktree path to canonical form (e.g., /tmp -> /private/tmp on macOS)
    resolved_worktree = str(Path(worktree).resolve()) if worktree else None

    workflows = await repository.list_active(worktree_path=resolved_worktree)

    return WorkflowListResponse(
        workflows=[
            WorkflowSummary(
                id=w.id,
                issue_id=w.issue_id,
                worktree_name=w.worktree_name,
                status=w.workflow_status,
                started_at=w.started_at,
                current_stage=w.current_stage,
            )
            for w in workflows
        ],
        total=len(workflows),
        has_more=False,
    )


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

    # TODO: Fetch token usage and recent events
    token_usage = None
    recent_events: list[dict[str, object]] = []

    return WorkflowDetailResponse(
        id=workflow.id,
        issue_id=workflow.issue_id,
        worktree_path=workflow.worktree_path,
        worktree_name=workflow.worktree_name,
        status=workflow.workflow_status,
        started_at=workflow.started_at,
        completed_at=workflow.completed_at,
        failure_reason=workflow.failure_reason,
        current_stage=workflow.current_stage,
        plan=None,
        token_usage=token_usage,
        recent_events=recent_events,
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
    logger.info(f"Cancelled workflow {workflow_id}")
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
    logger.info(f"Approved workflow {workflow_id}")
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
    logger.info(f"Rejected workflow {workflow_id}: {request.feedback}")
    return ActionResponse(status="rejected", workflow_id=workflow_id)


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
        logger.warning(
            f"Workflow conflict: {exc.workflow_id} at {exc.worktree_path}"
        )
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
        logger.warning(
            f"Concurrency limit exceeded: {exc.current_count}/{exc.max_concurrent}"
        )
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
        logger.warning(
            f"Invalid state for workflow {exc.workflow_id}: {exc.current_status}"
        )
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
        logger.warning(f"Workflow not found: {exc.workflow_id}")
        error = ErrorResponse(
            code="NOT_FOUND",
            error=str(exc),
            details={"workflow_id": exc.workflow_id},
        )
        return JSONResponse(
            status_code=404,
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
        logger.warning(f"Invalid worktree: {exc.worktree_path} - {exc.reason}")
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
        logger.warning(f"Validation error: {exc}")
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
        logger.exception(f"Unhandled exception: {exc}")
        error = ErrorResponse(
            code="INTERNAL_ERROR",
            error=str(exc),
        )
        return JSONResponse(
            status_code=500,
            content=error.model_dump(),
        )
