# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for workflow routes."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from amelia.core.state import (
    BatchApproval,
    BatchResult,
    BlockerReport,
    ExecutionBatch,
    ExecutionPlan,
    ExecutionState,
    PlanStep,
    StepResult,
)
from amelia.core.types import DeveloperStatus, Issue, Profile
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

    async def test_get_workflow_returns_plan_as_none(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """Get workflow returns None for legacy plan field (deprecated)."""
        # Create a test profile
        profile = Profile(
            name="test",
            driver="cli:claude",
            tracker="noop",
            strategy="single",
        )

        # Create a test issue
        issue = Issue(
            id="TEST-123",
            title="Test Issue",
            description="Test issue description",
            status="open",
        )

        # Create an execution plan with batches (new model)
        step = PlanStep(
            id="step-1",
            description="Run test",
            action_type="command",
            command="pytest tests/",
        )
        batch = ExecutionBatch(
            batch_number=1,
            steps=(step,),
            risk_summary="low",
            description="Test batch",
        )
        execution_plan = ExecutionPlan(
            goal="Test goal",
            batches=(batch,),
            total_estimated_minutes=5,
            tdd_approach=True,
        )

        # Create ExecutionState with execution_plan
        execution_state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            execution_plan=execution_plan,
        )

        # Create ServerExecutionState with the execution_state
        workflow = make_workflow(
            id="wf-123",
            issue_id="TEST-123",
            status="in_progress",
            execution_state=execution_state,
            current_stage="development",
        )

        # Mock repository to return the workflow
        mock_repository.get.return_value = workflow
        mock_repository.get_recent_events.return_value = []

        # Call GET /workflows/{id}
        response = await client.get("/workflows/wf-123")

        # Assert response is successful
        assert response.status_code == 200
        data = response.json()

        # Assert legacy plan field is None (deprecated in favor of execution_plan)
        assert data["plan"] is None, "Legacy plan field should be None"
        # execution_plan should be present
        assert data["execution_plan"] is not None


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
                "driver": "api:openrouter",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "pending"

        # Verify orchestrator received optional fields
        call_kwargs = mock_orchestrator.start_workflow.call_args.kwargs
        assert call_kwargs["worktree_name"] == "custom-name"
        assert call_kwargs["profile"] == "work"
        assert call_kwargs["driver"] == "api:openrouter"

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


