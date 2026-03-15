"""REST API client for Amelia server."""
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from pydantic import BaseModel

from amelia.client.models import (
    BatchStartResponse,
    CreateReviewWorkflowRequest,
    CreateWorkflowRequest,
    CreateWorkflowResponse,
    RejectWorkflowRequest,
    WorkflowListResponse,
    WorkflowResponse,
)
from amelia.core.types import PRAutoFixConfig, PRReviewComment, PRSummary


class AmeliaClientError(Exception):
    """Base exception for API client errors."""


class ServerUnreachableError(AmeliaClientError):
    """Raised when server cannot be reached."""


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


class InvalidRequestError(AmeliaClientError):
    """Raised when request validation fails (400/422)."""


class TriggerPRAutoFixResponse(BaseModel):
    """Response from triggering PR auto-fix."""

    workflow_id: str
    message: str


class PRAutoFixStatusResponse(BaseModel):
    """Response with PR auto-fix configuration status."""

    enabled: bool
    config: PRAutoFixConfig | None = None


class PRListResponse(BaseModel):
    """Response containing a list of open PRs."""

    prs: list[PRSummary]


class PRCommentsResponse(BaseModel):
    """Response containing PR review comments."""

    comments: list[PRReviewComment]


class AmeliaClient:
    """HTTP client for Amelia REST API.

    Provides methods for all workflow operations: create, approve, reject,
    cancel, and query. Handles errors and converts them to descriptive exceptions.

    Example:
        >>> client = AmeliaClient()
        >>> workflow = await client.create_workflow(
        ...     issue_id="ISSUE-123",
        ...     worktree_path="/home/user/repo",
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

    def _handle_action_response(
        self, response: httpx.Response, workflow_id: str | uuid.UUID
    ) -> None:
        """Handle response for workflow action endpoints (approve/reject/cancel/resume).

        Args:
            response: HTTP response to check.
            workflow_id: Workflow ID for error messages.

        Raises:
            WorkflowNotFoundError: If workflow not found (404).
            InvalidRequestError: If action invalid (400/409).
            httpx.HTTPStatusError: For other non-2xx status codes.
        """
        if response.status_code == 200:
            return
        elif response.status_code == 404:
            raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")
        elif response.status_code in (400, 409):
            data = response.json()
            raise InvalidRequestError(
                data.get("detail", "Invalid request")
            )
        else:
            response.raise_for_status()

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
        profile: str | None = None,
        task_title: str | None = None,
        task_description: str | None = None,
        start: bool = True,
        plan_now: bool = False,
    ) -> CreateWorkflowResponse:
        """Create a new workflow.

        Args:
            issue_id: Issue identifier (e.g., "ISSUE-123")
            worktree_path: Absolute path to git worktree
            profile: Optional profile name for configuration
            task_title: Optional task title for none tracker (bypasses issue lookup)
            task_description: Optional task description (requires task_title)
            start: Whether to start workflow immediately (default True)
            plan_now: Whether to run Architect before queueing (requires start=False)

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
            profile=profile,
            task_title=task_title,
            task_description=task_description,
            start=start,
            plan_now=plan_now,
        )

        async with self._http_client() as client:
            response = await client.post(
                f"{self.base_url}/api/workflows",
                json=request.model_dump(exclude_none=True),
            )

            if response.status_code in (200, 201):
                return CreateWorkflowResponse.model_validate(response.json())

            self._handle_workflow_create_errors(response)

        raise RuntimeError("Unexpected code path in create_workflow")

    async def create_review_workflow(
        self,
        diff_content: str,
        worktree_path: str,
        profile: str | None = None,
    ) -> CreateWorkflowResponse:
        """Create a review-fix workflow.

        Args:
            diff_content: The git diff to review.
            worktree_path: Absolute path to git worktree.
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

        raise RuntimeError("Unexpected code path in create_review_workflow")

    async def approve_workflow(self, workflow_id: str | uuid.UUID) -> None:
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
            self._handle_action_response(response, workflow_id)

    async def reject_workflow(self, workflow_id: str | uuid.UUID, reason: str) -> None:
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

            self._handle_action_response(response, workflow_id)

    async def cancel_workflow(self, workflow_id: str | uuid.UUID) -> None:
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

            self._handle_action_response(response, workflow_id)

    async def resume_workflow(self, workflow_id: str) -> None:
        """Resume a failed workflow from its last checkpoint.

        Args:
            workflow_id: Workflow ID to resume.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidRequestError: If workflow cannot be resumed (wrong status, no checkpoint).
            ServerUnreachableError: If server is not running.
        """
        async with self._http_client() as client:
            response = await client.post(
                f"{self.base_url}/api/workflows/{workflow_id}/resume"
            )

            self._handle_action_response(response, workflow_id)

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

        raise RuntimeError("Unexpected code path in get_workflow")

    async def start_workflow(self, workflow_id: str) -> dict[str, str]:
        """Start a pending workflow.

        Transitions a workflow from pending to in_progress state.

        Args:
            workflow_id: Workflow ID to start.

        Returns:
            Dict with workflow_id and status.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidRequestError: If workflow is not in pending state.
            ServerUnreachableError: If server is not running.
        """
        async with self._http_client() as client:
            response = await client.post(
                f"{self.base_url}/api/workflows/{workflow_id}/start"
            )

            if response.status_code == 202:
                data: dict[str, str] = response.json()
                return data
            elif response.status_code == 404:
                raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")
            elif response.status_code == 409:
                raise InvalidRequestError(response.json().get("detail", "Invalid state"))
            else:
                response.raise_for_status()

        raise RuntimeError("Unexpected code path in start_workflow")

    async def start_batch(
        self,
        workflow_ids: list[str] | None = None,
        worktree_path: str | None = None,
    ) -> BatchStartResponse:
        """Start multiple pending workflows.

        Args:
            workflow_ids: Specific workflow IDs to start, or None for all pending.
            worktree_path: Optional filter by worktree path.

        Returns:
            BatchStartResponse with started IDs and errors.

        Raises:
            ServerUnreachableError: If server is not running.
        """
        request_body: dict[str, Any] = {}
        if workflow_ids is not None:
            request_body["workflow_ids"] = workflow_ids
        if worktree_path is not None:
            request_body["worktree_path"] = worktree_path

        async with self._http_client() as client:
            response = await client.post(
                f"{self.base_url}/api/workflows/start-batch",
                json=request_body,
            )

            if response.status_code == 200:
                return BatchStartResponse.model_validate(response.json())
            else:
                response.raise_for_status()

        raise RuntimeError("Unexpected code path in start_batch")

    async def trigger_pr_autofix(
        self,
        pr_number: int,
        profile: str,
        aggressiveness: str | None = None,
    ) -> TriggerPRAutoFixResponse:
        """Trigger a PR auto-fix cycle.

        Args:
            pr_number: PR number to fix.
            profile: Profile name.
            aggressiveness: Optional aggressiveness override (critical/standard/thorough).

        Returns:
            TriggerPRAutoFixResponse with workflow_id and message.

        Raises:
            ServerUnreachableError: If server is not running.
            InvalidRequestError: If request validation fails.
        """
        async with self._http_client() as client:
            kwargs: dict[str, Any] = {
                "params": {"profile": profile},
            }
            if aggressiveness is not None:
                kwargs["json"] = {"aggressiveness": aggressiveness}

            response = await client.post(
                f"{self.base_url}/api/github/prs/{pr_number}/auto-fix",
                **kwargs,
            )

            if response.status_code == 202:
                return TriggerPRAutoFixResponse.model_validate(response.json())

            self._handle_workflow_create_errors(response)

        raise RuntimeError("Unexpected code path in trigger_pr_autofix")

    async def list_prs(self, profile: str) -> PRListResponse:
        """List open PRs for a profile's repository.

        Args:
            profile: Profile name.

        Returns:
            PRListResponse with list of open PRs.

        Raises:
            WorkflowNotFoundError: If profile not found (404).
            InvalidRequestError: On other errors.
            ServerUnreachableError: If server is not running.
        """
        async with self._http_client() as client:
            response = await client.get(
                f"{self.base_url}/api/github/prs",
                params={"profile": profile},
            )

            if response.status_code == 200:
                return PRListResponse.model_validate(response.json())
            elif response.status_code == 404:
                raise WorkflowNotFoundError(
                    f"Profile '{profile}' not found"
                )
            else:
                raise InvalidRequestError(f"Failed to list PRs: {response.json()}")

        raise RuntimeError("Unexpected code path in list_prs")

    async def get_pr_comments(
        self, pr_number: int, profile: str
    ) -> PRCommentsResponse:
        """Get unresolved review comments for a PR.

        Args:
            pr_number: PR number.
            profile: Profile name.

        Returns:
            PRCommentsResponse with list of review comments.

        Raises:
            InvalidRequestError: On error responses.
            ServerUnreachableError: If server is not running.
        """
        async with self._http_client() as client:
            response = await client.get(
                f"{self.base_url}/api/github/prs/{pr_number}/comments",
                params={"profile": profile},
            )

            if response.status_code == 200:
                return PRCommentsResponse.model_validate(response.json())
            elif response.status_code == 404:
                raise WorkflowNotFoundError(
                    f"PR #{pr_number} or profile '{profile}' not found"
                )
            else:
                raise InvalidRequestError(
                    f"Failed to get PR comments: {response.json()}"
                )

        raise RuntimeError("Unexpected code path in get_pr_comments")

    async def get_pr_autofix_status(self, profile: str) -> PRAutoFixStatusResponse:
        """Get PR auto-fix configuration status for a profile.

        Args:
            profile: Profile name.

        Returns:
            PRAutoFixStatusResponse with enabled flag and config.

        Raises:
            WorkflowNotFoundError: If profile not found (404).
            ServerUnreachableError: If server is not running.
        """
        async with self._http_client() as client:
            response = await client.get(
                f"{self.base_url}/api/github/prs/config",
                params={"profile": profile},
            )

            if response.status_code == 200:
                return PRAutoFixStatusResponse.model_validate(response.json())
            elif response.status_code == 404:
                raise WorkflowNotFoundError(
                    f"Profile '{profile}' not found"
                )
            else:
                response.raise_for_status()

        raise RuntimeError("Unexpected code path in get_pr_autofix_status")
