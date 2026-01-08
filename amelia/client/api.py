"""REST API client for Amelia server."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx

from amelia.client.models import (
    CreateReviewWorkflowRequest,
    CreateWorkflowRequest,
    CreateWorkflowResponse,
    RejectWorkflowRequest,
    WorkflowListResponse,
    WorkflowResponse,
)


class AmeliaClientError(Exception):
    """Base exception for API client errors."""

    pass


class ServerUnreachableError(AmeliaClientError):
    """Raised when server cannot be reached."""

    pass


class WorkflowConflictError(AmeliaClientError):
    """Raised when workflow already exists for worktree (409 Conflict).

    Attributes:
        active_workflow: Details of the existing active workflow, if available.
    """

    def __init__(self, message: str, active_workflow: dict[str, Any] | None = None):
        super().__init__(message)
        self.active_workflow = active_workflow


class RateLimitError(AmeliaClientError):
    """Raised when rate limit is exceeded (429 Too Many Requests).

    Attributes:
        retry_after: Seconds to wait before retrying, if provided by server.
    """

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class WorkflowNotFoundError(AmeliaClientError):
    """Raised when workflow is not found (404)."""

    pass


class InvalidRequestError(AmeliaClientError):
    """Raised when request validation fails (400/422)."""

    pass


class AmeliaClient:
    """HTTP client for Amelia REST API.

    Provides methods for all workflow operations: create, approve, reject,
    cancel, and query. Handles errors and converts them to descriptive exceptions.

    Example:
        >>> client = AmeliaClient()
        >>> workflow = await client.create_workflow(
        ...     issue_id="ISSUE-123",
        ...     worktree_path="/home/user/repo",
        ...     worktree_name="main"
        ... )
        >>> await client.approve_workflow(workflow.id)
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8420"):
        """Initialize API client.

        Args:
            base_url: Base URL of the Amelia server (default: http://127.0.0.1:8420)
        """
        self.base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(30.0, connect=5.0)

    @asynccontextmanager
    async def _http_client(self) -> AsyncIterator[httpx.AsyncClient]:
        """Context manager for HTTP client with connection error handling.

        Yields:
            Configured httpx.AsyncClient instance.

        Raises:
            ServerUnreachableError: If server cannot be reached.
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                yield client
        except httpx.ConnectError as e:
            raise ServerUnreachableError(
                f"Cannot connect to Amelia server at {self.base_url}. "
                f"Is the server running? Try: amelia server"
            ) from e

    def _handle_workflow_create_errors(self, response: httpx.Response) -> None:
        """Handle error responses for workflow creation endpoints.

        Args:
            response: HTTP response to check for errors.

        Raises:
            WorkflowConflictError: If workflow already active (409).
            RateLimitError: If rate limit exceeded (429).
            InvalidRequestError: If validation fails (400/422).
            httpx.HTTPStatusError: For other non-2xx status codes.
        """
        if response.status_code == 409:
            data = response.json()
            detail = data.get("detail", {})
            active = detail.get("active_workflow")
            raise WorkflowConflictError(
                detail.get("message", "Workflow already active"),
                active_workflow=active,
            )
        elif response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(
                f"Too many concurrent workflows. Retry after {retry_after} seconds.",
                retry_after=int(retry_after) if retry_after else None,
            )
        elif response.status_code in (400, 422):
            raise InvalidRequestError(f"Invalid request: {response.json()}")
        else:
            response.raise_for_status()

    async def create_workflow(
        self,
        issue_id: str,
        worktree_path: str,
        worktree_name: str | None = None,
        profile: str | None = None,
    ) -> CreateWorkflowResponse:
        """Create a new workflow.

        Args:
            issue_id: Issue identifier (e.g., "ISSUE-123")
            worktree_path: Absolute path to git worktree
            worktree_name: Human-readable name for worktree
            profile: Optional profile name for configuration

        Returns:
            CreateWorkflowResponse with workflow id and initial status

        Raises:
            WorkflowConflictError: If workflow already active in this worktree
            RateLimitError: If concurrent workflow limit exceeded
            ServerUnreachableError: If server is not running
            InvalidRequestError: If request validation fails
        """
        request = CreateWorkflowRequest(
            issue_id=issue_id,
            worktree_path=worktree_path,
            worktree_name=worktree_name,
            profile=profile,
        )

        async with self._http_client() as client:
            response = await client.post(
                f"{self.base_url}/api/workflows",
                json=request.model_dump(exclude_none=True),
            )

            if response.status_code in (200, 201):
                return CreateWorkflowResponse.model_validate(response.json())

            self._handle_workflow_create_errors(response)

        # This should never be reached, but mypy needs it
        raise RuntimeError("Unexpected code path in create_workflow")

    async def create_review_workflow(
        self,
        diff_content: str,
        worktree_path: str,
        worktree_name: str | None = None,
        profile: str | None = None,
    ) -> CreateWorkflowResponse:
        """Create a review-fix workflow.

        Args:
            diff_content: The git diff to review.
            worktree_path: Absolute path to git worktree.
            worktree_name: Human-readable name for worktree.
            profile: Optional profile name for configuration.

        Returns:
            CreateWorkflowResponse with workflow id and initial status.

        Raises:
            WorkflowConflictError: If workflow already active in this worktree.
            RateLimitError: If concurrent workflow limit exceeded.
            ServerUnreachableError: If server is not running.
            InvalidRequestError: If request validation fails.
        """
        request = CreateReviewWorkflowRequest(
            diff_content=diff_content,
            worktree_path=worktree_path,
            worktree_name=worktree_name,
            profile=profile,
        )

        async with self._http_client() as client:
            response = await client.post(
                f"{self.base_url}/api/workflows/review",
                json=request.model_dump(exclude_none=True),
            )

            if response.status_code in (200, 201):
                return CreateWorkflowResponse.model_validate(response.json())

            self._handle_workflow_create_errors(response)

        # This should never be reached, but mypy needs it
        raise RuntimeError("Unexpected code path in create_review_workflow")

    async def approve_workflow(self, workflow_id: str) -> None:
        """Approve a workflow plan.

        Args:
            workflow_id: Workflow ID to approve.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidRequestError: If workflow is not in a state that can be approved.
            ServerUnreachableError: If server is not running.
        """
        async with self._http_client() as client:
            response = await client.post(
                f"{self.base_url}/api/workflows/{workflow_id}/approve"
            )

            if response.status_code == 200:
                return
            elif response.status_code == 404:
                raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")
            elif response.status_code == 400:
                raise InvalidRequestError(response.json().get("detail", "Invalid request"))
            else:
                response.raise_for_status()

    async def reject_workflow(self, workflow_id: str, reason: str) -> None:
        """Reject a workflow plan.

        Args:
            workflow_id: Workflow ID to reject.
            reason: Reason for rejection.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidRequestError: If workflow is not in a state that can be rejected.
            ServerUnreachableError: If server is not running.
        """
        request = RejectWorkflowRequest(feedback=reason)

        async with self._http_client() as client:
            response = await client.post(
                f"{self.base_url}/api/workflows/{workflow_id}/reject",
                json=request.model_dump(),
            )

            if response.status_code == 200:
                return
            elif response.status_code == 404:
                raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")
            elif response.status_code == 400:
                raise InvalidRequestError(response.json().get("detail", "Invalid request"))
            else:
                response.raise_for_status()

    async def cancel_workflow(self, workflow_id: str) -> None:
        """Cancel an active workflow.

        Args:
            workflow_id: Workflow ID to cancel.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            ServerUnreachableError: If server is not running.
        """
        async with self._http_client() as client:
            response = await client.post(
                f"{self.base_url}/api/workflows/{workflow_id}/cancel"
            )

            if response.status_code == 200:
                return
            elif response.status_code == 404:
                raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")
            else:
                response.raise_for_status()

    async def get_active_workflows(
        self, worktree_path: str | None = None
    ) -> WorkflowListResponse:
        """Get list of active workflows.

        Args:
            worktree_path: Optional filter by worktree path (server-side filtering)

        Returns:
            WorkflowListResponse with list of workflows

        Raises:
            ServerUnreachableError: If server is not running
        """
        async with self._http_client() as client:
            params = {}
            if worktree_path:
                params["worktree"] = worktree_path

            response = await client.get(
                f"{self.base_url}/api/workflows/active",
                params=params,
            )

            if response.status_code == 200:
                return WorkflowListResponse.model_validate(response.json())
            else:
                response.raise_for_status()

        raise RuntimeError("Unexpected code path in get_active_workflows")

    async def get_workflow(self, workflow_id: str) -> WorkflowResponse:
        """Get details of a specific workflow.

        Args:
            workflow_id: Workflow ID to fetch

        Returns:
            WorkflowResponse with workflow details

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            ServerUnreachableError: If server is not running
        """
        async with self._http_client() as client:
            response = await client.get(
                f"{self.base_url}/api/workflows/{workflow_id}"
            )

            if response.status_code == 200:
                return WorkflowResponse.model_validate(response.json())
            elif response.status_code == 404:
                raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")
            else:
                response.raise_for_status()

        # This should never be reached, but mypy needs it
        raise RuntimeError("Unexpected code path in get_workflow")
