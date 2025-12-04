"""Tests for workflow routes."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from amelia.server.database import WorkflowRepository
from amelia.server.exceptions import (
    ConcurrencyLimitError,
    InvalidStateError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.service import OrchestratorService
from amelia.server.routes.workflows import (
    configure_exception_handlers,
    get_orchestrator,
    get_repository,
    router,
)


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Create a mock workflow repository."""
    return AsyncMock(spec=WorkflowRepository)


@pytest.fixture
def mock_orchestrator() -> AsyncMock:
    """Create a mock orchestrator service."""
    return AsyncMock(spec=OrchestratorService)


@pytest.fixture
def app(mock_repository: AsyncMock, mock_orchestrator: AsyncMock) -> FastAPI:
    """Create a test FastAPI app."""
    test_app = FastAPI()
    configure_exception_handlers(test_app)
    test_app.include_router(router)
    test_app.dependency_overrides[get_repository] = lambda: mock_repository
    test_app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator
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

    async def test_approve_workflow_not_found(
        self, client: AsyncClient, mock_orchestrator: AsyncMock
    ):
        """Approve nonexistent workflow returns 404."""

        mock_orchestrator.approve_workflow.side_effect = WorkflowNotFoundError(
            "wf-missing"
        )

        response = await client.post("/workflows/wf-missing/approve")

        assert response.status_code == 404

    async def test_approve_workflow_wrong_state(
        self,
        client: AsyncClient,
        mock_orchestrator: AsyncMock,
    ):
        """Approve workflow not in blocked state returns 422."""

        mock_orchestrator.approve_workflow.side_effect = InvalidStateError(
            "Workflow not in blocked state", "wf-123", "in_progress"
        )

        response = await client.post("/workflows/wf-123/approve")

        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "INVALID_STATE"


class TestRejectWorkflow:
    """Tests for POST /api/workflows/{id}/reject endpoint."""

    async def test_reject_workflow_not_found(
        self, client: AsyncClient, mock_orchestrator: AsyncMock
    ):
        """Reject nonexistent workflow returns 404."""

        mock_orchestrator.reject_workflow.side_effect = WorkflowNotFoundError(
            "wf-missing"
        )

        response = await client.post(
            "/workflows/wf-missing/reject",
            json={"feedback": "Test"},
        )

        assert response.status_code == 404


class TestCreateWorkflow:
    """Test POST /workflows endpoint."""

    async def test_create_workflow_success(
        self, client: AsyncClient, mock_orchestrator: AsyncMock
    ):
        """POST /workflows should return 201 with id, status, and message."""
        mock_orchestrator.start_workflow.return_value = "wf-123"

        response = await client.post(
            "/workflows",
            json={
                "issue_id": "ISSUE-123",
                "worktree_path": "/tmp/worktree-123",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "wf-123"
        assert data["status"] == "pending"
        assert "ISSUE-123" in data["message"]

        # Verify orchestrator was called with canonicalized path
        expected_path = str(Path("/tmp/worktree-123").resolve())
        mock_orchestrator.start_workflow.assert_called_once()
        call_kwargs = mock_orchestrator.start_workflow.call_args.kwargs
        assert call_kwargs["issue_id"] == "ISSUE-123"
        assert call_kwargs["worktree_path"] == expected_path

    async def test_create_workflow_with_optional_fields(
        self, client: AsyncClient, mock_orchestrator: AsyncMock
    ):
        """POST /workflows should accept optional profile, driver, and worktree_name."""
        mock_orchestrator.start_workflow.return_value = "wf-456"

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

        # Verify orchestrator received optional fields
        call_kwargs = mock_orchestrator.start_workflow.call_args.kwargs
        assert call_kwargs["worktree_name"] == "custom-name"
        assert call_kwargs["profile"] == "work"
        assert call_kwargs["driver"] == "api:openai"

    async def test_create_workflow_conflict(
        self,
        client: AsyncClient,
        mock_orchestrator: AsyncMock,
    ):
        """POST /workflows should return 409 when worktree is busy."""

        expected_path = str(Path("/tmp/worktree-123").resolve())
        mock_orchestrator.start_workflow.side_effect = WorkflowConflictError(
            expected_path, "existing-id"
        )

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

    async def test_create_workflow_at_concurrency_limit(
        self, client: AsyncClient, mock_orchestrator: AsyncMock
    ):
        """POST /workflows should return 429 when at concurrency limit."""

        mock_orchestrator.start_workflow.side_effect = ConcurrencyLimitError(5, 5)

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


class TestCancelWorkflow:
    """Tests for POST /api/workflows/{id}/cancel endpoint."""

    async def test_cancel_completed_workflow_fails(
        self,
        client: AsyncClient,
        mock_orchestrator: AsyncMock,
    ):
        """Cannot cancel completed workflow."""

        mock_orchestrator.cancel_workflow.side_effect = InvalidStateError(
            "Cannot cancel completed workflow", "wf-123", "completed"
        )

        response = await client.post("/workflows/wf-123/cancel")

        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "INVALID_STATE"

    async def test_cancel_workflow_not_found(
        self, client: AsyncClient, mock_orchestrator: AsyncMock
    ):
        """Cancel nonexistent workflow returns 404."""

        mock_orchestrator.cancel_workflow.side_effect = WorkflowNotFoundError(
            "wf-missing"
        )

        response = await client.post("/workflows/wf-missing/cancel")

        assert response.status_code == 404
