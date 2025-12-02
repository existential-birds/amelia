# REST API Workflow Endpoints Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement REST API endpoints for workflow lifecycle management with validation, pagination, error handling, and proper HTTP semantics.

**Architecture:** FastAPI router-based architecture with Pydantic request/response schemas, custom exception classes, dependency injection for repository, cursor-based pagination, and comprehensive error handling.

**Tech Stack:** FastAPI, Pydantic, pytest, httpx

**Depends on:** Plan 3 (Workflow Models & Repository)

---

## Task 1: Create Custom Exception Classes

**Files:**
- Create: `amelia/server/exceptions.py`
- Create: `amelia/server/__init__.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/test_exceptions.py
"""Tests for custom exception classes."""
import pytest


class TestWorkflowConflictError:
    """Tests for WorkflowConflictError."""

    def test_create_with_worktree_and_workflow_id(self):
        """Exception stores worktree path and conflicting workflow ID."""
        from amelia.server.exceptions import WorkflowConflictError

        exc = WorkflowConflictError(
            worktree_path="/path/to/repo",
            workflow_id="wf-123",
        )

        assert exc.worktree_path == "/path/to/repo"
        assert exc.workflow_id == "wf-123"
        assert "already active" in str(exc).lower()

    def test_message_includes_path_and_id(self):
        """Exception message includes worktree path and workflow ID."""
        from amelia.server.exceptions import WorkflowConflictError

        exc = WorkflowConflictError(
            worktree_path="/repo",
            workflow_id="wf-456",
        )

        message = str(exc)
        assert "/repo" in message
        assert "wf-456" in message


class TestConcurrencyLimitError:
    """Tests for ConcurrencyLimitError."""

    def test_create_with_limit_and_current(self):
        """Exception stores max_concurrent and current count."""
        from amelia.server.exceptions import ConcurrencyLimitError

        exc = ConcurrencyLimitError(
            max_concurrent=5,
            current_count=5,
        )

        assert exc.max_concurrent == 5
        assert exc.current_count == 5

    def test_message_includes_limit(self):
        """Exception message includes concurrency limit."""
        from amelia.server.exceptions import ConcurrencyLimitError

        exc = ConcurrencyLimitError(max_concurrent=3, current_count=3)
        message = str(exc)

        assert "3" in message
        assert "concurrent" in message.lower()

    def test_default_current_count_equals_max(self):
        """current_count defaults to max_concurrent."""
        from amelia.server.exceptions import ConcurrencyLimitError

        exc = ConcurrencyLimitError(max_concurrent=10)
        assert exc.current_count == 10


class TestInvalidStateError:
    """Tests for InvalidStateError."""

    def test_create_with_message_and_workflow_id(self):
        """Exception stores custom message and workflow ID."""
        from amelia.server.exceptions import InvalidStateError

        exc = InvalidStateError(
            message="Cannot approve: not blocked",
            workflow_id="wf-789",
        )

        assert exc.workflow_id == "wf-789"
        assert "Cannot approve" in str(exc)

    def test_create_with_status_details(self):
        """Exception can include current status details."""
        from amelia.server.exceptions import InvalidStateError

        exc = InvalidStateError(
            message="Workflow is completed",
            workflow_id="wf-100",
            current_status="completed",
        )

        assert exc.current_status == "completed"


class TestWorkflowNotFoundError:
    """Tests for WorkflowNotFoundError."""

    def test_create_with_workflow_id(self):
        """Exception stores workflow ID."""
        from amelia.server.exceptions import WorkflowNotFoundError

        exc = WorkflowNotFoundError(workflow_id="wf-missing")

        assert exc.workflow_id == "wf-missing"
        assert "not found" in str(exc).lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_exceptions.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create server package init**

```python
# amelia/server/__init__.py
"""Amelia server package."""
from amelia.server.exceptions import (
    ConcurrencyLimitError,
    InvalidStateError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)

__all__ = [
    "WorkflowConflictError",
    "ConcurrencyLimitError",
    "InvalidStateError",
    "WorkflowNotFoundError",
]
```

**Step 4: Implement exception classes**

```python
# amelia/server/exceptions.py
"""Custom exception classes for API error handling."""


class WorkflowConflictError(Exception):
    """Raised when attempting to start a workflow in a busy worktree.

    HTTP: 409 Conflict
    """

    def __init__(self, worktree_path: str, workflow_id: str):
        """Initialize conflict error.

        Args:
            worktree_path: Path to the busy worktree.
            workflow_id: ID of the conflicting active workflow.
        """
        self.worktree_path = worktree_path
        self.workflow_id = workflow_id
        super().__init__(
            f"Workflow already active in {worktree_path} (workflow_id: {workflow_id})"
        )


class ConcurrencyLimitError(Exception):
    """Raised when maximum concurrent workflow limit is reached.

    HTTP: 429 Too Many Requests
    """

    def __init__(self, max_concurrent: int, current_count: int | None = None):
        """Initialize concurrency limit error.

        Args:
            max_concurrent: Maximum allowed concurrent workflows.
            current_count: Current number of active workflows (defaults to max).
        """
        self.max_concurrent = max_concurrent
        self.current_count = current_count if current_count is not None else max_concurrent
        super().__init__(
            f"Maximum {max_concurrent} concurrent workflows reached "
            f"({current_count} currently active)"
        )


class InvalidStateError(Exception):
    """Raised when workflow is in wrong state for requested operation.

    HTTP: 422 Unprocessable Entity
    """

    def __init__(
        self,
        message: str,
        workflow_id: str,
        current_status: str | None = None,
    ):
        """Initialize invalid state error.

        Args:
            message: Human-readable error description.
            workflow_id: Workflow that's in invalid state.
            current_status: Current workflow status (optional).
        """
        self.workflow_id = workflow_id
        self.current_status = current_status
        super().__init__(message)


class WorkflowNotFoundError(Exception):
    """Raised when workflow ID doesn't exist.

    HTTP: 404 Not Found
    """

    def __init__(self, workflow_id: str):
        """Initialize not found error.

        Args:
            workflow_id: Workflow ID that wasn't found.
        """
        self.workflow_id = workflow_id
        super().__init__(f"Workflow not found: {workflow_id}")
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_exceptions.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/__init__.py amelia/server/exceptions.py tests/unit/server/test_exceptions.py
git commit -m "feat(server): add custom exception classes for API error handling"
```

---

## Task 2: Create Request/Response Schemas

**Files:**
- Create: `amelia/server/models/requests.py`
- Create: `amelia/server/models/responses.py`
- Modify: `amelia/server/models/__init__.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/models/test_requests.py
"""Tests for request schemas."""
import pytest
from pydantic import ValidationError


