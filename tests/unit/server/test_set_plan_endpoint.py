"""Unit tests for POST /api/workflows/{id}/plan endpoint."""

from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from amelia.server.dependencies import get_orchestrator
from amelia.server.main import create_app

# Fixed UUID for deterministic URL paths in tests
_WF_ID = uuid4()
_WF_URL = f"/api/workflows/{_WF_ID}/plan"


class TestSetPlanEndpoint:
    """Tests for POST /api/workflows/{id}/plan endpoint."""

    @pytest.fixture
    def mock_orchestrator(self) -> MagicMock:
        """Create mock orchestrator."""
        mock = MagicMock()
        mock.set_workflow_plan = AsyncMock(
            return_value={
                "status": "validating",
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
        """Setting plan with inline content returns 200 with validating status."""
        response = test_client.post(
            _WF_URL,
            json={"plan_content": "# Plan\n\n### Task 1: Do thing"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "validating"
        assert data["total_tasks"] == 2
        assert data.get("goal") is None
        assert data.get("key_files") is None

    def test_set_plan_requires_either_file_or_content(
        self, test_client: TestClient
    ) -> None:
        """Request without plan_file or plan_content returns 422."""
        response = test_client.post(
            _WF_URL,
            json={},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_set_plan_with_plan_file(
        self, test_client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Setting plan with plan_file returns 200."""
        response = test_client.post(
            _WF_URL,
            json={"plan_file": "docs/plan.md"},
        )

        assert response.status_code == status.HTTP_200_OK
        mock_orchestrator.set_workflow_plan.assert_called_once_with(
            workflow_id=ANY,
            plan_file="docs/plan.md",
            plan_content=None,
            force=False,
        )
        # Verify UUID type
        call_kwargs = mock_orchestrator.set_workflow_plan.call_args[1]
        assert isinstance(call_kwargs["workflow_id"], UUID)

    def test_set_plan_with_force_flag(
        self, test_client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Setting plan with force=true passes force to orchestrator."""
        response = test_client.post(
            _WF_URL,
            json={"plan_content": "# Plan", "force": True},
        )

        assert response.status_code == status.HTTP_200_OK
        mock_orchestrator.set_workflow_plan.assert_called_once_with(
            workflow_id=ANY,
            plan_file=None,
            plan_content="# Plan",
            force=True,
        )

    def test_set_plan_mutually_exclusive_fields(
        self, test_client: TestClient
    ) -> None:
        """Request with both plan_file and plan_content returns 422."""
        response = test_client.post(
            _WF_URL,
            json={"plan_file": "plan.md", "plan_content": "# Plan"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
