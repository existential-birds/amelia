"""Integration tests for review workflow API endpoints."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient


@pytest.fixture
def mock_orchestrator() -> AsyncMock:
    """Create mock orchestrator service."""
    mock = AsyncMock()
    mock.start_review_workflow = AsyncMock(return_value="wf-review-123")
    return mock


@pytest.fixture
def test_client(mock_orchestrator: AsyncMock) -> TestClient:
    """Create test client with mocked orchestrator."""
    from contextlib import nullcontext

    from amelia.server.dependencies import get_orchestrator
    from amelia.server.main import create_app

    # Create app without the full lifespan context for testing
    app = create_app()
    # Override lifespan to skip database/orchestrator initialization
    app.router.lifespan_context = nullcontext
    app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator

    return TestClient(app)


class TestCreateReviewWorkflowEndpoint:
    """Tests for POST /api/workflows/review endpoint."""

    def test_creates_review_workflow_returns_201(
        self,
        test_client: TestClient,
        mock_orchestrator: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Successful request returns 201 with workflow ID."""
        worktree = tmp_path / "repo"
        worktree.mkdir()

        response = test_client.post(
            "/api/workflows/review",
            json={
                "diff_content": "+ new line",
                "worktree_path": str(worktree),
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["id"] == "wf-review-123"
        assert data["status"] == "pending"

    def test_rejects_empty_diff_content(
        self,
        test_client: TestClient,
        tmp_path: Path,
    ) -> None:
        """Empty diff_content returns 422 validation error."""
        worktree = tmp_path / "repo"
        worktree.mkdir()

        response = test_client.post(
            "/api/workflows/review",
            json={
                "diff_content": "",
                "worktree_path": str(worktree),
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_returns_409_on_workflow_conflict(
        self,
        test_client: TestClient,
        mock_orchestrator: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Returns 409 when worktree has active workflow."""
        from amelia.server.exceptions import WorkflowConflictError

        worktree = tmp_path / "repo"
        worktree.mkdir()

        mock_orchestrator.start_review_workflow.side_effect = WorkflowConflictError(
            str(worktree), "wf-existing"
        )

        response = test_client.post(
            "/api/workflows/review",
            json={
                "diff_content": "+ line",
                "worktree_path": str(worktree),
            },
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["code"] == "WORKFLOW_CONFLICT"
        assert data["details"]["workflow_id"] == "wf-existing"

    def test_rejects_relative_worktree_path(
        self,
        test_client: TestClient,
    ) -> None:
        """Relative worktree path returns 422 validation error."""
        response = test_client.post(
            "/api/workflows/review",
            json={
                "diff_content": "+ line",
                "worktree_path": "relative/path",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        # Should have validation error about path being absolute
        assert "detail" in data
