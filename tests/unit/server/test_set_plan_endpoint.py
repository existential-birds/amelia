"""Unit tests for POST /api/workflows/{id}/plan endpoint."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from amelia.server.dependencies import get_orchestrator
from amelia.server.main import create_app


class TestSetPlanEndpoint:
    """Tests for POST /api/workflows/{id}/plan endpoint."""

    @pytest.fixture
    def mock_orchestrator(self) -> MagicMock:
        """Create mock orchestrator."""
        mock = MagicMock()
        mock.set_workflow_plan = AsyncMock(
            return_value={
                "goal": "Test goal",
                "key_files": ["file.py"],
                "total_tasks": 2,
            }
        )
        return mock

    @pytest.fixture
    def test_client(self, mock_orchestrator: MagicMock) -> TestClient:
        """Create test client with mocked orchestrator."""
        app = create_app()
        app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator
        return TestClient(app)

    def test_set_plan_with_inline_content(
        self, test_client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Setting plan with inline content returns 200."""
        response = test_client.post(
            "/api/workflows/wf-001/plan",
            json={"plan_content": "# Plan\n\n### Task 1: Do thing"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["goal"] == "Test goal"
        assert data["key_files"] == ["file.py"]
        assert data["total_tasks"] == 2

    def test_set_plan_requires_either_file_or_content(
        self, test_client: TestClient
    ) -> None:
        """Request without plan_file or plan_content returns 422."""
        response = test_client.post(
            "/api/workflows/wf-001/plan",
            json={},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_set_plan_with_plan_file(
        self, test_client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Setting plan with plan_file returns 200."""
        response = test_client.post(
            "/api/workflows/wf-001/plan",
            json={"plan_file": "docs/plan.md"},
        )

        assert response.status_code == status.HTTP_200_OK
        mock_orchestrator.set_workflow_plan.assert_called_once_with(
            workflow_id="wf-001",
            plan_file="docs/plan.md",
            plan_content=None,
            force=False,
        )

    def test_set_plan_with_force_flag(
        self, test_client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Setting plan with force=true passes force to orchestrator."""
        response = test_client.post(
            "/api/workflows/wf-001/plan",
            json={"plan_content": "# Plan", "force": True},
        )

        assert response.status_code == status.HTTP_200_OK
        mock_orchestrator.set_workflow_plan.assert_called_once_with(
            workflow_id="wf-001",
            plan_file=None,
            plan_content="# Plan",
            force=True,
        )

    def test_set_plan_mutually_exclusive_fields(
        self, test_client: TestClient
    ) -> None:
        """Request with both plan_file and plan_content returns 422."""
        response = test_client.post(
            "/api/workflows/wf-001/plan",
            json={"plan_file": "plan.md", "plan_content": "# Plan"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
