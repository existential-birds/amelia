"""Integration tests for workflow API endpoints.

Tests the HTTP layer with real route handlers, real OrchestratorService,
and real WorkflowRepository (in-memory SQLite). Only mocks at the
LangGraph checkpoint/resume boundary.

Mock boundaries:
- AsyncSqliteSaver: Prevents actual graph execution
- create_implementation_graph: Returns mock graph for approve/reject/cancel

Real components:
- FastAPI route handlers
- OrchestratorService
- WorkflowRepository with in-memory SQLite
- Request/Response model validation
- Exception handlers
"""

import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from amelia.pipelines.implementation.state import ImplementationState
from amelia.server.database.connection import Database
from amelia.server.database.repository import WorkflowRepository
from amelia.server.dependencies import get_orchestrator, get_repository
from amelia.server.events.bus import EventBus
from amelia.server.main import create_app
from amelia.server.models.state import ServerExecutionState, WorkflowStatus
from amelia.server.orchestrator.service import OrchestratorService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def test_db(temp_db_path: Path) -> AsyncGenerator[Database, None]:
    """Create and initialize in-memory SQLite database."""
    db = Database(temp_db_path)
    await db.connect()
    await db.ensure_schema()
    yield db
    await db.close()


@pytest.fixture
def test_repository(test_db: Database) -> WorkflowRepository:
    """Create repository backed by test database."""
    return WorkflowRepository(test_db)


@pytest.fixture
def test_event_bus() -> EventBus:
    """Create event bus for testing."""
    return EventBus()


@pytest.fixture
def temp_checkpoint_db(tmp_path: Path) -> str:
    """Create temporary checkpoint database path."""
    return str(tmp_path / "checkpoints.db")


@pytest.fixture
def test_orchestrator(
    test_event_bus: EventBus,
    test_repository: WorkflowRepository,
    temp_checkpoint_db: str,
) -> OrchestratorService:
    """Create real OrchestratorService with test dependencies."""
    return OrchestratorService(
        event_bus=test_event_bus,
        repository=test_repository,
        checkpoint_path=temp_checkpoint_db,
    )


@pytest.fixture
def test_client(
    test_orchestrator: OrchestratorService,
    test_repository: WorkflowRepository,
) -> TestClient:
    """Create test client with real dependencies."""
    app = create_app()

    # Create a no-op lifespan that doesn't initialize database/orchestrator
    @asynccontextmanager
    async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
        yield

    app.router.lifespan_context = noop_lifespan
    app.dependency_overrides[get_orchestrator] = lambda: test_orchestrator
    app.dependency_overrides[get_repository] = lambda: test_repository

    return TestClient(app)


