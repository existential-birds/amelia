"""Tests for workflow routes and exception handlers."""

import base64
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, field_validator

from amelia.server.database import WorkflowRepository
from amelia.server.exceptions import (
    ConcurrencyLimitError,
    InvalidStateError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.server.models.state import ServerExecutionState
from amelia.server.routes.workflows import configure_exception_handlers, get_repository, router


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Create a mock workflow repository."""
    return AsyncMock(spec=WorkflowRepository)


@pytest.fixture
def app(mock_repository: AsyncMock) -> FastAPI:
    """Create a test FastAPI app."""
    test_app = FastAPI()
    configure_exception_handlers(test_app)
    test_app.include_router(router)
    test_app.dependency_overrides[get_repository] = lambda: mock_repository
    return test_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    """Create an async test client."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def make_workflow() -> Callable[..., ServerExecutionState]:
    """Factory fixture for creating test workflows with sensible defaults."""

    def _make(
        id: str = "wf-123",
        status: str = "in_progress",
        issue_id: str = "ISSUE-456",
        worktree_path: str = "/path/to/repo",
        worktree_name: str = "main",
        started_at: datetime | None = None,
        current_stage: str | None = None,
        **kwargs,
    ) -> ServerExecutionState:
        return ServerExecutionState(
            id=id,
            issue_id=issue_id,
            worktree_path=worktree_path,
            worktree_name=worktree_name,
            workflow_status=status,
            started_at=started_at,
            current_stage=current_stage,
            **kwargs,
        )

    return _make


class TestExceptionHandlers:
    """Test exception handlers."""

    async def test_workflow_conflict_returns_409(self, app: FastAPI, client: AsyncClient):
        """WorkflowConflictError should return 409 with code WORKFLOW_CONFLICT."""

        @app.get("/test-conflict")
        async def trigger_conflict():
            raise WorkflowConflictError("/path/to/worktree", "workflow-123")

        response = await client.get("/test-conflict")
        assert response.status_code == 409
        data = response.json()
        assert data["code"] == "WORKFLOW_CONFLICT"
        assert "workflow-123" in data["error"]

    async def test_concurrency_limit_returns_429(self, app: FastAPI, client: AsyncClient):
        """ConcurrencyLimitError should return 429 with Retry-After header."""

        @app.get("/test-concurrency")
        async def trigger_concurrency():
            raise ConcurrencyLimitError(max_concurrent=10, current_count=10)

        response = await client.get("/test-concurrency")
        assert response.status_code == 429
        assert response.headers.get("Retry-After") == "30"
        data = response.json()
        assert data["code"] == "CONCURRENCY_LIMIT"

    async def test_invalid_state_returns_422(self, app: FastAPI, client: AsyncClient):
        """InvalidStateError should return 422 with code INVALID_STATE."""

        @app.get("/test-invalid-state")
        async def trigger_invalid_state():
            raise InvalidStateError(
                "Cannot transition from running to completed",
                "workflow-123",
                "running",
            )

        response = await client.get("/test-invalid-state")
        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "INVALID_STATE"
        assert "running" in data["error"]
        assert "completed" in data["error"]

    async def test_workflow_not_found_returns_404(self, app: FastAPI, client: AsyncClient):
        """WorkflowNotFoundError should return 404 with code NOT_FOUND."""

        @app.get("/test-not-found")
        async def trigger_not_found():
            raise WorkflowNotFoundError("workflow-123")

        response = await client.get("/test-not-found")
        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "NOT_FOUND"
        assert "workflow-123" in data["error"]

    async def test_validation_error_returns_400(self, app: FastAPI, client: AsyncClient):
        """Pydantic ValidationError should return 400 with code VALIDATION_ERROR."""

        @app.get("/test-validation")
        async def trigger_validation():
            class TestModel(BaseModel):
                value: int

                @field_validator("value")
                @classmethod
                def must_be_positive(cls, v: int) -> int:
                    if v <= 0:
                        raise ValueError("must be positive")
                    return v

            TestModel(value=-1)

        response = await client.get("/test-validation")
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "VALIDATION_ERROR"

    async def test_generic_exception_returns_500(self, app: FastAPI, client: AsyncClient):
        """Generic exceptions should return 500 with code INTERNAL_ERROR."""

        @app.get("/test-generic")
        async def trigger_generic():
            raise RuntimeError("Something went wrong")

        response = await client.get("/test-generic")
        assert response.status_code == 500
        data = response.json()
        assert data["code"] == "INTERNAL_ERROR"
        assert "Something went wrong" in data["error"]


class TestListWorkflows:
    """Test GET /workflows endpoint."""

    async def test_list_workflows_empty(
        self, client: AsyncClient, mock_repository: AsyncMock
    ):
        """Empty list returns total=0 and empty workflows array."""
        mock_repository.list_workflows.return_value = []
        mock_repository.count_workflows.return_value = 0

        response = await client.get("/workflows")
        assert response.status_code == 200
        data = response.json()
        assert data["workflows"] == []
        assert data["total"] == 0
        assert data["has_more"] is False

    async def test_list_workflows_with_results(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """List returns workflow summaries."""
        now = datetime.now(UTC)
        workflow = make_workflow(
            started_at=now,
            current_stage="development",
            worktree_name="feature-branch",
        )
        mock_repository.list_workflows.return_value = [workflow]
        mock_repository.count_workflows.return_value = 1

        response = await client.get("/workflows")
        assert response.status_code == 200
        data = response.json()
        assert len(data["workflows"]) == 1
        assert data["workflows"][0]["id"] == "wf-123"
        assert data["workflows"][0]["issue_id"] == "ISSUE-456"
        assert data["workflows"][0]["worktree_name"] == "feature-branch"
        assert data["workflows"][0]["status"] == "in_progress"
        assert data["workflows"][0]["current_stage"] == "development"
        assert data["total"] == 1
        assert data["has_more"] is False

    async def test_list_workflows_filter_by_status(
        self, client: AsyncClient, mock_repository: AsyncMock
    ):
        """Status parameter filters workflows."""
        mock_repository.list_workflows.return_value = []
        mock_repository.count_workflows.return_value = 0

        response = await client.get("/workflows?status=completed")
        assert response.status_code == 200

        mock_repository.list_workflows.assert_called_once()
        call_kwargs = mock_repository.list_workflows.call_args.kwargs
        assert call_kwargs["status"] == "completed"

    async def test_list_workflows_with_worktree_filter(
        self, client: AsyncClient, mock_repository: AsyncMock
    ):
        """Worktree parameter filters workflows by worktree path."""
        mock_repository.list_workflows.return_value = []
        mock_repository.count_workflows.return_value = 0

        response = await client.get("/workflows?worktree=/path/to/worktree")
        assert response.status_code == 200

        mock_repository.list_workflows.assert_called_once()
        call_kwargs = mock_repository.list_workflows.call_args.kwargs
        assert call_kwargs["worktree_path"] == "/path/to/worktree"

        mock_repository.count_workflows.assert_called_once()
        count_kwargs = mock_repository.count_workflows.call_args.kwargs
        assert count_kwargs["worktree_path"] == "/path/to/worktree"

    async def test_list_workflows_pagination(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """Limit works and has_more=True when more results exist."""
        mock_states = [
            make_workflow(
                id=f"wf-{i}",
                issue_id=f"ISSUE-{i}",
                worktree_path=f"/path/{i}",
                worktree_name=f"branch-{i}",
                status="completed",
                started_at=datetime.now(UTC),
            )
            for i in range(3)
        ]
        mock_repository.list_workflows.return_value = mock_states
        mock_repository.count_workflows.return_value = 10

        response = await client.get("/workflows?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["workflows"]) == 2
        assert data["has_more"] is True
        assert data["cursor"] is not None

    async def test_list_workflows_with_cursor(
        self, client: AsyncClient, mock_repository: AsyncMock
    ):
        """Cursor pagination works."""
        now = datetime.now(UTC)
        cursor_data = f"{now.isoformat()}|wf-123"
        cursor = base64.b64encode(cursor_data.encode()).decode()

        mock_repository.list_workflows.return_value = []
        mock_repository.count_workflows.return_value = 0

        response = await client.get(f"/workflows?cursor={cursor}")
        assert response.status_code == 200

        mock_repository.list_workflows.assert_called_once()
        call_kwargs = mock_repository.list_workflows.call_args.kwargs
        assert call_kwargs["after_started_at"] == now
        assert call_kwargs["after_id"] == "wf-123"

    async def test_list_workflows_invalid_cursor_returns_400(
        self, client: AsyncClient, mock_repository: AsyncMock
    ):
        """Invalid cursor returns 400 error."""
        response = await client.get("/workflows?cursor=invalid-cursor")
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "Invalid cursor format" in data["detail"]


class TestListActiveWorkflows:
    """Test GET /workflows/active endpoint."""

    async def test_list_active_workflows(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """GET /workflows/active returns active workflows only."""
        now = datetime.now(UTC)
        mock_states = [
            make_workflow(id="wf-1", issue_id="ISSUE-1", worktree_path="/path/1", worktree_name="branch-1", status="in_progress", started_at=now),
            make_workflow(id="wf-2", issue_id="ISSUE-2", worktree_path="/path/2", worktree_name="branch-2", status="blocked", started_at=now),
        ]
        mock_repository.list_active.return_value = mock_states

        response = await client.get("/workflows/active")
        assert response.status_code == 200
        data = response.json()
        assert len(data["workflows"]) == 2
        assert data["total"] == 2
        assert data["has_more"] is False
        assert data["workflows"][0]["status"] == "in_progress"
        assert data["workflows"][1]["status"] == "blocked"


class TestGetWorkflow:
    """Tests for GET /api/workflows/{id} endpoint."""

    async def test_get_workflow_success(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """Get workflow by ID."""
        workflow = make_workflow(started_at=datetime.now(UTC), current_stage="development")
        mock_repository.get = AsyncMock(return_value=workflow)

        response = await client.get("/workflows/wf-123")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == "wf-123"
        assert body["issue_id"] == "ISSUE-456"
        assert body["status"] == "in_progress"

    async def test_get_workflow_not_found(
        self, client: AsyncClient, mock_repository: AsyncMock
    ):
        """Get nonexistent workflow returns 404."""
        mock_repository.get = AsyncMock(return_value=None)

        response = await client.get("/workflows/wf-missing")

        assert response.status_code == 404
        body = response.json()
        assert body["code"] == "NOT_FOUND"


class TestApproveWorkflow:
    """Tests for POST /api/workflows/{id}/approve endpoint."""

    async def test_approve_blocked_workflow(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """Approve a blocked workflow."""
        workflow = make_workflow(status="blocked")
        mock_repository.get = AsyncMock(return_value=workflow)
        mock_repository.set_status = AsyncMock()

        response = await client.post("/workflows/wf-123/approve")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "approved"
        mock_repository.set_status.assert_called_once_with("wf-123", "in_progress")

    async def test_approve_workflow_not_found(
        self, client: AsyncClient, mock_repository: AsyncMock
    ):
        """Approve nonexistent workflow returns 404."""
        mock_repository.get = AsyncMock(return_value=None)

        response = await client.post("/workflows/wf-missing/approve")

        assert response.status_code == 404

    async def test_approve_workflow_wrong_state(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """Approve workflow not in blocked state returns 422."""
        workflow = make_workflow(status="in_progress")  # Not blocked
        mock_repository.get = AsyncMock(return_value=workflow)

        response = await client.post("/workflows/wf-123/approve")

        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "INVALID_STATE"


class TestRejectWorkflow:
    """Tests for POST /api/workflows/{id}/reject endpoint."""

    async def test_reject_blocked_workflow(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """Reject a blocked workflow."""
        workflow = make_workflow(status="blocked")
        mock_repository.get = AsyncMock(return_value=workflow)
        mock_repository.set_status = AsyncMock()

        response = await client.post(
            "/workflows/wf-123/reject",
            json={"feedback": "Plan needs more tests"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "rejected"
        mock_repository.set_status.assert_called_once_with(
            "wf-123", "failed", failure_reason="Plan needs more tests"
        )

    async def test_reject_requires_feedback(
        self, client: AsyncClient, mock_repository: AsyncMock
    ):
        """Reject requires feedback field."""
        response = await client.post(
            "/workflows/wf-123/reject",
            json={},  # Missing feedback
        )

        assert response.status_code == 422  # Pydantic validation

    async def test_reject_workflow_not_found(
        self, client: AsyncClient, mock_repository: AsyncMock
    ):
        """Reject nonexistent workflow returns 404."""
        mock_repository.get = AsyncMock(return_value=None)

        response = await client.post(
            "/workflows/wf-missing/reject",
            json={"feedback": "Test"},
        )

        assert response.status_code == 404


class TestCreateWorkflow:
    """Test POST /workflows endpoint."""

    async def test_create_workflow_success(
        self, client: AsyncClient, mock_repository: AsyncMock
    ):
        """POST /workflows should return 201 with id, status, and message."""
        mock_repository.get_by_worktree.return_value = None
        mock_repository.count_active.return_value = 0
        mock_repository.create.return_value = None

        response = await client.post(
            "/workflows",
            json={
                "issue_id": "ISSUE-123",
                "worktree_path": "/tmp/worktree-123",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["status"] == "pending"
        assert "ISSUE-123" in data["message"]

        # Path is canonicalized by validator (e.g., /tmp -> /private/tmp on macOS)
        expected_path = str(Path("/tmp/worktree-123").resolve())
        mock_repository.get_by_worktree.assert_called_once_with(expected_path)
        mock_repository.count_active.assert_called_once()
        mock_repository.create.assert_called_once()

    async def test_create_workflow_with_optional_fields(
        self, client: AsyncClient, mock_repository: AsyncMock
    ):
        """POST /workflows should accept optional profile, driver, and worktree_name."""
        mock_repository.get_by_worktree.return_value = None
        mock_repository.count_active.return_value = 0
        mock_repository.create.return_value = None

        response = await client.post(
            "/workflows",
            json={
                "issue_id": "ISSUE-456",
                "worktree_path": "/tmp/worktree-456",
                "worktree_name": "custom-name",
                "profile": "work",
                "driver": "api:openai",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "pending"

        create_call = mock_repository.create.call_args
        created_state: ServerExecutionState = create_call[0][0]
        assert created_state.worktree_name == "custom-name"

    async def test_create_workflow_conflict(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """POST /workflows should return 409 when worktree is busy."""
        existing_workflow = make_workflow(
            id="existing-id",
            issue_id="ISSUE-999",
            worktree_path="/tmp/worktree-123",
            worktree_name="worktree-123",
        )
        mock_repository.get_by_worktree.return_value = existing_workflow

        response = await client.post(
            "/workflows",
            json={
                "issue_id": "ISSUE-123",
                "worktree_path": "/tmp/worktree-123",
            },
        )

        assert response.status_code == 409
        data = response.json()
        assert data["code"] == "WORKFLOW_CONFLICT"
        assert "existing-id" in data["error"]

        mock_repository.count_active.assert_not_called()
        mock_repository.create.assert_not_called()

    async def test_create_workflow_at_concurrency_limit(
        self, client: AsyncClient, mock_repository: AsyncMock
    ):
        """POST /workflows should return 429 when at concurrency limit."""
        mock_repository.get_by_worktree.return_value = None
        mock_repository.count_active.return_value = 5  # At limit (default is 5)

        response = await client.post(
            "/workflows",
            json={
                "issue_id": "ISSUE-123",
                "worktree_path": "/tmp/worktree-123",
            },
        )

        assert response.status_code == 429
        data = response.json()
        assert data["code"] == "CONCURRENCY_LIMIT"
        assert response.headers.get("Retry-After") == "30"

        mock_repository.create.assert_not_called()

    async def test_create_workflow_validation_error(
        self, client: AsyncClient, mock_repository: AsyncMock
    ):
        """POST /workflows should return 422 for invalid issue_id."""
        response = await client.post(
            "/workflows",
            json={
                "issue_id": "ISSUE 123",  # Space is invalid
                "worktree_path": "/tmp/worktree-123",
            },
        )

        # FastAPI returns 422 for validation errors by default
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

        mock_repository.get_by_worktree.assert_not_called()
        mock_repository.count_active.assert_not_called()
        mock_repository.create.assert_not_called()

    async def test_create_workflow_derives_worktree_name(
        self, client: AsyncClient, mock_repository: AsyncMock
    ):
        """POST /workflows should derive worktree_name from path if not provided."""
        mock_repository.get_by_worktree.return_value = None
        mock_repository.count_active.return_value = 0
        mock_repository.create.return_value = None

        response = await client.post(
            "/workflows",
            json={
                "issue_id": "ISSUE-789",
                "worktree_path": "/tmp/my-custom-worktree",
            },
        )

        assert response.status_code == 201

        create_call = mock_repository.create.call_args
        created_state: ServerExecutionState = create_call[0][0]
        assert created_state.worktree_name == "my-custom-worktree"


class TestCancelWorkflow:
    """Tests for POST /api/workflows/{id}/cancel endpoint."""

    async def test_cancel_active_workflow(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """Cancel an active workflow."""
        workflow = make_workflow(status="in_progress")
        mock_repository.get = AsyncMock(return_value=workflow)
        mock_repository.set_status = AsyncMock()

        response = await client.post("/workflows/wf-123/cancel")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "cancelled"
        mock_repository.set_status.assert_called_once_with("wf-123", "cancelled")

    @pytest.mark.parametrize("status", ["pending", "blocked"])
    async def test_cancel_cancellable_states(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
        status: str,
    ):
        """Cancel works for pending and blocked workflows."""
        workflow = make_workflow(status=status)
        mock_repository.get = AsyncMock(return_value=workflow)
        mock_repository.set_status = AsyncMock()

        response = await client.post("/workflows/wf-123/cancel")

        assert response.status_code == 200

    async def test_cancel_completed_workflow_fails(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """Cannot cancel completed workflow."""
        workflow = make_workflow(status="completed")
        mock_repository.get = AsyncMock(return_value=workflow)

        response = await client.post("/workflows/wf-123/cancel")

        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "INVALID_STATE"

    async def test_cancel_workflow_not_found(
        self, client: AsyncClient, mock_repository: AsyncMock
    ):
        """Cancel nonexistent workflow returns 404."""
        mock_repository.get = AsyncMock(return_value=None)

        response = await client.post("/workflows/wf-missing/cancel")

        assert response.status_code == 404