class TestBatchExecutionFields:
    """Tests for batch execution fields in WorkflowDetailResponse."""

    async def test_get_workflow_returns_execution_plan(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """Get workflow returns execution_plan when present."""
        # Create a test profile
        profile = Profile(
            name="test",
            driver="cli:claude",
            tracker="noop",
            strategy="single",
        )

        # Create a test issue
        issue = Issue(
            id="TEST-123",
            title="Test Issue",
            description="Test issue description",
            status="open",
        )

        # Create an execution plan with batches
        step1 = PlanStep(
            id="step-1",
            description="Run tests",
            action_type="command",
            command="pytest tests/",
            risk_level="low",
        )
        step2 = PlanStep(
            id="step-2",
            description="Build project",
            action_type="command",
            command="npm run build",
            risk_level="medium",
        )
        batch1 = ExecutionBatch(
            batch_number=1,
            steps=(step1,),
            risk_summary="low",
            description="Test batch",
        )
        batch2 = ExecutionBatch(
            batch_number=2,
            steps=(step2,),
            risk_summary="medium",
            description="Build batch",
        )
        execution_plan = ExecutionPlan(
            goal="Test and build the project",
            batches=(batch1, batch2),
            total_estimated_minutes=10,
            tdd_approach=True,
        )

        # Create ExecutionState with the execution plan
        execution_state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            execution_plan=execution_plan,
            current_batch_index=0,
        )

        # Create ServerExecutionState with the execution_state
        workflow = make_workflow(
            id="wf-123",
            issue_id="TEST-123",
            status="in_progress",
            execution_state=execution_state,
            current_stage="development",
        )

        # Mock repository to return the workflow
        mock_repository.get.return_value = workflow
        mock_repository.get_recent_events.return_value = []

        # Call GET /workflows/{id}
        response = await client.get("/workflows/wf-123")

        # Assert response is successful
        assert response.status_code == 200
        data = response.json()

        # Assert execution_plan data is returned
        assert data["execution_plan"] is not None
        assert data["execution_plan"]["goal"] == "Test and build the project"
        assert len(data["execution_plan"]["batches"]) == 2
        assert data["execution_plan"]["batches"][0]["batch_number"] == 1
        assert data["execution_plan"]["batches"][0]["description"] == "Test batch"
        assert len(data["execution_plan"]["batches"][0]["steps"]) == 1
        assert data["execution_plan"]["batches"][0]["steps"][0]["id"] == "step-1"
        assert data["execution_plan"]["total_estimated_minutes"] == 10
        assert data["execution_plan"]["tdd_approach"] is True

    async def test_get_workflow_returns_batch_results(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """Get workflow returns batch_results when present."""
        # Create a test profile and issue
        profile = Profile(
            name="test",
            driver="cli:claude",
            tracker="noop",
            strategy="single",
        )
        issue = Issue(
            id="TEST-123",
            title="Test Issue",
            description="Test issue description",
            status="open",
        )

        # Create batch results
        step_result1 = StepResult(
            step_id="step-1",
            status="completed",
            output="Tests passed",
            executed_command="pytest tests/",
            duration_seconds=5.0,
        )
        batch_result1 = BatchResult(
            batch_number=1,
            status="complete",
            completed_steps=(step_result1,),
        )
        batch_results = [batch_result1]

        # Create ExecutionState with batch results
        execution_state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            current_batch_index=1,
            batch_results=batch_results,
        )

        # Create ServerExecutionState
        workflow = make_workflow(
            id="wf-123",
            issue_id="TEST-123",
            status="in_progress",
            execution_state=execution_state,
        )

        mock_repository.get.return_value = workflow
        mock_repository.get_recent_events.return_value = []

        # Call GET /workflows/{id}
        response = await client.get("/workflows/wf-123")

        # Assert response
        assert response.status_code == 200
        data = response.json()

        # Assert batch_results data is returned
        assert data["current_batch_index"] == 1
        assert len(data["batch_results"]) == 1
        assert data["batch_results"][0]["batch_number"] == 1
        assert data["batch_results"][0]["status"] == "complete"
        assert len(data["batch_results"][0]["completed_steps"]) == 1
        assert data["batch_results"][0]["completed_steps"][0]["step_id"] == "step-1"
        assert data["batch_results"][0]["completed_steps"][0]["status"] == "completed"
        assert data["batch_results"][0]["completed_steps"][0]["output"] == "Tests passed"

    async def test_get_workflow_returns_developer_status(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """Get workflow returns developer_status."""
        profile = Profile(
            name="test",
            driver="cli:claude",
            tracker="noop",
            strategy="single",
        )
        issue = Issue(
            id="TEST-123",
            title="Test Issue",
            description="Test issue description",
            status="open",
        )

        # Create ExecutionState with specific developer status
        execution_state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            developer_status=DeveloperStatus.BATCH_COMPLETE,
        )

        workflow = make_workflow(
            id="wf-123",
            issue_id="TEST-123",
            status="in_progress",
            execution_state=execution_state,
        )

        mock_repository.get.return_value = workflow
        mock_repository.get_recent_events.return_value = []

        response = await client.get("/workflows/wf-123")

        assert response.status_code == 200
        data = response.json()
        assert data["developer_status"] == "batch_complete"

    async def test_get_workflow_returns_current_blocker(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """Get workflow returns current_blocker when present."""
        profile = Profile(
            name="test",
            driver="cli:claude",
            tracker="noop",
            strategy="single",
        )
        issue = Issue(
            id="TEST-123",
            title="Test Issue",
            description="Test issue description",
            status="open",
        )

        # Create a blocker report
        blocker = BlockerReport(
            step_id="step-2",
            step_description="Build project",
            blocker_type="command_failed",
            error_message="npm build failed with exit code 1",
            attempted_actions=("Retried build command", "Checked dependencies"),
            suggested_resolutions=("Fix build errors", "Update dependencies"),
        )

        # Create ExecutionState with blocker
        execution_state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            developer_status=DeveloperStatus.BLOCKED,
            current_blocker=blocker,
        )

        workflow = make_workflow(
            id="wf-123",
            issue_id="TEST-123",
            status="blocked",
            execution_state=execution_state,
        )

        mock_repository.get.return_value = workflow
        mock_repository.get_recent_events.return_value = []

        response = await client.get("/workflows/wf-123")

        assert response.status_code == 200
        data = response.json()
        assert data["current_blocker"] is not None
        assert data["current_blocker"]["step_id"] == "step-2"
        assert data["current_blocker"]["step_description"] == "Build project"
        assert data["current_blocker"]["blocker_type"] == "command_failed"
        assert data["current_blocker"]["error_message"] == "npm build failed with exit code 1"
        assert len(data["current_blocker"]["attempted_actions"]) == 2
        assert len(data["current_blocker"]["suggested_resolutions"]) == 2

    async def test_get_workflow_returns_batch_approvals(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """Get workflow returns batch_approvals when present."""
        profile = Profile(
            name="test",
            driver="cli:claude",
            tracker="noop",
            strategy="single",
        )
        issue = Issue(
            id="TEST-123",
            title="Test Issue",
            description="Test issue description",
            status="open",
        )

        # Create batch approvals
        now = datetime.now(UTC)
        approval1 = BatchApproval(
            batch_number=1,
            approved=True,
            feedback="Looks good",
            approved_at=now,
        )
        batch_approvals = [approval1]

        # Create ExecutionState with approvals
        execution_state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            batch_approvals=batch_approvals,
        )

        workflow = make_workflow(
            id="wf-123",
            issue_id="TEST-123",
            status="in_progress",
            execution_state=execution_state,
        )

        mock_repository.get.return_value = workflow
        mock_repository.get_recent_events.return_value = []

        response = await client.get("/workflows/wf-123")

        assert response.status_code == 200
        data = response.json()
        assert len(data["batch_approvals"]) == 1
        assert data["batch_approvals"][0]["batch_number"] == 1
        assert data["batch_approvals"][0]["approved"] is True
        assert data["batch_approvals"][0]["feedback"] == "Looks good"

    async def test_get_workflow_with_no_execution_state(
        self,
        client: AsyncClient,
        mock_repository: AsyncMock,
        make_workflow: Callable[..., ServerExecutionState],
    ):
        """Get workflow returns default values when execution_state is None."""
        workflow = make_workflow(
            id="wf-123",
            issue_id="TEST-123",
            status="pending",
            execution_state=None,
        )

        mock_repository.get.return_value = workflow
        mock_repository.get_recent_events.return_value = []

        response = await client.get("/workflows/wf-123")

        assert response.status_code == 200
        data = response.json()
        assert data["execution_plan"] is None
        assert data["current_batch_index"] == 0
        assert data["batch_results"] == []
        assert data["developer_status"] is None
        assert data["current_blocker"] is None
        assert data["batch_approvals"] == []