async def create_test_workflow(
    repository: WorkflowRepository,
    workflow_id: str = "wf-001",
    issue_id: str = "TEST-001",
    worktree_path: str = "/tmp/test-repo",
    workflow_status: WorkflowStatus = "pending",
    profile_id: str = "test",
) -> ServerExecutionState:
    """Create and persist a test workflow.

    Args:
        repository: Repository to persist to.
        workflow_id: Workflow ID.
        issue_id: Issue ID.
        worktree_path: Worktree path.
        workflow_status: Initial status.
        profile_id: Profile ID for execution state.

    Returns:
        Created ServerExecutionState.
    """
    execution_state = ImplementationState(
        workflow_id=workflow_id,
        profile_id=profile_id,
        created_at=datetime.now(UTC),
        status="pending",
    )
    workflow = ServerExecutionState(
        id=workflow_id,
        issue_id=issue_id,
        worktree_path=worktree_path,
        workflow_status=workflow_status,
        started_at=datetime.now(UTC),
        execution_state=execution_state,
    )
    await repository.create(workflow)
    return workflow


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
        test_client: TestClient,
        test_repository: WorkflowRepository,
        mock_settings: MagicMock,
        langgraph_mock_factory: Any,
    ) -> None:
        """Successful approval returns 200 with ActionResponse."""
        # Create workflow in "blocked" state (awaiting approval)
        await create_test_workflow(
            test_repository,
            workflow_id="wf-approve-ok",
            workflow_status="blocked",
        )

        # Mock LangGraph to prevent actual graph execution
        mocks = langgraph_mock_factory(astream_items=[])
        with (
            patch(
                "amelia.server.orchestrator.service.AsyncSqliteSaver"
            ) as mock_saver_class,
            patch(
                "amelia.server.orchestrator.service.create_implementation_graph"
            ) as mock_create_graph,
            patch.object(
                OrchestratorService,
                "_load_settings_for_worktree",
                return_value=mock_settings,
            ),
        ):
            mock_create_graph.return_value = mocks.graph
            mock_saver_class.from_conn_string.return_value = (
                mocks.saver_class.from_conn_string.return_value
            )

            response = test_client.post("/api/workflows/wf-approve-ok/approve")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "approved"
        assert data["workflow_id"] == "wf-approve-ok"

    async def test_approve_workflow_not_found_returns_404(
        self,
        test_client: TestClient,
    ) -> None:
        """Approving non-existent workflow returns 404."""
        response = test_client.post("/api/workflows/wf-nonexistent/approve")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["code"] == "NOT_FOUND"

    async def test_approve_workflow_invalid_state_returns_422(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Approving workflow not in blocked state returns 422."""
        # Create workflow in "in_progress" state (not awaiting approval)
        await create_test_workflow(
            test_repository,
            workflow_id="wf-running",
            workflow_status="in_progress",
        )

        response = test_client.post("/api/workflows/wf-running/approve")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        assert data["code"] == "INVALID_STATE"
        assert data["details"]["workflow_id"] == "wf-running"
        assert data["details"]["current_status"] == "in_progress"


@pytest.mark.integration
class TestRejectWorkflowEndpoint:
    """Tests for POST /api/workflows/{id}/reject endpoint.

    Uses real OrchestratorService with mocked LangGraph checkpoint/resume.
    """

    async def test_reject_workflow_returns_200(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        mock_settings: MagicMock,
        langgraph_mock_factory: Any,
    ) -> None:
        """Successful rejection returns 200 with ActionResponse."""
        # Create workflow in "blocked" state
        await create_test_workflow(
            test_repository,
            workflow_id="wf-reject-ok",
            workflow_status="blocked",
        )

        # Mock LangGraph
        mocks = langgraph_mock_factory()
        with (
            patch(
                "amelia.server.orchestrator.service.AsyncSqliteSaver"
            ) as mock_saver_class,
            patch(
                "amelia.server.orchestrator.service.create_implementation_graph"
            ) as mock_create_graph,
            patch.object(
                OrchestratorService,
                "_load_settings_for_worktree",
                return_value=mock_settings,
            ),
        ):
            mock_create_graph.return_value = mocks.graph
            mock_saver_class.from_conn_string.return_value = (
                mocks.saver_class.from_conn_string.return_value
            )

            response = test_client.post(
                "/api/workflows/wf-reject-ok/reject",
                json={"feedback": "Please add more tests"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "rejected"
        assert data["workflow_id"] == "wf-reject-ok"

        # Verify workflow status was updated to failed
        workflow = await test_repository.get("wf-reject-ok")
        assert workflow is not None
        assert workflow.workflow_status == "failed"
        assert workflow.failure_reason == "Please add more tests"

    async def test_reject_workflow_not_found_returns_404(
        self,
        test_client: TestClient,
    ) -> None:
        """Rejecting non-existent workflow returns 404."""
        response = test_client.post(
            "/api/workflows/wf-ghost/reject",
            json={"feedback": "Rejected"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["code"] == "NOT_FOUND"

    async def test_reject_workflow_invalid_state_returns_422(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Rejecting workflow not in blocked state returns 422."""
        # Create workflow in "completed" state
        await create_test_workflow(
            test_repository,
            workflow_id="wf-completed",
            workflow_status="completed",
        )

        response = test_client.post(
            "/api/workflows/wf-completed/reject",
            json={"feedback": "Changes needed"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        assert data["code"] == "INVALID_STATE"

    async def test_reject_workflow_requires_feedback(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Rejection without feedback returns 422 validation error."""
        await create_test_workflow(
            test_repository,
            workflow_id="wf-needs-feedback",
            workflow_status="blocked",
        )

        response = test_client.post(
            "/api/workflows/wf-needs-feedback/reject",
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
        test_client: TestClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Successful cancellation returns 200 with ActionResponse."""
        # Create workflow in "in_progress" state (cancellable)
        await create_test_workflow(
            test_repository,
            workflow_id="wf-cancel-ok",
            workflow_status="in_progress",
        )

        response = test_client.post("/api/workflows/wf-cancel-ok/cancel")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "cancelled"
        assert data["workflow_id"] == "wf-cancel-ok"

        # Verify workflow status was updated
        workflow = await test_repository.get("wf-cancel-ok")
        assert workflow is not None
        assert workflow.workflow_status == "cancelled"

    async def test_cancel_workflow_not_found_returns_404(
        self,
        test_client: TestClient,
    ) -> None:
        """Cancelling non-existent workflow returns 404."""
        response = test_client.post("/api/workflows/wf-phantom/cancel")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["code"] == "NOT_FOUND"

    @pytest.mark.parametrize(
        "workflow_status",
        ["completed", "failed", "cancelled"],
    )
    async def test_cancel_workflow_terminal_state_returns_422(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        workflow_status: WorkflowStatus,
    ) -> None:
        """Cancelling workflow in terminal state returns 422."""
        await create_test_workflow(
            test_repository,
            workflow_id=f"wf-{workflow_status}",
            workflow_status=workflow_status,
        )

        response = test_client.post(f"/api/workflows/wf-{workflow_status}/cancel")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        assert data["code"] == "INVALID_STATE"


@pytest.mark.integration
class TestListWorkflowsEndpoint:
    """Tests for GET /api/workflows endpoint.

    Uses real WorkflowRepository with in-memory SQLite.
    No LLM mocking needed - only reads from database.
    """

    async def test_list_workflows_returns_200(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Successful list returns 200 with WorkflowListResponse."""
        # Create sample workflows
        await create_test_workflow(
            test_repository, "wf-001", "TEST-001", "/tmp/repo1", "pending"
        )
        await create_test_workflow(
            test_repository, "wf-002", "TEST-002", "/tmp/repo2", "in_progress"
        )
        await create_test_workflow(
            test_repository, "wf-003", "TEST-003", "/tmp/repo3", "completed"
        )

        response = test_client.get("/api/workflows")

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
        test_client: TestClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """List with status filter returns only matching workflows."""
        await create_test_workflow(
            test_repository, "wf-pending-1", "TEST-P1", "/tmp/pending1", "pending"
        )
        await create_test_workflow(
            test_repository, "wf-pending-2", "TEST-P2", "/tmp/pending2", "pending"
        )
        await create_test_workflow(
            test_repository, "wf-completed", "TEST-C", "/tmp/completed", "completed"
        )

        response = test_client.get("/api/workflows?status=pending")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 2
        assert all(wf["status"] == "pending" for wf in data["workflows"])

    async def test_list_workflows_with_worktree_filter(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """List with worktree filter filters by path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Resolve path to canonical form (e.g., /tmp -> /private/tmp on macOS)
            resolved_path = str(Path(tmp_dir).resolve())
            await create_test_workflow(
                test_repository, "wf-t1", "TEST-T1", resolved_path, "pending"
            )
            await create_test_workflow(
                test_repository, "wf-t2", "TEST-T2", "/other/path", "pending"
            )

            response = test_client.get(f"/api/workflows?worktree={tmp_dir}")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            # Should only return workflow matching the worktree
            assert data["total"] == 1
            assert data["workflows"][0]["id"] == "wf-t1"

    async def test_list_workflows_with_pagination(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """List with limit returns limited results with has_more indicator."""
        # Create 5 workflows
        for i in range(5):
            await create_test_workflow(
                test_repository,
                f"wf-page-{i}",
                f"TEST-{i}",
                f"/tmp/page{i}",
                "pending",
            )

        response = test_client.get("/api/workflows?limit=2")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["workflows"]) == 2
        assert data["has_more"] is True
        assert data["cursor"] is not None

    async def test_list_workflows_invalid_cursor_returns_400(
        self,
        test_client: TestClient,
    ) -> None:
        """Invalid cursor returns 400 error."""
        response = test_client.get("/api/workflows?cursor=invalid-base64!")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    async def test_list_workflows_empty_returns_empty_list(
        self,
        test_client: TestClient,
    ) -> None:
        """List with no workflows returns empty list."""
        response = test_client.get("/api/workflows")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["workflows"] == []
        assert data["total"] == 0


@pytest.mark.integration
class TestListActiveWorkflowsEndpoint:
    """Tests for GET /api/workflows/active endpoint.

    Uses real WorkflowRepository with in-memory SQLite.
    """

    async def test_list_active_returns_200(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Successful list returns 200 with only active workflows."""
        # Create mix of active and terminal workflows
        await create_test_workflow(
            test_repository, "wf-active-1", "TEST-A1", "/tmp/a1", "pending"
        )
        await create_test_workflow(
            test_repository, "wf-active-2", "TEST-A2", "/tmp/a2", "in_progress"
        )
        await create_test_workflow(
            test_repository, "wf-active-3", "TEST-A3", "/tmp/a3", "blocked"
        )
        await create_test_workflow(
            test_repository, "wf-done", "TEST-D", "/tmp/done", "completed"
        )
        await create_test_workflow(
            test_repository, "wf-err", "TEST-E", "/tmp/err", "failed"
        )

        response = test_client.get("/api/workflows/active")

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
        test_client: TestClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """List active with worktree filter filters by path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Resolve path to canonical form (e.g., /tmp -> /private/tmp on macOS)
            resolved_path = str(Path(tmp_dir).resolve())
            await create_test_workflow(
                test_repository, "wf-wt1", "TEST-WT1", resolved_path, "in_progress"
            )
            await create_test_workflow(
                test_repository, "wf-wt2", "TEST-WT2", "/other/path", "pending"
            )

            response = test_client.get(f"/api/workflows/active?worktree={tmp_dir}")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total"] == 1
            assert data["workflows"][0]["id"] == "wf-wt1"

    async def test_list_active_empty_returns_empty_list(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """List active with no active workflows returns empty list."""
        # Create only terminal workflows
        await create_test_workflow(
            test_repository, "wf-c1", "TEST-C1", "/tmp/c1", "completed"
        )
        await create_test_workflow(
            test_repository, "wf-c2", "TEST-C2", "/tmp/c2", "cancelled"
        )

        response = test_client.get("/api/workflows/active")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["workflows"] == []
        assert data["total"] == 0
        assert data["has_more"] is False
