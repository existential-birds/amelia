"""Workflow management routes and exception handlers."""

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic_core import ValidationError

from amelia.server.database import WorkflowRepository
from amelia.server.exceptions import (
    ConcurrencyLimitError,
    InvalidStateError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.server.models.responses import ErrorResponse


# Create the workflows router
router = APIRouter(prefix="/workflows", tags=["workflows"])


def get_repository() -> WorkflowRepository:
    """Get the workflow repository dependency.

    This is a placeholder that will be implemented when database
    lifecycle management is added.

    Returns:
        WorkflowRepository instance.

    Raises:
        NotImplementedError: Always (not yet implemented).
    """
    raise NotImplementedError("Repository dependency not yet implemented")


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
