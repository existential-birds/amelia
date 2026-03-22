"""Integration tests for workflow API endpoints.

Tests the HTTP layer with real route handlers, real OrchestratorService,
and real WorkflowRepository (PostgreSQL test database). Only mocks at the
LangGraph checkpoint/resume boundary.

Mock boundaries:
- Mock checkpointer: Prevents actual graph execution
- create_implementation_graph: Returns mock graph for approve/reject/cancel

Real components:
- FastAPI route handlers
- OrchestratorService
- WorkflowRepository with PostgreSQL test database
- Request/Response model validation
- Exception handlers
"""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from fastapi import status

from amelia.server.database.repository import WorkflowRepository
from amelia.server.models.state import WorkflowStatus
from tests.integration.conftest import create_test_workflow


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def test_client(orchestrator_test_client: httpx.AsyncClient) -> httpx.AsyncClient:
    """Alias shared orchestrator_test_client fixture for local use."""
    return orchestrator_test_client


# =============================================================================
# Test Classes
# =============================================================================


@pytest.mark.integration
class TestApproveWorkflowEndpoint:
    """Tests for POST /api/workflows/{id}/approve endpoint.

    Uses real OrchestratorService with mocked LangGraph checkpoint/resume.
    """

    async def test_approve_workflow_returns_200(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        langgraph_mock_factory: Any,
    ) -> None:
        """Successful approval returns 200 with ActionResponse."""
        # Create workflow in "blocked" state (awaiting approval)
        workflow = await create_test_workflow(
            test_repository,
            workflow_status="blocked",
        )

        # Mock LangGraph to prevent actual graph execution
        mocks = langgraph_mock_factory(astream_items=[])
        with patch(
            "amelia.server.orchestrator.service.create_implementation_graph"
        ) as mock_create_graph:
            mock_create_graph.return_value = mocks.graph

            response = await test_client.post(f"/api/workflows/{workflow.id}/approve")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "approved"
        assert data["workflow_id"] == str(workflow.id)

    async def test_approve_workflow_not_found_returns_404(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Approving non-existent workflow returns 404."""
        fake_id = uuid4()
        response = await test_client.post(f"/api/workflows/{fake_id}/approve")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["code"] == "NOT_FOUND"

    async def test_approve_workflow_invalid_state_returns_422(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Approving workflow not in blocked state returns 422."""
        # Create workflow in "in_progress" state (not awaiting approval)
        workflow = await create_test_workflow(
            test_repository,
            workflow_status="in_progress",
        )

        response = await test_client.post(f"/api/workflows/{workflow.id}/approve")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        assert data["code"] == "INVALID_STATE"
        assert data["details"]["workflow_id"] == str(workflow.id)
        assert data["details"]["current_status"] == "in_progress"


@pytest.mark.integration
class TestRejectWorkflowEndpoint:
    """Tests for POST /api/workflows/{id}/reject endpoint.

    Uses real OrchestratorService with mocked LangGraph checkpoint/resume.
    """

    async def test_reject_workflow_returns_200(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Successful rejection returns 200 with ActionResponse."""
        # Create workflow in "blocked" state
        workflow = await create_test_workflow(
            test_repository,
            workflow_status="blocked",
        )

        response = await test_client.post(
            f"/api/workflows/{workflow.id}/reject",
            json={"feedback": "Please add more tests"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "rejected"
        assert data["workflow_id"] == str(workflow.id)

        # Verify workflow status was updated to failed
        updated = await test_repository.get(workflow.id)
        assert updated is not None
        assert updated.workflow_status == "failed"
        assert updated.failure_reason == "Please add more tests"

    async def test_reject_workflow_not_found_returns_404(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Rejecting non-existent workflow returns 404."""
        fake_id = uuid4()
        response = await test_client.post(
            f"/api/workflows/{fake_id}/reject",
            json={"feedback": "Rejected"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["code"] == "NOT_FOUND"

    async def test_reject_workflow_invalid_state_returns_422(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Rejecting workflow not in blocked state returns 422."""
        # Create workflow in "completed" state
        workflow = await create_test_workflow(
            test_repository,
            workflow_status="completed",
        )

        response = await test_client.post(
            f"/api/workflows/{workflow.id}/reject",
            json={"feedback": "Changes needed"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        assert data["code"] == "INVALID_STATE"

    async def test_reject_workflow_requires_feedback(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Rejection without feedback returns 422 validation error."""
        workflow = await create_test_workflow(
            test_repository,
            workflow_status="blocked",
        )

        response = await test_client.post(
            f"/api/workflows/{workflow.id}/reject",
            json={},  # Missing feedback
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.integration
class TestCancelWorkflowEndpoint:
    """Tests for POST /api/workflows/{id}/cancel endpoint.

    Uses real OrchestratorService with real repository.
    """

    async def test_cancel_workflow_returns_200(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Successful cancellation returns 200 with ActionResponse."""
        # Create workflow in "in_progress" state (cancellable)
        workflow = await create_test_workflow(
            test_repository,
            workflow_status="in_progress",
        )

        response = await test_client.post(f"/api/workflows/{workflow.id}/cancel")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "cancelled"
        assert data["workflow_id"] == str(workflow.id)

        # Verify workflow status was updated
        updated = await test_repository.get(workflow.id)
        assert updated is not None
        assert updated.workflow_status == "cancelled"

    async def test_cancel_workflow_not_found_returns_404(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Cancelling non-existent workflow returns 404."""
        fake_id = uuid4()
        response = await test_client.post(f"/api/workflows/{fake_id}/cancel")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["code"] == "NOT_FOUND"

    @pytest.mark.parametrize(
        "workflow_status",
        ["completed", "failed", "cancelled"],
    )
    async def test_cancel_workflow_terminal_state_returns_422(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        workflow_status: WorkflowStatus,
    ) -> None:
        """Cancelling workflow in terminal state returns 422."""
        workflow = await create_test_workflow(
            test_repository,
            workflow_status=workflow_status,
        )

        response = await test_client.post(f"/api/workflows/{workflow.id}/cancel")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        assert data["code"] == "INVALID_STATE"


@pytest.mark.integration
class TestListWorkflowsEndpoint:
    """Tests for GET /api/workflows endpoint.

    Uses real WorkflowRepository with PostgreSQL test database.
    No LLM mocking needed - only reads from database.
    """

    async def test_list_workflows_returns_200(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Successful list returns 200 with WorkflowListResponse."""
        # Create sample workflows
        await create_test_workflow(
            test_repository, issue_id="TEST-001", worktree_path="/tmp/repo1", workflow_status="pending"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-002", worktree_path="/tmp/repo2", workflow_status="in_progress"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-003", worktree_path="/tmp/repo3", workflow_status="completed"
        )

        response = await test_client.get("/api/workflows")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "workflows" in data
        assert "total" in data
        assert data["total"] == 3
        assert len(data["workflows"]) == 3

        # Verify workflow summaries have required fields
        wf = data["workflows"][0]
        assert "id" in wf
        assert "issue_id" in wf
        assert "status" in wf

    async def test_list_workflows_with_status_filter(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """List with status filter returns only matching workflows."""
        await create_test_workflow(
            test_repository, issue_id="TEST-P1", worktree_path="/tmp/pending1", workflow_status="pending"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-P2", worktree_path="/tmp/pending2", workflow_status="pending"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-C", worktree_path="/tmp/completed", workflow_status="completed"
        )

        response = await test_client.get("/api/workflows?status=pending")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 2
        assert all(wf["status"] == "pending" for wf in data["workflows"])

    async def test_list_workflows_with_worktree_filter(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """List with worktree filter filters by path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Resolve path to canonical form (e.g., /tmp -> /private/tmp on macOS)
            resolved_path = str(Path(tmp_dir).resolve())
            wf1 = await create_test_workflow(
                test_repository, issue_id="TEST-T1", worktree_path=resolved_path, workflow_status="pending"
            )
            await create_test_workflow(
                test_repository, issue_id="TEST-T2", worktree_path="/other/path", workflow_status="pending"
            )

            response = await test_client.get(f"/api/workflows?worktree={tmp_dir}")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            # Should only return workflow matching the worktree
            assert data["total"] == 1
            assert data["workflows"][0]["id"] == str(wf1.id)

    async def test_list_workflows_with_pagination(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """List with limit returns limited results with has_more indicator."""
        # Create 5 workflows
        for i in range(5):
            await create_test_workflow(
                test_repository,
                issue_id=f"TEST-{i}",
                worktree_path=f"/tmp/page{i}",
                workflow_status="pending",
            )

        response = await test_client.get("/api/workflows?limit=2")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["workflows"]) == 2
        assert data["has_more"] is True
        assert data["cursor"] is not None

    async def test_list_workflows_invalid_cursor_returns_400(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Invalid cursor returns 400 error."""
        response = await test_client.get("/api/workflows?cursor=invalid-base64!")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    async def test_list_workflows_empty_returns_empty_list(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """List with no workflows returns empty list."""
        response = await test_client.get("/api/workflows")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["workflows"] == []
        assert data["total"] == 0


@pytest.mark.integration
class TestListActiveWorkflowsEndpoint:
    """Tests for GET /api/workflows/active endpoint.

    Uses real WorkflowRepository with PostgreSQL test database.
    """

    async def test_list_active_returns_200(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Successful list returns 200 with only active workflows."""
        # Create mix of active and terminal workflows
        await create_test_workflow(
            test_repository, issue_id="TEST-A1", worktree_path="/tmp/a1", workflow_status="pending"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-A2", worktree_path="/tmp/a2", workflow_status="in_progress"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-A3", worktree_path="/tmp/a3", workflow_status="blocked"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-D", worktree_path="/tmp/done", workflow_status="completed"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-E", worktree_path="/tmp/err", workflow_status="failed"
        )

        response = await test_client.get("/api/workflows/active")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "workflows" in data
        assert "total" in data
        assert data["total"] == 3  # Only active workflows
        # Verify only active statuses
        statuses = {wf["status"] for wf in data["workflows"]}
        assert statuses <= {"pending", "in_progress", "blocked"}

    async def test_list_active_with_worktree_filter(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """List active with worktree filter filters by path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Resolve path to canonical form (e.g., /tmp -> /private/tmp on macOS)
            resolved_path = str(Path(tmp_dir).resolve())
            wf1 = await create_test_workflow(
                test_repository, issue_id="TEST-WT1", worktree_path=resolved_path, workflow_status="in_progress"
            )
            await create_test_workflow(
                test_repository, issue_id="TEST-WT2", worktree_path="/other/path", workflow_status="pending"
            )

            response = await test_client.get(f"/api/workflows/active?worktree={tmp_dir}")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total"] == 1
            assert data["workflows"][0]["id"] == str(wf1.id)

    async def test_list_active_empty_returns_empty_list(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """List active with no active workflows returns empty list."""
        # Create only terminal workflows
        await create_test_workflow(
            test_repository, issue_id="TEST-C1", worktree_path="/tmp/c1", workflow_status="completed"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-C2", worktree_path="/tmp/c2", workflow_status="cancelled"
        )

        response = await test_client.get("/api/workflows/active")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["workflows"] == []
        assert data["total"] == 0
        assert data["has_more"] is False