class TestCreateWorkflowRequest:
    """Tests for CreateWorkflowRequest schema."""

    def test_create_with_required_fields(self):
        """Request can be created with required fields."""
        from amelia.server.models.requests import CreateWorkflowRequest

        req = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/absolute/path/to/repo",
        )

        assert req.issue_id == "ISSUE-123"
        assert req.worktree_path == "/absolute/path/to/repo"

    def test_optional_fields_default_none(self):
        """Optional fields default to None."""
        from amelia.server.models.requests import CreateWorkflowRequest

        req = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path",
        )

        assert req.worktree_name is None
        assert req.profile is None
        assert req.driver is None

    def test_issue_id_alphanumeric_validation(self):
        """issue_id must be alphanumeric with dashes/underscores."""
        from amelia.server.models.requests import CreateWorkflowRequest

        # Valid
        valid = CreateWorkflowRequest(
            issue_id="ISSUE-123_test",
            worktree_path="/path",
        )
        assert valid.issue_id == "ISSUE-123_test"

    def test_issue_id_rejects_invalid_pattern(self):
        """issue_id rejects non-alphanumeric characters."""
        from amelia.server.models.requests import CreateWorkflowRequest

        with pytest.raises(ValidationError) as exc:
            CreateWorkflowRequest(
                issue_id="ISSUE/123",  # Slash not allowed
                worktree_path="/path",
            )
        assert "issue_id" in str(exc.value)

    def test_issue_id_min_length(self):
        """issue_id must have at least 1 character."""
        from amelia.server.models.requests import CreateWorkflowRequest

        with pytest.raises(ValidationError) as exc:
            CreateWorkflowRequest(
                issue_id="",
                worktree_path="/path",
            )
        assert "issue_id" in str(exc.value)

    def test_issue_id_max_length(self):
        """issue_id cannot exceed 100 characters."""
        from amelia.server.models.requests import CreateWorkflowRequest

        long_id = "A" * 101
        with pytest.raises(ValidationError) as exc:
            CreateWorkflowRequest(
                issue_id=long_id,
                worktree_path="/path",
            )
        assert "issue_id" in str(exc.value)

    def test_issue_id_dangerous_characters_rejected(self):
        """issue_id validator rejects path traversal and injection chars."""
        from amelia.server.models.requests import CreateWorkflowRequest

        dangerous = ["../etc", "test\0null", "test;rm", "test|cat", "$USER"]

        for bad_id in dangerous:
            with pytest.raises(ValidationError):
                CreateWorkflowRequest(
                    issue_id=bad_id,
                    worktree_path="/path",
                )

    def test_worktree_path_must_be_absolute(self):
        """worktree_path must be absolute path."""
        from amelia.server.models.requests import CreateWorkflowRequest

        with pytest.raises(ValidationError) as exc:
            CreateWorkflowRequest(
                issue_id="ISSUE-123",
                worktree_path="relative/path",  # Not absolute
            )
        assert "absolute" in str(exc.value).lower()

    def test_worktree_path_resolves_canonical(self):
        """worktree_path is resolved to canonical form."""
        from amelia.server.models.requests import CreateWorkflowRequest
        import os

        # Use real path with .. to test resolution
        req = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path=f"{os.getcwd()}/../test",
        )

        # Should be resolved (no ..)
        assert ".." not in req.worktree_path

    def test_worktree_path_rejects_null_bytes(self):
        """worktree_path rejects null bytes."""
        from amelia.server.models.requests import CreateWorkflowRequest

        with pytest.raises(ValidationError) as exc:
            CreateWorkflowRequest(
                issue_id="ISSUE-123",
                worktree_path="/path/to\0/repo",
            )
        assert "null byte" in str(exc.value).lower()

    def test_profile_pattern_validation(self):
        """profile must match lowercase alphanumeric pattern."""
        from amelia.server.models.requests import CreateWorkflowRequest

        # Valid
        valid = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path",
            profile="work-profile_01",
        )
        assert valid.profile == "work-profile_01"

        # Invalid (uppercase)
        with pytest.raises(ValidationError):
            CreateWorkflowRequest(
                issue_id="ISSUE-123",
                worktree_path="/path",
                profile="WorkProfile",
            )

    def test_driver_pattern_validation(self):
        """driver must match 'type:name' pattern."""
        from amelia.server.models.requests import CreateWorkflowRequest

        # Valid
        valid = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path",
            driver="sdk:claude",
        )
        assert valid.driver == "sdk:claude"

        # Invalid (no colon)
        with pytest.raises(ValidationError):
            CreateWorkflowRequest(
                issue_id="ISSUE-123",
                worktree_path="/path",
                driver="invalid",
            )


class TestRejectRequest:
    """Tests for RejectRequest schema."""

    def test_create_with_feedback(self):
        """RejectRequest requires feedback field."""
        from amelia.server.models.requests import RejectRequest

        req = RejectRequest(feedback="Plan needs more tests")

        assert req.feedback == "Plan needs more tests"

    def test_feedback_required(self):
        """feedback field is required."""
        from amelia.server.models.requests import RejectRequest

        with pytest.raises(ValidationError) as exc:
            RejectRequest()  # Missing feedback
        assert "feedback" in str(exc.value)

    def test_feedback_min_length(self):
        """feedback must have at least 1 character."""
        from amelia.server.models.requests import RejectRequest

        with pytest.raises(ValidationError) as exc:
            RejectRequest(feedback="")
        assert "feedback" in str(exc.value)
```

```python
# tests/unit/server/models/test_responses.py
"""Tests for response schemas."""
import pytest
from datetime import datetime


class TestCreateWorkflowResponse:
    """Tests for CreateWorkflowResponse schema."""

    def test_create_response(self):
        """Response includes id, status, and message."""
        from amelia.server.models.responses import CreateWorkflowResponse

        resp = CreateWorkflowResponse(
            id="wf-123",
            status="pending",
            message="Workflow created",
        )

        assert resp.id == "wf-123"
        assert resp.status == "pending"
        assert resp.message == "Workflow created"


class TestWorkflowSummary:
    """Tests for WorkflowSummary schema."""

    def test_create_summary(self):
        """Summary includes core workflow fields."""
        from amelia.server.models.responses import WorkflowSummary

        summary = WorkflowSummary(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_name="main",
            status="in_progress",
            started_at=datetime.utcnow(),
            current_stage="development",
        )

        assert summary.id == "wf-123"
        assert summary.issue_id == "ISSUE-456"
        assert summary.status == "in_progress"

    def test_optional_fields_can_be_none(self):
        """Optional fields can be None."""
        from amelia.server.models.responses import WorkflowSummary

        summary = WorkflowSummary(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_name="main",
            status="pending",
        )

        assert summary.started_at is None
        assert summary.current_stage is None


class TestWorkflowListResponse:
    """Tests for WorkflowListResponse schema."""

    def test_create_list_response(self):
        """List response includes workflows, total, cursor."""
        from amelia.server.models.responses import (
            WorkflowListResponse,
            WorkflowSummary,
        )

        resp = WorkflowListResponse(
            workflows=[
                WorkflowSummary(
                    id="wf-1",
                    issue_id="ISSUE-1",
                    worktree_name="main",
                    status="pending",
                )
            ],
            total=100,
            cursor="base64cursor",
            has_more=True,
        )

        assert len(resp.workflows) == 1
        assert resp.total == 100
        assert resp.cursor == "base64cursor"
        assert resp.has_more is True

    def test_default_cursor_none(self):
        """cursor defaults to None."""
        from amelia.server.models.responses import WorkflowListResponse

        resp = WorkflowListResponse(
            workflows=[],
            total=0,
        )

        assert resp.cursor is None
        assert resp.has_more is False


class TestWorkflowDetailResponse:
    """Tests for WorkflowDetailResponse schema."""

    def test_create_detail_response(self):
        """Detail response includes all workflow fields."""
        from amelia.server.models.responses import WorkflowDetailResponse

        resp = WorkflowDetailResponse(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/path/to/repo",
            worktree_name="main",
            status="in_progress",
            started_at=datetime.utcnow(),
            completed_at=None,
            failure_reason=None,
            current_stage="development",
            plan=None,
            token_usage={},
            recent_events=[],
        )

        assert resp.id == "wf-123"
        assert resp.issue_id == "ISSUE-456"
        assert resp.worktree_path == "/path/to/repo"


class TestErrorResponse:
    """Tests for ErrorResponse schema."""

    def test_create_error_response(self):
        """Error response includes error, code, details."""
        from amelia.server.models.responses import ErrorResponse

        resp = ErrorResponse(
            error="Workflow not found",
            code="NOT_FOUND",
            details={"workflow_id": "wf-missing"},
        )

        assert resp.error == "Workflow not found"
        assert resp.code == "NOT_FOUND"
        assert resp.details["workflow_id"] == "wf-missing"

    def test_details_optional(self):
        """details field is optional."""
        from amelia.server.models.responses import ErrorResponse

        resp = ErrorResponse(
            error="Internal error",
            code="INTERNAL_ERROR",
        )

        assert resp.details is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_requests.py tests/unit/server/models/test_responses.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement request schemas**