class TestBatchApprovalEndpoint:
    """Tests for POST /workflows/{id}/batches/{batch_number}/approve endpoint."""

    async def test_approve_batch_success(
        self, client: AsyncClient, mock_orchestrator: AsyncMock
    ):
        """Approve batch should call orchestrator and return success."""
        mock_orchestrator.approve_workflow.return_value = None

        response = await client.post("/workflows/wf-123/batches/1/approve")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        assert data["workflow_id"] == "wf-123"
        mock_orchestrator.approve_workflow.assert_called_once_with("wf-123")

    async def test_approve_batch_not_found(
        self, client: AsyncClient, mock_orchestrator: AsyncMock
    ):
        """Approve batch for nonexistent workflow returns 404."""
        mock_orchestrator.approve_workflow.side_effect = WorkflowNotFoundError("wf-missing")

        response = await client.post("/workflows/wf-missing/batches/1/approve")

        assert response.status_code == 404

    async def test_approve_batch_invalid_state(
        self, client: AsyncClient, mock_orchestrator: AsyncMock
    ):
        """Approve batch when not in correct state returns 422."""
        mock_orchestrator.approve_workflow.side_effect = InvalidStateError(
            "Workflow not ready for approval", "wf-123", "in_progress"
        )

        response = await client.post("/workflows/wf-123/batches/1/approve")

        assert response.status_code == 422


