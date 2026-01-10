# tests/unit/server/routes/test_workflows_queue.py
"""Tests for queue-related workflow endpoints."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from amelia.server.dependencies import get_orchestrator, get_repository
from amelia.server.exceptions import (
    InvalidStateError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.server.main import create_app
from amelia.server.models.responses import BatchStartResponse


@pytest.fixture
def mock_repository() -> MagicMock:
    """Create a mock WorkflowRepository."""
    repo = MagicMock()
    repo.get = AsyncMock()
    repo.get_token_summary = AsyncMock()
    repo.get_recent_events = AsyncMock(return_value=[])
    repo.list_workflows = AsyncMock()
    repo.count_workflows = AsyncMock()
    repo.get_token_summaries_batch = AsyncMock()
    repo.list_active = AsyncMock()
    return repo


@pytest.fixture
def mock_orchestrator() -> MagicMock:
    """Create a mock OrchestratorService with queue methods."""
    orch = MagicMock()
    orch.start_workflow = AsyncMock(return_value="wf-started")
    orch.queue_workflow = AsyncMock(return_value="wf-queued")
    orch.queue_and_plan_workflow = AsyncMock(return_value="wf-planned")
    return orch


@pytest.fixture
def client(mock_repository: MagicMock, mock_orchestrator: MagicMock) -> TestClient:
    """Create test client with mocked dependencies."""
    app = create_app()

    @asynccontextmanager
    async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
        yield

    app.router.lifespan_context = noop_lifespan
    app.dependency_overrides[get_repository] = lambda: mock_repository
    app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator

    return TestClient(app)


class TestCreateWorkflowQueue:
    """Tests for POST /workflows with queue parameters."""

    def test_default_starts_immediately(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Default behavior (start=True) starts workflow immediately."""
        response = client.post(
            "/api/workflows",
            json={"issue_id": "ISSUE-123", "worktree_path": "/repo"},
        )

        assert response.status_code == 201
        mock_orchestrator.start_workflow.assert_called_once()

    def test_queue_without_plan(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """start=False queues without planning."""
        response = client.post(
            "/api/workflows",
            json={
                "issue_id": "ISSUE-123",
                "worktree_path": "/repo",
                "start": False,
            },
        )

        assert response.status_code == 201
        mock_orchestrator.queue_workflow.assert_called_once()
        mock_orchestrator.start_workflow.assert_not_called()

    def test_queue_with_plan(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """start=False, plan_now=True runs Architect then queues."""
        response = client.post(
            "/api/workflows",
            json={
                "issue_id": "ISSUE-123",
                "worktree_path": "/repo",
                "start": False,
                "plan_now": True,
            },
        )

        assert response.status_code == 201
        mock_orchestrator.queue_and_plan_workflow.assert_called_once()

    def test_plan_now_ignored_when_start_true(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """plan_now is ignored when start=True."""
        response = client.post(
            "/api/workflows",
            json={
                "issue_id": "ISSUE-123",
                "worktree_path": "/repo",
                "start": True,
                "plan_now": True,
            },
        )

        assert response.status_code == 201
        mock_orchestrator.start_workflow.assert_called_once()
        mock_orchestrator.queue_and_plan_workflow.assert_not_called()


class TestStartWorkflowEndpoint:
    """Tests for POST /workflows/{id}/start endpoint."""

    def test_start_pending_workflow_success(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Successfully start a pending workflow."""
        mock_orchestrator.start_pending_workflow = AsyncMock()

        response = client.post("/api/workflows/wf-123/start")

        assert response.status_code == 202
        mock_orchestrator.start_pending_workflow.assert_called_once_with("wf-123")

    def test_start_workflow_not_found(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Return 404 when workflow not found."""
        mock_orchestrator.start_pending_workflow = AsyncMock(
            side_effect=WorkflowNotFoundError("wf-nonexistent")
        )

        response = client.post("/api/workflows/wf-nonexistent/start")

        assert response.status_code == 404

    def test_start_workflow_wrong_state(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Return 422 when workflow not pending (via global exception handler)."""
        mock_orchestrator.start_pending_workflow = AsyncMock(
            side_effect=InvalidStateError(
                "Workflow is not in pending state",
                workflow_id="wf-running",
                current_status="in_progress",
            )
        )

        response = client.post("/api/workflows/wf-running/start")

        # InvalidStateError is handled by global handler returning 422
        assert response.status_code == 422

    def test_start_workflow_worktree_conflict(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Return 409 when worktree has active workflow."""
        mock_orchestrator.start_pending_workflow = AsyncMock(
            side_effect=WorkflowConflictError(
                worktree_path="/tmp/worktree",
                workflow_id="wf-existing",
            )
        )

        response = client.post("/api/workflows/wf-123/start")

        assert response.status_code == 409


class TestBatchStartEndpoint:
    """Tests for POST /workflows/start-batch endpoint."""

    def test_batch_start_all(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Start all pending workflows."""
        mock_orchestrator.start_batch_workflows = AsyncMock(
            return_value=BatchStartResponse(
                started=["wf-1", "wf-2"],
                errors={},
            )
        )

        response = client.post("/api/workflows/start-batch", json={})

        assert response.status_code == 200
        data = response.json()
        assert data["started"] == ["wf-1", "wf-2"]
        assert data["errors"] == {}

    def test_batch_start_specific_ids(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Start specific workflow IDs."""
        mock_orchestrator.start_batch_workflows = AsyncMock(
            return_value=BatchStartResponse(started=["wf-1"], errors={})
        )

        response = client.post(
            "/api/workflows/start-batch",
            json={"workflow_ids": ["wf-1"]},
        )

        assert response.status_code == 200
        call_args = mock_orchestrator.start_batch_workflows.call_args[0][0]
        assert call_args.workflow_ids == ["wf-1"]

    def test_batch_start_partial_failure(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Handle partial failures."""
        mock_orchestrator.start_batch_workflows = AsyncMock(
            return_value=BatchStartResponse(
                started=["wf-1"],
                errors={"wf-2": "Worktree conflict"},
            )
        )

        response = client.post("/api/workflows/start-batch", json={})

        assert response.status_code == 200
        data = response.json()
        assert data["started"] == ["wf-1"]
        assert data["errors"]["wf-2"] == "Worktree conflict"