```python
# amelia/server/models/requests.py
"""Request schemas for workflow API endpoints."""
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class CreateWorkflowRequest(BaseModel):
    """Request to create a new workflow.

    Attributes:
        issue_id: Issue identifier (alphanumeric, dashes, underscores only).
        worktree_path: Absolute path to git worktree root.
        worktree_name: Human-readable worktree name (derived if not provided).
        profile: Profile name for configuration.
        driver: Driver specification (e.g., 'sdk:claude', 'api:openai').
    """

    issue_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Issue identifier (alphanumeric, underscores, hyphens only)",
    )
    worktree_path: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Absolute path to git worktree root",
    )
    worktree_name: str | None = Field(
        default=None,
        max_length=255,
        description="Human-readable worktree name (derived from path if not provided)",
    )
    profile: str | None = Field(
        default=None,
        max_length=64,
        pattern=r"^[a-z0-9_-]+$",
        description="Profile name for configuration",
    )
    driver: str | None = Field(
        default=None,
        pattern=r"^(sdk|api|cli):[a-z0-9_-]+$",
        description="Driver specification (e.g., 'sdk:claude', 'api:openai')",
    )

    @field_validator("issue_id")
    @classmethod
    def validate_issue_id(cls, v: str) -> str:
        """Prevent path traversal and injection in issue_id.

        Args:
            v: Raw issue_id value.

        Returns:
            Validated issue_id.

        Raises:
            ValueError: If dangerous characters detected.
        """
        dangerous_chars = [
            "/",
            "\\",
            "..",
            "\0",
            "\n",
            "\r",
            "'",
            '"',
            "`",
            "$",
            "|",
            ";",
            "&",
        ]
        for char in dangerous_chars:
            if char in v:
                raise ValueError(f"Invalid character in issue_id: {repr(char)}")
        return v

    @field_validator("worktree_path")
    @classmethod
    def validate_worktree_path(cls, v: str) -> str:
        """Validate worktree path is absolute and safe.

        Args:
            v: Raw worktree_path value.

        Returns:
            Canonicalized absolute path.

        Raises:
            ValueError: If path is invalid or unsafe.
        """
        path = Path(v)

        # Must be absolute
        if not path.is_absolute():
            raise ValueError("Worktree path must be absolute")

        # Resolve to canonical form (removes .., symlinks)
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError) as e:
            raise ValueError(f"Invalid path: {e}")

        # Check for null bytes (path traversal attack)
        if "\0" in v:
            raise ValueError("Invalid null byte in path")

        return str(resolved)


class RejectRequest(BaseModel):
    """Request to reject a workflow plan.

    Attributes:
        feedback: Reason for rejection (required).
    """

    feedback: str = Field(
        ...,
        min_length=1,
        description="Reason for rejection",
    )
```

**Step 4: Implement response schemas**

```python
# amelia/server/models/responses.py
"""Response schemas for workflow API endpoints."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from amelia.server.models.state import WorkflowStatus


class CreateWorkflowResponse(BaseModel):
    """Response from creating a workflow.

    Attributes:
        id: Workflow identifier.
        status: Initial workflow status.
        message: Human-readable status message.
    """

    id: str = Field(..., description="Workflow identifier")
    status: WorkflowStatus = Field(..., description="Initial workflow status")
    message: str = Field(..., description="Human-readable status message")


class WorkflowSummary(BaseModel):
    """Summary view of a workflow for list endpoints.

    Attributes:
        id: Workflow identifier.
        issue_id: Issue being worked on.
        worktree_name: Human-readable worktree name.
        status: Current workflow status.
        started_at: When workflow started (None if pending).
        current_stage: Currently executing stage (None if not started).
    """

    id: str
    issue_id: str
    worktree_name: str
    status: WorkflowStatus
    started_at: datetime | None = None
    current_stage: str | None = None


class WorkflowListResponse(BaseModel):
    """Paginated list of workflows.

    Attributes:
        workflows: List of workflow summaries.
        total: Total number of matching workflows.
        cursor: Opaque cursor for next page (base64 encoded).
        has_more: True if more results available.
    """

    workflows: list[WorkflowSummary]
    total: int
    cursor: str | None = None
    has_more: bool = False


class TokenSummary(BaseModel):
    """Token usage summary for an agent.

    Attributes:
        input_tokens: Total input tokens.
        output_tokens: Total output tokens.
        total_tokens: Sum of input + output tokens.
        estimated_cost_usd: Estimated cost in USD.
    """

    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None = None


class WorkflowDetailResponse(BaseModel):
    """Detailed view of a single workflow.

    Attributes:
        id: Workflow identifier.
        issue_id: Issue being worked on.
        worktree_path: Absolute path to worktree.
        worktree_name: Human-readable worktree name.
        status: Current workflow status.
        started_at: When workflow started.
        completed_at: When workflow ended.
        failure_reason: Error message when failed.
        current_stage: Currently executing stage.
        plan: Full task plan (TaskDAG from amelia.core.types).
        token_usage: Token usage by agent.
        recent_events: Last 50 workflow events.
    """

    id: str
    issue_id: str
    worktree_path: str
    worktree_name: str
    status: WorkflowStatus
    started_at: datetime | None
    completed_at: datetime | None
    failure_reason: str | None
    current_stage: str | None
    plan: Any | None  # TaskDAG from amelia.core.types (avoid circular import)
    token_usage: dict[str, TokenSummary]
    recent_events: list[Any]  # WorkflowEvent list


class ErrorResponse(BaseModel):
    """Standard error response.

    Attributes:
        error: Human-readable error message.
        code: Machine-readable error code.
        details: Optional structured error details.
    """

    error: str = Field(..., description="Human-readable error message")
    code: str = Field(
        ...,
        description="Machine-readable error code (e.g., WORKFLOW_CONFLICT, NOT_FOUND)",
    )
    details: dict[str, Any] | None = Field(
        default=None,
        description="Optional structured error details",
    )
```

**Step 5: Update models package init**

```python
# amelia/server/models/__init__.py
"""Domain models for Amelia server."""
from amelia.server.models.events import EventType, WorkflowEvent
from amelia.server.models.requests import CreateWorkflowRequest, RejectRequest
from amelia.server.models.responses import (
    CreateWorkflowResponse,
    ErrorResponse,
    TokenSummary,
    WorkflowDetailResponse,
    WorkflowListResponse,
    WorkflowSummary,
)
from amelia.server.models.state import (
    InvalidStateTransitionError,
    ServerExecutionState,
    VALID_TRANSITIONS,
    WorkflowStatus,
    validate_transition,
)
from amelia.server.models.tokens import MODEL_PRICING, TokenUsage, calculate_token_cost

__all__ = [
    # Events
    "EventType",
    "WorkflowEvent",
    # State
    "WorkflowStatus",
    "ServerExecutionState",
    "VALID_TRANSITIONS",
    "InvalidStateTransitionError",
    "validate_transition",
    # Tokens
    "TokenUsage",
    "MODEL_PRICING",
    "calculate_token_cost",
    # Requests
    "CreateWorkflowRequest",
    "RejectRequest",
    # Responses
    "CreateWorkflowResponse",
    "WorkflowSummary",
    "WorkflowListResponse",
    "WorkflowDetailResponse",
    "TokenSummary",
    "ErrorResponse",
]
```

**Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_requests.py tests/unit/server/models/test_responses.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add amelia/server/models/requests.py amelia/server/models/responses.py amelia/server/models/__init__.py tests/unit/server/models/test_requests.py tests/unit/server/models/test_responses.py
git commit -m "feat(models): add request/response schemas with validation"
```

---

## Task 3: Create FastAPI Router with Exception Handlers

**Files:**
- Create: `amelia/server/routes/__init__.py`
- Create: `amelia/server/routes/workflows.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/routes/test_workflows.py
"""Tests for workflow API endpoints."""
import pytest
from datetime import datetime
from uuid import uuid4
from httpx import AsyncClient
from fastapi import FastAPI, status


@pytest.fixture
def app():
    """Create test FastAPI app."""
    from amelia.server.routes.workflows import router, configure_exception_handlers

    app = FastAPI()
    app.include_router(router, prefix="/api")
    configure_exception_handlers(app)
    return app


@pytest.fixture
async def client(app):
    """Create async test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_repository(monkeypatch):
    """Mock WorkflowRepository for testing."""
    from unittest.mock import AsyncMock

    class MockRepository:
        def __init__(self):
            self.workflows = {}
            self.create = AsyncMock(side_effect=self._create)
            self.get = AsyncMock(side_effect=self._get)
            self.get_by_worktree = AsyncMock(return_value=None)
            self.list_active = AsyncMock(return_value=[])
            self.count_active = AsyncMock(return_value=0)
            self.set_status = AsyncMock()

        async def _create(self, state):
            self.workflows[state.id] = state

        async def _get(self, workflow_id):
            return self.workflows.get(workflow_id)

    mock_repo = MockRepository()

    # Override dependency
    from amelia.server.routes import workflows

    async def override_get_repository():
        return mock_repo

    monkeypatch.setattr(workflows, "get_repository", override_get_repository)
    return mock_repo