class TestBlockerResolutionEndpoint:
    """Tests for POST /workflows/{id}/blocker/resolve endpoint."""

    async def test_resolve_blocker_skip(
        self, client: AsyncClient, mock_orchestrator: AsyncMock
    ):
        """Resolve blocker with skip action."""
        mock_orchestrator.resolve_blocker.return_value = None

        response = await client.post(
            "/workflows/wf-123/blocker/resolve",
            json={"action": "skip", "feedback": "Skip this step"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "skipped"
        assert data["workflow_id"] == "wf-123"
        mock_orchestrator.resolve_blocker.assert_called_once_with(
            workflow_id="wf-123", action="skip", feedback="Skip this step"
        )

    async def test_resolve_blocker_retry(
        self, client: AsyncClient, mock_orchestrator: AsyncMock
    ):
        """Resolve blocker with retry action."""
        mock_orchestrator.resolve_blocker.return_value = None

        response = await client.post(
            "/workflows/wf-123/blocker/resolve",
            json={"action": "retry"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "retrying"
        mock_orchestrator.resolve_blocker.assert_called_once_with(
            workflow_id="wf-123", action="retry", feedback=None
        )

    async def test_resolve_blocker_abort(
        self, client: AsyncClient, mock_orchestrator: AsyncMock
    ):
        """Resolve blocker with abort action."""
        mock_orchestrator.resolve_blocker.return_value = None

        response = await client.post(
            "/workflows/wf-123/blocker/resolve",
            json={"action": "abort"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "aborted"
        mock_orchestrator.resolve_blocker.assert_called_once_with(
            workflow_id="wf-123", action="abort", feedback=None
        )

    async def test_resolve_blocker_abort_revert(
        self, client: AsyncClient, mock_orchestrator: AsyncMock
    ):
        """Resolve blocker with abort_revert action."""
        mock_orchestrator.resolve_blocker.return_value = None

        response = await client.post(
            "/workflows/wf-123/blocker/resolve",
            json={"action": "abort_revert"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "aborted"
        mock_orchestrator.resolve_blocker.assert_called_once_with(
            workflow_id="wf-123", action="abort_revert", feedback=None
        )

    async def test_resolve_blocker_fix(
        self, client: AsyncClient, mock_orchestrator: AsyncMock
    ):
        """Resolve blocker with fix action."""
        mock_orchestrator.resolve_blocker.return_value = None

        response = await client.post(
            "/workflows/wf-123/blocker/resolve",
            json={"action": "fix", "feedback": "Use this command instead"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "fix_provided"
        mock_orchestrator.resolve_blocker.assert_called_once_with(
            workflow_id="wf-123", action="fix", feedback="Use this command instead"
        )

    async def test_resolve_blocker_not_found(
        self, client: AsyncClient, mock_orchestrator: AsyncMock
    ):
        """Resolve blocker for nonexistent workflow returns 404."""
        mock_orchestrator.resolve_blocker.side_effect = WorkflowNotFoundError("wf-missing")

        response = await client.post(
            "/workflows/wf-missing/blocker/resolve",
            json={"action": "skip"},
        )

        assert response.status_code == 404

    async def test_resolve_blocker_missing_feedback_for_fix(
        self, client: AsyncClient, mock_orchestrator: AsyncMock
    ):
        """Resolve blocker with fix action and no feedback passes None."""
        mock_orchestrator.resolve_blocker.return_value = None

        response = await client.post(
            "/workflows/wf-123/blocker/resolve",
            json={"action": "fix"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "fix_provided"
        mock_orchestrator.resolve_blocker.assert_called_once_with(
            workflow_id="wf-123", action="fix", feedback=None
        )
