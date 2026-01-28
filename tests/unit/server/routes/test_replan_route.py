"""Unit tests for the replan workflow route handler."""

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.exceptions import (
    InvalidStateError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.server.routes.workflows import configure_exception_handlers, router

from .conftest import patch_lifespan


def get_orchestrator_mock() -> MagicMock:
    """Create mock orchestrator."""
    mock = MagicMock()
    mock.replan_workflow = AsyncMock()
    return mock


def create_test_client(orchestrator_mock: MagicMock) -> TestClient:
    """Create test client with mocked orchestrator."""
    app = patch_lifespan(FastAPI())

    # Wire the dependency
    from amelia.server.dependencies import get_orchestrator

    app.dependency_overrides[get_orchestrator] = lambda: orchestrator_mock

    app.include_router(router, prefix="/api")
    configure_exception_handlers(app)
    return TestClient(app)


class TestReplanRoute:
    """Tests for POST /api/workflows/{id}/replan."""

    def test_replan_success(self) -> None:
        """Should return 200 with workflow_id and status."""
        orch = get_orchestrator_mock()
        client = create_test_client(orch)

        response = client.post("/api/workflows/wf-123/replan")

        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "wf-123"
        assert data["status"] == "replanning"
        orch.replan_workflow.assert_awaited_once_with("wf-123")

    def test_replan_not_found(self) -> None:
        """Should return 404 for missing workflow."""
        orch = get_orchestrator_mock()
        orch.replan_workflow.side_effect = WorkflowNotFoundError("wf-missing")
        client = create_test_client(orch)

        response = client.post("/api/workflows/wf-missing/replan")
        assert response.status_code == 404

    def test_replan_wrong_status(self) -> None:
        """Should return 422 for non-blocked workflow."""
        orch = get_orchestrator_mock()
        orch.replan_workflow.side_effect = InvalidStateError(
            "Workflow must be in blocked status",
            workflow_id="wf-wrong",
            current_status="in_progress",
        )
        client = create_test_client(orch)

        response = client.post("/api/workflows/wf-wrong/replan")
        assert response.status_code == 422

    def test_replan_conflict(self) -> None:
        """Should return 409 when planning already running."""
        orch = get_orchestrator_mock()
        orch.replan_workflow.side_effect = WorkflowConflictError(
            "Planning task already running for workflow wf-busy"
        )
        client = create_test_client(orch)

        response = client.post("/api/workflows/wf-busy/replan")
        assert response.status_code == 409

    def test_replan_profile_not_found(self) -> None:
        """Should return 400 when profile is not found."""
        orch = get_orchestrator_mock()
        orch.replan_workflow.side_effect = ValueError("Profile 'test' not found")
        client = create_test_client(orch)

        response = client.post("/api/workflows/wf-no-profile/replan")
        assert response.status_code == 400