class TestExceptionHandlers:
    """Tests for exception handlers."""

    @pytest.mark.asyncio
    async def test_workflow_conflict_returns_409(self, app, client):
        """WorkflowConflictError returns 409 with details."""
        from amelia.server.routes.workflows import router
        from amelia.server.exceptions import WorkflowConflictError

        @router.get("/test-conflict")
        async def test_conflict():
            raise WorkflowConflictError(
                worktree_path="/path/to/repo",
                workflow_id="wf-123",
            )

        response = await client.get("/api/test-conflict")

        assert response.status_code == status.HTTP_409_CONFLICT
        body = response.json()
        assert body["code"] == "WORKFLOW_CONFLICT"
        assert "already active" in body["error"].lower()
        assert body["details"]["worktree_path"] == "/path/to/repo"
        assert body["details"]["workflow_id"] == "wf-123"

    @pytest.mark.asyncio
    async def test_concurrency_limit_returns_429(self, app, client):
        """ConcurrencyLimitError returns 429 with Retry-After header."""
        from amelia.server.routes.workflows import router
        from amelia.server.exceptions import ConcurrencyLimitError

        @router.get("/test-limit")
        async def test_limit():
            raise ConcurrencyLimitError(max_concurrent=5, current_count=5)

        response = await client.get("/api/test-limit")

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"] == "30"
        body = response.json()
        assert body["code"] == "CONCURRENCY_LIMIT"

    @pytest.mark.asyncio
    async def test_invalid_state_returns_422(self, app, client):
        """InvalidStateError returns 422."""
        from amelia.server.routes.workflows import router
        from amelia.server.exceptions import InvalidStateError

        @router.get("/test-invalid-state")
        async def test_invalid_state():
            raise InvalidStateError(
                message="Cannot approve: not blocked",
                workflow_id="wf-456",
            )

        response = await client.get("/api/test-invalid-state")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        body = response.json()
        assert body["code"] == "INVALID_STATE"
        assert "Cannot approve" in body["error"]

    @pytest.mark.asyncio
    async def test_workflow_not_found_returns_404(self, app, client):
        """WorkflowNotFoundError returns 404."""
        from amelia.server.routes.workflows import router
        from amelia.server.exceptions import WorkflowNotFoundError

        @router.get("/test-not-found")
        async def test_not_found():
            raise WorkflowNotFoundError(workflow_id="wf-missing")

        response = await client.get("/api/test-not-found")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        body = response.json()
        assert body["code"] == "NOT_FOUND"
        assert "not found" in body["error"].lower()

    @pytest.mark.asyncio
    async def test_validation_error_returns_400(self, app, client):
        """Pydantic ValidationError returns 400."""
        from amelia.server.routes.workflows import router
        from pydantic import BaseModel, Field

        class TestRequest(BaseModel):
            value: int = Field(..., ge=1, le=10)

        @router.post("/test-validation")
        async def test_validation(req: TestRequest):
            return {"ok": True}

        response = await client.post("/test-validation", json={"value": 100})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        body = response.json()
        assert body["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_generic_exception_returns_500(self, app, client):
        """Generic exceptions return 500."""
        from amelia.server.routes.workflows import router

        @router.get("/test-error")
        async def test_error():
            raise RuntimeError("Something went wrong")

        response = await client.get("/api/test-error")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        body = response.json()
        assert body["code"] == "INTERNAL_ERROR"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_workflows.py::TestExceptionHandlers -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create routes package**

```python
# amelia/server/routes/__init__.py
"""API routes for Amelia server."""
from amelia.server.routes.workflows import router as workflows_router

__all__ = ["workflows_router"]
```

**Step 4: Implement router with exception handlers**

```python
# amelia/server/routes/workflows.py
"""Workflow API endpoints."""
from typing import Annotated

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import ValidationError

from amelia.server.database import WorkflowRepository
from amelia.server.exceptions import (
    ConcurrencyLimitError,
    InvalidStateError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.server.models.responses import ErrorResponse

router = APIRouter()


# Dependency injection (will be properly implemented in later tasks)
async def get_repository() -> WorkflowRepository:
    """Get workflow repository instance.

    This is a placeholder that will be properly implemented
    when we add database connection management.
    """
    raise NotImplementedError("Repository dependency not yet implemented")


def configure_exception_handlers(app: FastAPI) -> None:
    """Configure exception handlers for the FastAPI app.

    Args:
        app: FastAPI application instance.
    """

    @app.exception_handler(WorkflowConflictError)
    async def workflow_conflict_handler(
        request: Request,
        exc: WorkflowConflictError,
    ) -> JSONResponse:
        """Handle workflow conflict errors (409).

        Args:
            request: FastAPI request.
            exc: WorkflowConflictError exception.

        Returns:
            JSON response with 409 status.
        """
        logger.warning(f"Workflow conflict: {exc}")
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse(
                error=str(exc),
                code="WORKFLOW_CONFLICT",
                details={
                    "worktree_path": exc.worktree_path,
                    "workflow_id": exc.workflow_id,
                },
            ).model_dump(),
        )

    @app.exception_handler(ConcurrencyLimitError)
    async def concurrency_limit_handler(
        request: Request,
        exc: ConcurrencyLimitError,
    ) -> JSONResponse:
        """Handle concurrency limit errors (429).

        Args:
            request: FastAPI request.
            exc: ConcurrencyLimitError exception.

        Returns:
            JSON response with 429 status and Retry-After header.
        """
        logger.warning(f"Concurrency limit reached: {exc}")
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=ErrorResponse(
                error=str(exc),
                code="CONCURRENCY_LIMIT",
                details={
                    "max_concurrent": exc.max_concurrent,
                    "current_count": exc.current_count,
                },
            ).model_dump(),
            headers={"Retry-After": "30"},
        )

    @app.exception_handler(InvalidStateError)
    async def invalid_state_handler(
        request: Request,
        exc: InvalidStateError,
    ) -> JSONResponse:
        """Handle invalid state errors (422).

        Args:
            request: FastAPI request.
            exc: InvalidStateError exception.

        Returns:
            JSON response with 422 status.
        """
        logger.warning(f"Invalid state transition: {exc}")
        details = {"workflow_id": exc.workflow_id}
        if exc.current_status:
            details["current_status"] = exc.current_status
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error=str(exc),
                code="INVALID_STATE",
                details=details,
            ).model_dump(),
        )

    @app.exception_handler(WorkflowNotFoundError)
    async def workflow_not_found_handler(
        request: Request,
        exc: WorkflowNotFoundError,
    ) -> JSONResponse:
        """Handle workflow not found errors (404).

        Args:
            request: FastAPI request.
            exc: WorkflowNotFoundError exception.

        Returns:
            JSON response with 404 status.
        """
        logger.warning(f"Workflow not found: {exc.workflow_id}")
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                error=str(exc),
                code="NOT_FOUND",
                details={"workflow_id": exc.workflow_id},
            ).model_dump(),
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(
        request: Request,
        exc: ValidationError,
    ) -> JSONResponse:
        """Handle Pydantic validation errors (400).

        Args:
            request: FastAPI request.
            exc: Pydantic ValidationError.

        Returns:
            JSON response with 400 status.
        """
        logger.warning(f"Validation error: {exc}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                error="Validation failed",
                code="VALIDATION_ERROR",
                details={"errors": exc.errors()},
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Handle generic exceptions (500).

        Args:
            request: FastAPI request.
            exc: Any unhandled exception.

        Returns:
            JSON response with 500 status.
        """
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="Internal server error",
                code="INTERNAL_ERROR",
            ).model_dump(),
        )
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_workflows.py::TestExceptionHandlers -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/routes/__init__.py amelia/server/routes/workflows.py tests/unit/server/routes/test_workflows.py
git commit -m "feat(routes): add FastAPI router with exception handlers"
```

---

## Task 4: Implement POST /api/workflows Endpoint

**Files:**
- Modify: `amelia/server/routes/workflows.py`
- Modify: `tests/unit/server/routes/test_workflows.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/server/routes/test_workflows.py

class TestCreateWorkflow:
    """Tests for POST /api/workflows endpoint."""

    @pytest.mark.asyncio
    async def test_create_workflow_success(self, client, mock_repository):
        """Successfully create a workflow."""
        response = await client.post(
            "/api/workflows",
            json={
                "issue_id": "ISSUE-123",
                "worktree_path": "/tmp/test-repo",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        body = response.json()
        assert "id" in body
        assert body["status"] == "pending"
        assert "created" in body["message"].lower()

        # Verify repository was called
        mock_repository.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_workflow_with_optional_fields(self, client, mock_repository):
        """Create workflow with optional fields."""
        response = await client.post(
            "/api/workflows",
            json={
                "issue_id": "ISSUE-456",
                "worktree_path": "/tmp/repo",
                "worktree_name": "feature-branch",
                "profile": "work",
                "driver": "sdk:claude",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

    @pytest.mark.asyncio
    async def test_create_workflow_conflict(self, client, mock_repository):
        """Creating workflow in busy worktree returns 409."""
        from amelia.server.models.state import ServerExecutionState

        # Simulate existing active workflow
        existing = ServerExecutionState(
            id="wf-existing",
            issue_id="ISSUE-1",
            worktree_path="/tmp/test-repo",
            worktree_name="main",
            workflow_status="in_progress",
        )
        mock_repository.get_by_worktree.return_value = existing

        response = await client.post(
            "/api/workflows",
            json={
                "issue_id": "ISSUE-123",
                "worktree_path": "/tmp/test-repo",
            },
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        body = response.json()
        assert body["code"] == "WORKFLOW_CONFLICT"

    @pytest.mark.asyncio
    async def test_create_workflow_at_concurrency_limit(self, client, mock_repository):
        """Creating workflow at limit returns 429."""
        # Simulate max concurrent workflows
        mock_repository.count_active.return_value = 5

        response = await client.post(
            "/api/workflows",
            json={
                "issue_id": "ISSUE-123",
                "worktree_path": "/tmp/test-repo",
            },
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        body = response.json()
        assert body["code"] == "CONCURRENCY_LIMIT"
        assert "Retry-After" in response.headers

    @pytest.mark.asyncio
    async def test_create_workflow_validation_error(self, client, mock_repository):
        """Invalid request returns 400."""
        response = await client.post(
            "/api/workflows",
            json={
                "issue_id": "ISSUE/123",  # Invalid character
                "worktree_path": "/tmp/repo",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        body = response.json()
        assert body["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_create_workflow_derives_worktree_name(self, client, mock_repository):
        """Worktree name is derived from path if not provided."""
        response = await client.post(
            "/api/workflows",
            json={
                "issue_id": "ISSUE-123",
                "worktree_path": "/tmp/my-project",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

        # Check that repository.create was called with derived name
        call_args = mock_repository.create.call_args
        state = call_args[0][0]
        assert state.worktree_name == "my-project"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_workflows.py::TestCreateWorkflow -v`
Expected: FAIL (endpoint not implemented)

**Step 3: Implement POST /workflows endpoint**

```python
# Add to amelia/server/routes/workflows.py

import os
from uuid import uuid4
from fastapi import Depends, status

from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.models.responses import CreateWorkflowResponse
from amelia.server.models.state import ServerExecutionState

# Configuration constant (will be moved to config later)
MAX_CONCURRENT_WORKFLOWS = int(os.environ.get("AMELIA_MAX_CONCURRENT", "5"))


@router.post("/workflows", status_code=status.HTTP_201_CREATED)
async def create_workflow(
    request: CreateWorkflowRequest,
    repository: WorkflowRepository = Depends(get_repository),
) -> CreateWorkflowResponse:
    """Create a new workflow.

    Args:
        request: Workflow creation request.
        repository: Workflow repository dependency.

    Returns:
        Created workflow response.

    Raises:
        WorkflowConflictError: If worktree already has active workflow.
        ConcurrencyLimitError: If max concurrent workflows reached.
    """
    # Check for worktree conflict
    existing = await repository.get_by_worktree(request.worktree_path)
    if existing is not None:
        raise WorkflowConflictError(
            worktree_path=request.worktree_path,
            workflow_id=existing.id,
        )

    # Check concurrency limit
    active_count = await repository.count_active()
    if active_count >= MAX_CONCURRENT_WORKFLOWS:
        raise ConcurrencyLimitError(
            max_concurrent=MAX_CONCURRENT_WORKFLOWS,
            current_count=active_count,
        )

    # Derive worktree name from path if not provided
    worktree_name = request.worktree_name
    if worktree_name is None:
        from pathlib import Path
        worktree_name = Path(request.worktree_path).name

    # Create workflow record
    workflow_id = str(uuid4())
    state = ServerExecutionState(
        id=workflow_id,
        issue_id=request.issue_id,
        worktree_path=request.worktree_path,
        worktree_name=worktree_name,
        workflow_status="pending",
    )

    await repository.create(state)

    logger.info(
        f"Created workflow {workflow_id} for issue {request.issue_id} "
        f"in {request.worktree_path}"
    )

    return CreateWorkflowResponse(
        id=workflow_id,
        status="pending",
        message=f"Workflow created for issue {request.issue_id}",
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_workflows.py::TestCreateWorkflow -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/routes/workflows.py tests/unit/server/routes/test_workflows.py
git commit -m "feat(routes): implement POST /api/workflows endpoint"
```

---

## Task 5: Implement GET /api/workflows and GET /api/workflows/active

**Files:**
- Modify: `amelia/server/routes/workflows.py`
- Modify: `tests/unit/server/routes/test_workflows.py`
- Modify: `amelia/server/database/repository.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/server/routes/test_workflows.py

class TestListWorkflows:
    """Tests for GET /api/workflows endpoint."""

    @pytest.mark.asyncio
    async def test_list_workflows_empty(self, client, mock_repository):
        """List workflows when none exist."""
        mock_repository.list_workflows = AsyncMock(return_value=[])
        mock_repository.count_workflows = AsyncMock(return_value=0)

        response = await client.get("/api/workflows")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["workflows"] == []
        assert body["total"] == 0
        assert body["has_more"] is False

    @pytest.mark.asyncio
    async def test_list_workflows_with_results(self, client, mock_repository):
        """List workflows returns results."""
        from amelia.server.models.state import ServerExecutionState
        from datetime import datetime

        workflows = [
            ServerExecutionState(
                id="wf-1",
                issue_id="ISSUE-1",
                worktree_path="/repo1",
                worktree_name="main",
                workflow_status="in_progress",
                started_at=datetime.utcnow(),
                current_stage="development",
            ),
            ServerExecutionState(
                id="wf-2",
                issue_id="ISSUE-2",
                worktree_path="/repo2",
                worktree_name="feat",
                workflow_status="blocked",
                started_at=datetime.utcnow(),
                current_stage="planning",
            ),
        ]

        mock_repository.list_workflows = AsyncMock(return_value=workflows)
        mock_repository.count_workflows = AsyncMock(return_value=2)

        response = await client.get("/api/workflows")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert len(body["workflows"]) == 2
        assert body["total"] == 2

    @pytest.mark.asyncio
    async def test_list_workflows_filter_by_status(self, client, mock_repository):
        """List workflows can filter by status."""
        mock_repository.list_workflows = AsyncMock(return_value=[])
        mock_repository.count_workflows = AsyncMock(return_value=0)

        response = await client.get("/api/workflows?status=in_progress")

        assert response.status_code == status.HTTP_200_OK
        # Verify repository was called with status filter
        mock_repository.list_workflows.assert_called_once()
        call_kwargs = mock_repository.list_workflows.call_args.kwargs
        assert call_kwargs["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_list_workflows_pagination(self, client, mock_repository):
        """List workflows supports pagination."""
        from amelia.server.models.state import ServerExecutionState
        from datetime import datetime

        # Return limit+1 to simulate has_more
        workflows = [
            ServerExecutionState(
                id=f"wf-{i}",
                issue_id=f"ISSUE-{i}",
                worktree_path=f"/repo{i}",
                worktree_name=f"wt{i}",
                workflow_status="pending",
                started_at=datetime(2025, 1, i, 12, 0, 0),
            )
            for i in range(1, 22)  # 21 items (limit is 20)
        ]

        mock_repository.list_workflows = AsyncMock(return_value=workflows)
        mock_repository.count_workflows = AsyncMock(return_value=100)

        response = await client.get("/api/workflows?limit=20")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert len(body["workflows"]) == 20  # Trimmed to limit
        assert body["has_more"] is True
        assert body["cursor"] is not None  # Cursor for next page

    @pytest.mark.asyncio
    async def test_list_workflows_with_cursor(self, client, mock_repository):
        """List workflows accepts cursor for pagination."""
        import base64

        mock_repository.list_workflows = AsyncMock(return_value=[])
        mock_repository.count_workflows = AsyncMock(return_value=0)

        # Create valid cursor
        cursor_data = "2025-01-15T12:00:00|wf-123"
        cursor = base64.b64encode(cursor_data.encode()).decode()

        response = await client.get(f"/api/workflows?cursor={cursor}")

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_list_workflows_invalid_cursor_returns_400(self, client, mock_repository):
        """Invalid cursor returns 400."""
        response = await client.get("/api/workflows?cursor=invalid-base64!!!")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestListActiveWorkflows:
    """Tests for GET /api/workflows/active endpoint."""

    @pytest.mark.asyncio
    async def test_list_active_workflows(self, client, mock_repository):
        """List active workflows."""
        from amelia.server.models.state import ServerExecutionState

        active = [
            ServerExecutionState(
                id="wf-1",
                issue_id="ISSUE-1",
                worktree_path="/repo1",
                worktree_name="main",
                workflow_status="in_progress",
            ),
        ]

        mock_repository.list_active = AsyncMock(return_value=active)

        response = await client.get("/api/workflows/active")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert len(body["workflows"]) == 1
        assert body["workflows"][0]["status"] == "in_progress"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_workflows.py::TestListWorkflows -v`
Expected: FAIL (endpoints not implemented)

**Step 3: Add pagination methods to repository**

```python
# Add to amelia/server/database/repository.py

from datetime import datetime

    async def list_workflows(
        self,
        status: WorkflowStatus | None = None,
        worktree_path: str | None = None,
        limit: int = 20,
        after_started_at: datetime | None = None,
        after_id: str | None = None,
    ) -> list[ServerExecutionState]:
        """List workflows with cursor-based pagination.

        Args:
            status: Filter by status (optional).
            worktree_path: Filter by worktree path (optional).
            limit: Maximum number of results.
            after_started_at: Cursor timestamp for pagination.
            after_id: Cursor workflow ID for pagination.

        Returns:
            List of workflows ordered by started_at DESC, id DESC.
        """
        conditions = []
        params: list = []

        if status:
            conditions.append("status = ?")
            params.append(status)

        if worktree_path:
            conditions.append("worktree_path = ?")
            params.append(worktree_path)

        # Cursor-based pagination
        if after_started_at and after_id:
            conditions.append(
                "(started_at < ? OR (started_at = ? AND id < ?))"
            )
            params.extend([after_started_at, after_started_at, after_id])

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
            SELECT state_json FROM workflows
            WHERE {where_clause}
            ORDER BY started_at DESC, id DESC
            LIMIT ?
        """
        params.append(limit)

        rows = await self._db.fetch_all(query, params)
        return [ServerExecutionState.model_validate_json(row[0]) for row in rows]

    async def count_workflows(
        self,
        status: WorkflowStatus | None = None,
        worktree_path: str | None = None,
    ) -> int:
        """Count workflows matching filters.

        Args:
            status: Filter by status (optional).
            worktree_path: Filter by worktree path (optional).

        Returns:
            Count of matching workflows.
        """
        conditions = []
        params: list = []

        if status:
            conditions.append("status = ?")
            params.append(status)

        if worktree_path:
            conditions.append("worktree_path = ?")
            params.append(worktree_path)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"SELECT COUNT(*) FROM workflows WHERE {where_clause}"
        row = await self._db.fetch_one(query, params)
        return row[0] if row else 0
```

**Step 4: Implement GET /workflows endpoints**

```python
# Add to amelia/server/routes/workflows.py

import base64
from datetime import datetime
from fastapi import Query, HTTPException

from amelia.server.models.responses import WorkflowListResponse, WorkflowSummary
from amelia.server.models.state import WorkflowStatus


@router.get("/workflows")
async def list_workflows(
    status: WorkflowStatus | None = None,
    worktree: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    repository: WorkflowRepository = Depends(get_repository),
) -> WorkflowListResponse:
    """List workflows with cursor-based pagination.

    Args:
        status: Filter by workflow status.
        worktree: Filter by worktree path.
        limit: Maximum results per page (1-100).
        cursor: Opaque pagination cursor.
        repository: Workflow repository dependency.

    Returns:
        Paginated list of workflows.

    Raises:
        HTTPException: If cursor is invalid (400).
    """
    # Decode cursor if provided
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
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cursor format",
            )

    # Fetch one extra to detect has_more
    workflows = await repository.list_workflows(
        status=status,
        worktree_path=worktree,
        limit=limit + 1,
        after_started_at=after_started_at,
        after_id=after_id,
    )

    has_more = len(workflows) > limit
    if has_more:
        workflows = workflows[:limit]

    # Build next cursor from last item
    next_cursor: str | None = None
    if has_more and workflows:
        last = workflows[-1]
        if last.started_at:
            cursor_data = f"{last.started_at.isoformat()}|{last.id}"
            next_cursor = base64.b64encode(cursor_data.encode()).decode()

    total = await repository.count_workflows(status=status, worktree_path=worktree)

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


@router.get("/workflows/active")
async def list_active_workflows(
    repository: WorkflowRepository = Depends(get_repository),
) -> WorkflowListResponse:
    """List all active workflows (pending, in_progress, blocked).

    Args:
        repository: Workflow repository dependency.

    Returns:
        List of active workflows.
    """
    workflows = await repository.list_active()

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
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_workflows.py::TestListWorkflows -v`
Run: `uv run pytest tests/unit/server/routes/test_workflows.py::TestListActiveWorkflows -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/routes/workflows.py amelia/server/database/repository.py tests/unit/server/routes/test_workflows.py
git commit -m "feat(routes): implement GET /api/workflows and /api/workflows/active"
```

---

## Task 6: Implement GET /api/workflows/{id}

**Files:**
- Modify: `amelia/server/routes/workflows.py`
- Modify: `tests/unit/server/routes/test_workflows.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/server/routes/test_workflows.py

class TestGetWorkflow:
    """Tests for GET /api/workflows/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_workflow_success(self, client, mock_repository):
        """Get workflow by ID."""
        from amelia.server.models.state import ServerExecutionState
        from datetime import datetime

        workflow = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/path/to/repo",
            worktree_name="main",
            workflow_status="in_progress",
            started_at=datetime.utcnow(),
            current_stage="development",
        )

        mock_repository.get = AsyncMock(return_value=workflow)

        response = await client.get("/api/workflows/wf-123")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["id"] == "wf-123"
        assert body["issue_id"] == "ISSUE-456"
        assert body["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_get_workflow_not_found(self, client, mock_repository):
        """Get nonexistent workflow returns 404."""
        mock_repository.get = AsyncMock(return_value=None)

        response = await client.get("/api/workflows/wf-missing")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        body = response.json()
        assert body["code"] == "NOT_FOUND"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_workflows.py::TestGetWorkflow -v`
Expected: FAIL (endpoint not implemented)

**Step 3: Implement GET /workflows/{id} endpoint**

```python
# Add to amelia/server/routes/workflows.py

from amelia.server.models.responses import WorkflowDetailResponse


@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    repository: WorkflowRepository = Depends(get_repository),
) -> WorkflowDetailResponse:
    """Get workflow by ID.

    Args:
        workflow_id: Workflow identifier.
        repository: Workflow repository dependency.

    Returns:
        Detailed workflow information.

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist.
    """
    workflow = await repository.get(workflow_id)
    if workflow is None:
        raise WorkflowNotFoundError(workflow_id=workflow_id)

    # TODO: Fetch token usage and recent events from repository
    # For now, return empty collections
    token_usage = {}
    recent_events = []

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
        plan=None,  # TODO: Load plan from state
        token_usage=token_usage,
        recent_events=recent_events,
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_workflows.py::TestGetWorkflow -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/routes/workflows.py tests/unit/server/routes/test_workflows.py
git commit -m "feat(routes): implement GET /api/workflows/{id}"
```

---

## Task 7: Implement POST /api/workflows/{id}/approve and POST /api/workflows/{id}/reject

**Files:**
- Modify: `amelia/server/routes/workflows.py`
- Modify: `tests/unit/server/routes/test_workflows.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/server/routes/test_workflows.py

class TestApproveWorkflow:
    """Tests for POST /api/workflows/{id}/approve endpoint."""

    @pytest.mark.asyncio
    async def test_approve_blocked_workflow(self, client, mock_repository):
        """Approve a blocked workflow."""
        from amelia.server.models.state import ServerExecutionState

        workflow = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/path",
            worktree_name="main",
            workflow_status="blocked",
        )

        mock_repository.get = AsyncMock(return_value=workflow)

        response = await client.post("/api/workflows/wf-123/approve")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["status"] == "approved"

        # Verify status was updated
        mock_repository.set_status.assert_called_once_with("wf-123", "in_progress")

    @pytest.mark.asyncio
    async def test_approve_workflow_not_found(self, client, mock_repository):
        """Approve nonexistent workflow returns 404."""
        from amelia.server.database import WorkflowNotFoundError

        mock_repository.get = AsyncMock(return_value=None)
        mock_repository.set_status = AsyncMock(
            side_effect=WorkflowNotFoundError("wf-missing")
        )

        response = await client.post("/api/workflows/wf-missing/approve")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_approve_workflow_wrong_state(self, client, mock_repository):
        """Approve workflow not in blocked state returns 422."""
        from amelia.server.models.state import ServerExecutionState

        workflow = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/path",
            worktree_name="main",
            workflow_status="in_progress",  # Not blocked
        )

        mock_repository.get = AsyncMock(return_value=workflow)

        response = await client.post("/api/workflows/wf-123/approve")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        body = response.json()
        assert body["code"] == "INVALID_STATE"


class TestRejectWorkflow:
    """Tests for POST /api/workflows/{id}/reject endpoint."""

    @pytest.mark.asyncio
    async def test_reject_blocked_workflow(self, client, mock_repository):
        """Reject a blocked workflow."""
        from amelia.server.models.state import ServerExecutionState

        workflow = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/path",
            worktree_name="main",
            workflow_status="blocked",
        )

        mock_repository.get = AsyncMock(return_value=workflow)

        response = await client.post(
            "/api/workflows/wf-123/reject",
            json={"feedback": "Plan needs more tests"},
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["status"] == "rejected"

        # Verify status was updated with failure reason
        mock_repository.set_status.assert_called_once_with(
            "wf-123",
            "failed",
            failure_reason="Plan needs more tests",
        )

    @pytest.mark.asyncio
    async def test_reject_requires_feedback(self, client, mock_repository):
        """Reject requires feedback field."""
        response = await client.post(
            "/api/workflows/wf-123/reject",
            json={},  # Missing feedback
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_reject_workflow_not_found(self, client, mock_repository):
        """Reject nonexistent workflow returns 404."""
        from amelia.server.database import WorkflowNotFoundError

        mock_repository.get = AsyncMock(return_value=None)
        mock_repository.set_status = AsyncMock(
            side_effect=WorkflowNotFoundError("wf-missing")
        )

        response = await client.post(
            "/api/workflows/wf-missing/reject",
            json={"feedback": "Test"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_workflows.py::TestApproveWorkflow -v`
Run: `uv run pytest tests/unit/server/routes/test_workflows.py::TestRejectWorkflow -v`
Expected: FAIL (endpoints not implemented)

**Step 3: Implement approve/reject endpoints**

```python
# Add to amelia/server/routes/workflows.py

from amelia.server.models.requests import RejectRequest


@router.post("/workflows/{workflow_id}/approve")
async def approve_workflow(
    workflow_id: str,
    repository: WorkflowRepository = Depends(get_repository),
) -> dict:
    """Approve a blocked workflow's plan.

    Args:
        workflow_id: Workflow to approve.
        repository: Workflow repository dependency.

    Returns:
        Success response.

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist.
        InvalidStateError: If workflow is not in blocked state.
    """
    # Check workflow exists and is blocked
    workflow = await repository.get(workflow_id)
    if workflow is None:
        raise WorkflowNotFoundError(workflow_id=workflow_id)

    if workflow.workflow_status != "blocked":
        raise InvalidStateError(
            message=f"Cannot approve: workflow is {workflow.workflow_status}, not blocked",
            workflow_id=workflow_id,
            current_status=workflow.workflow_status,
        )

    # Transition to in_progress
    await repository.set_status(workflow_id, "in_progress")

    logger.info(f"Approved workflow {workflow_id}")

    return {"status": "approved", "workflow_id": workflow_id}


@router.post("/workflows/{workflow_id}/reject")
async def reject_workflow(
    workflow_id: str,
    request: RejectRequest,
    repository: WorkflowRepository = Depends(get_repository),
) -> dict:
    """Reject a blocked workflow's plan.

    Args:
        workflow_id: Workflow to reject.
        request: Rejection request with feedback.
        repository: Workflow repository dependency.

    Returns:
        Success response.

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist.
        InvalidStateError: If workflow is not in blocked state.
    """
    # Check workflow exists and is blocked
    workflow = await repository.get(workflow_id)
    if workflow is None:
        raise WorkflowNotFoundError(workflow_id=workflow_id)

    if workflow.workflow_status != "blocked":
        raise InvalidStateError(
            message=f"Cannot reject: workflow is {workflow.workflow_status}, not blocked",
            workflow_id=workflow_id,
            current_status=workflow.workflow_status,
        )

    # Transition to failed with feedback
    await repository.set_status(
        workflow_id,
        "failed",
        failure_reason=request.feedback,
    )

    logger.info(f"Rejected workflow {workflow_id}: {request.feedback}")

    return {"status": "rejected", "workflow_id": workflow_id}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_workflows.py::TestApproveWorkflow -v`
Run: `uv run pytest tests/unit/server/routes/test_workflows.py::TestRejectWorkflow -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/routes/workflows.py tests/unit/server/routes/test_workflows.py
git commit -m "feat(routes): implement POST /api/workflows/{id}/approve and reject"
```

---

## Task 8: Implement POST /api/workflows/{id}/cancel

**Files:**
- Modify: `amelia/server/routes/workflows.py`
- Modify: `tests/unit/server/routes/test_workflows.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/server/routes/test_workflows.py

class TestCancelWorkflow:
    """Tests for POST /api/workflows/{id}/cancel endpoint."""

    @pytest.mark.asyncio
    async def test_cancel_active_workflow(self, client, mock_repository):
        """Cancel an active workflow."""
        from amelia.server.models.state import ServerExecutionState

        workflow = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/path",
            worktree_name="main",
            workflow_status="in_progress",
        )

        mock_repository.get = AsyncMock(return_value=workflow)

        response = await client.post("/api/workflows/wf-123/cancel")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["status"] == "cancelled"

        # Verify status was updated
        mock_repository.set_status.assert_called_once_with("wf-123", "cancelled")

    @pytest.mark.asyncio
    async def test_cancel_pending_workflow(self, client, mock_repository):
        """Cancel a pending workflow."""
        from amelia.server.models.state import ServerExecutionState

        workflow = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/path",
            worktree_name="main",
            workflow_status="pending",
        )

        mock_repository.get = AsyncMock(return_value=workflow)

        response = await client.post("/api/workflows/wf-123/cancel")

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_cancel_blocked_workflow(self, client, mock_repository):
        """Cancel a blocked workflow."""
        from amelia.server.models.state import ServerExecutionState

        workflow = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/path",
            worktree_name="main",
            workflow_status="blocked",
        )

        mock_repository.get = AsyncMock(return_value=workflow)

        response = await client.post("/api/workflows/wf-123/cancel")

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_cancel_completed_workflow_fails(self, client, mock_repository):
        """Cannot cancel completed workflow."""
        from amelia.server.models.state import ServerExecutionState

        workflow = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/path",
            worktree_name="main",
            workflow_status="completed",
        )

        mock_repository.get = AsyncMock(return_value=workflow)

        response = await client.post("/api/workflows/wf-123/cancel")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        body = response.json()
        assert body["code"] == "INVALID_STATE"

    @pytest.mark.asyncio
    async def test_cancel_workflow_not_found(self, client, mock_repository):
        """Cancel nonexistent workflow returns 404."""
        from amelia.server.database import WorkflowNotFoundError

        mock_repository.get = AsyncMock(return_value=None)
        mock_repository.set_status = AsyncMock(
            side_effect=WorkflowNotFoundError("wf-missing")
        )

        response = await client.post("/api/workflows/wf-missing/cancel")

        assert response.status_code == status.HTTP_404_NOT_FOUND
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_workflows.py::TestCancelWorkflow -v`
Expected: FAIL (endpoint not implemented)

**Step 3: Implement cancel endpoint**

```python
# Add to amelia/server/routes/workflows.py

@router.post("/workflows/{workflow_id}/cancel")
async def cancel_workflow(
    workflow_id: str,
    repository: WorkflowRepository = Depends(get_repository),
) -> dict:
    """Cancel an active workflow.

    Args:
        workflow_id: Workflow to cancel.
        repository: Workflow repository dependency.

    Returns:
        Success response.

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist.
        InvalidStateError: If workflow is already in terminal state.
    """
    # Check workflow exists and is cancellable
    workflow = await repository.get(workflow_id)
    if workflow is None:
        raise WorkflowNotFoundError(workflow_id=workflow_id)

    # Can only cancel active workflows (pending, in_progress, blocked)
    cancellable_states = {"pending", "in_progress", "blocked"}
    if workflow.workflow_status not in cancellable_states:
        raise InvalidStateError(
            message=f"Cannot cancel: workflow is {workflow.workflow_status}",
            workflow_id=workflow_id,
            current_status=workflow.workflow_status,
        )

    # Transition to cancelled
    await repository.set_status(workflow_id, "cancelled")

    logger.info(f"Cancelled workflow {workflow_id}")

    return {"status": "cancelled", "workflow_id": workflow_id}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_workflows.py::TestCancelWorkflow -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/routes/workflows.py tests/unit/server/routes/test_workflows.py
git commit -m "feat(routes): implement POST /api/workflows/{id}/cancel"
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] `uv run pytest tests/unit/server/ -v` - All server tests pass
- [ ] `uv run ruff check amelia/server` - No linting errors
- [ ] `uv run mypy amelia/server` - No type errors
- [ ] All endpoints return proper HTTP status codes
- [ ] Exception handlers return ErrorResponse schema
- [ ] Request validation works for all endpoints
- [ ] Cursor-based pagination works correctly

```python
# Quick verification in Python REPL
from amelia.server.routes.workflows import router
from amelia.server.exceptions import WorkflowConflictError, ConcurrencyLimitError
from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.models.responses import WorkflowListResponse

# Check router has all endpoints
print([r.path for r in router.routes])
# Expected:
# ['/workflows', '/workflows', '/workflows/active', '/workflows/{workflow_id}',
#  '/workflows/{workflow_id}/approve', '/workflows/{workflow_id}/reject',
#  '/workflows/{workflow_id}/cancel']

# Test request validation
req = CreateWorkflowRequest(
    issue_id="ISSUE-123",
    worktree_path="/tmp/test",
)
print(req.issue_id)  # Should work

# Test exception
try:
    raise WorkflowConflictError("/path", "wf-123")
except WorkflowConflictError as e:
    print(e.worktree_path)  # Should print "/path"
```

---

## Summary

This plan implements the REST API workflow endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/workflows` | POST | Create new workflow |
| `/api/workflows` | GET | List workflows with pagination |
| `/api/workflows/active` | GET | List active workflows |
| `/api/workflows/{id}` | GET | Get workflow details |
| `/api/workflows/{id}/approve` | POST | Approve blocked workflow |
| `/api/workflows/{id}/reject` | POST | Reject blocked workflow |
| `/api/workflows/{id}/cancel` | POST | Cancel active workflow |

**Key Features:**
- Custom exception classes (409, 422, 429, 404, 400, 500)
- Request/response schemas with Pydantic validation
- Cursor-based pagination for list endpoints
- FastAPI exception handlers
- Comprehensive error handling
- Input validation (issue_id, worktree_path)
- Concurrency limit enforcement
- State machine validation

**Next PR:** WebSocket Event Stream (Plan 5)
