"""Integration tests for queue workflow flow.

Tests the complete queue workflow lifecycle:
- Queue workflows without starting
- Start individual queued workflows
- Batch start multiple workflows

Uses real OrchestratorService with real WorkflowRepository (PostgreSQL test database).
Only mocks at external boundaries (LangGraph checkpoint/resume).

Mock boundaries:
- Mock checkpointer: Prevents actual graph execution
- create_implementation_graph: Returns mock graph

Real components:
- FastAPI route handlers
- OrchestratorService
- WorkflowRepository with PostgreSQL test database
- Request/Response model validation
"""

import tempfile
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from fastapi import status

from amelia.core.types import Profile
from amelia.server.database.repository import WorkflowRepository
from amelia.server.dependencies import get_orchestrator, get_repository
from amelia.server.main import create_app
from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.service import OrchestratorService
from tests.integration.server.conftest import noop_lifespan


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def test_client(
    test_orchestrator: OrchestratorService,
    test_repository: WorkflowRepository,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create async test client with real dependencies.

    Uses httpx.AsyncClient with ASGITransport so the ASGI app runs in the
    same event loop as the asyncpg pool created by test_db.
    """
    app = create_app()

    app.router.lifespan_context = noop_lifespan
    app.dependency_overrides[get_orchestrator] = lambda: test_orchestrator
    app.dependency_overrides[get_repository] = lambda: test_repository

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


async def create_pending_workflow(
    repository: WorkflowRepository,
    workflow_id: uuid.UUID | None = None,
    issue_id: str = "TEST-001",
    worktree_path: str = "/tmp/test-repo",
) -> ServerExecutionState:
    """Create and persist a pending workflow for testing.

    Args:
        repository: Repository to persist to.
        workflow_id: Workflow ID (UUID). Generated if not provided.
        issue_id: Issue ID.
        worktree_path: Worktree path.

    Returns:
        Created ServerExecutionState in pending status.
    """
    if workflow_id is None:
        workflow_id = uuid4()
    workflow = ServerExecutionState(
        id=workflow_id,
        issue_id=issue_id,
        worktree_path=worktree_path,
        workflow_status="pending",
        # Note: started_at is None for pending workflows (set when started)
    )
    await repository.create(workflow)
    return workflow


# =============================================================================
# Test Classes
# =============================================================================


@pytest.mark.integration
class TestQueueWorkflowCreation:
    """Tests for creating workflows in queued (pending) state."""

    async def test_create_workflow_with_start_false_queues_without_starting(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        active_test_profile: Profile,
        valid_worktree: str,
    ) -> None:
        """Creating workflow with start=False creates it in pending state."""
        response = await test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-QUEUE-001",
                "worktree_path": valid_worktree,
                "start": False,
                "task_title": "Test task",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "id" in data
        workflow_id = data["id"]

        # Verify workflow was created in pending state
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.workflow_status == "pending"
        assert workflow.issue_id == "TEST-QUEUE-001"

    async def test_create_workflow_defaults_to_immediate_start(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        active_test_profile: Profile,
        valid_worktree: str,
        langgraph_mock_factory: Any,
    ) -> None:
        """Creating workflow without start param defaults to start=True."""
        # Mock LangGraph to prevent actual graph execution
        mocks = langgraph_mock_factory(astream_items=[])
        with patch(
            "amelia.server.orchestrator.service.create_implementation_graph"
        ) as mock_create_graph:
            mock_create_graph.return_value = mocks.graph

            response = await test_client.post(
                "/api/workflows",
                json={
                    "issue_id": "TEST-IMMEDIATE-001",
                    "worktree_path": valid_worktree,
                    "task_title": "Test task",
                    # No start param - defaults to True
                },
            )

        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.integration
class TestStartPendingWorkflow:
    """Tests for POST /api/workflows/{id}/start endpoint."""

    async def test_start_pending_workflow_returns_202(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        langgraph_mock_factory: Any,
    ) -> None:
        """Starting a pending workflow returns 202 Accepted."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            resolved_path = str(Path(tmp_dir).resolve())

            # Create pending workflow directly in DB
            workflow = await create_pending_workflow(
                test_repository,
                issue_id="TEST-START",
                worktree_path=resolved_path,
            )

            # Mock LangGraph to prevent actual graph execution
            mocks = langgraph_mock_factory(astream_items=[])
            with patch(
                "amelia.server.orchestrator.service.create_implementation_graph"
            ) as mock_create_graph:
                mock_create_graph.return_value = mocks.graph

                response = await test_client.post(f"/api/workflows/{workflow.id}/start")

            assert response.status_code == status.HTTP_202_ACCEPTED
            data = response.json()
            assert data["workflow_id"] == str(workflow.id)
            assert data["status"] == "started"

    async def test_start_nonexistent_workflow_returns_404(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Starting a non-existent workflow returns 404."""
        fake_id = uuid4()
        response = await test_client.post(f"/api/workflows/{fake_id}/start")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_start_already_running_workflow_returns_409(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Starting a workflow that's not pending returns 409."""
        # Create workflow in in_progress state
        workflow = ServerExecutionState(
            id=uuid4(),
            issue_id="TEST-RUNNING",
            worktree_path="/tmp/running",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await test_repository.create(workflow)

        response = await test_client.post(f"/api/workflows/{workflow.id}/start")

        # Workflow is in_progress (not pending), so start returns INVALID_STATE
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.integration
class TestBatchStartWorkflows:
    """Tests for POST /api/workflows/start-batch endpoint."""

    async def test_batch_start_all_pending_workflows(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        langgraph_mock_factory: Any,
    ) -> None:
        """Batch start with no filters starts all pending workflows."""
        # Create pending workflows in different temp directories to avoid conflicts
        with tempfile.TemporaryDirectory() as tmp_dir1, \
             tempfile.TemporaryDirectory() as tmp_dir2:
            path1 = str(Path(tmp_dir1).resolve())
            path2 = str(Path(tmp_dir2).resolve())

            wf1 = await create_pending_workflow(
                test_repository,
                issue_id="TEST-BATCH-1",
                worktree_path=path1,
            )
            wf2 = await create_pending_workflow(
                test_repository,
                issue_id="TEST-BATCH-2",
                worktree_path=path2,
            )

            # Mock LangGraph
            mocks = langgraph_mock_factory(astream_items=[])
            with patch(
                "amelia.server.orchestrator.service.create_implementation_graph"
            ) as mock_create_graph:
                mock_create_graph.return_value = mocks.graph

                response = await test_client.post(
                    "/api/workflows/start-batch",
                    json={},
                )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "started" in data
            assert "errors" in data
            # Both workflows should be started
            assert len(data["started"]) == 2
            assert str(wf1.id) in data["started"]
            assert str(wf2.id) in data["started"]
            assert data["errors"] == {}

    async def test_batch_start_specific_workflow_ids(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        langgraph_mock_factory: Any,
    ) -> None:
        """Batch start with workflow_ids only starts specified workflows."""
        with tempfile.TemporaryDirectory() as tmp_dir1, \
             tempfile.TemporaryDirectory() as tmp_dir2, \
             tempfile.TemporaryDirectory() as tmp_dir3:
            path1 = str(Path(tmp_dir1).resolve())
            path2 = str(Path(tmp_dir2).resolve())
            path3 = str(Path(tmp_dir3).resolve())

            wf1 = await create_pending_workflow(
                test_repository,
                issue_id="TEST-SEL-1",
                worktree_path=path1,
            )
            wf2 = await create_pending_workflow(
                test_repository,
                issue_id="TEST-SEL-2",
                worktree_path=path2,
            )
            wf3 = await create_pending_workflow(
                test_repository,
                issue_id="TEST-NOT-SEL",
                worktree_path=path3,
            )

            # Mock LangGraph
            mocks = langgraph_mock_factory(astream_items=[])
            with patch(
                "amelia.server.orchestrator.service.create_implementation_graph"
            ) as mock_create_graph:
                mock_create_graph.return_value = mocks.graph

                response = await test_client.post(
                    "/api/workflows/start-batch",
                    json={"workflow_ids": [str(wf1.id), str(wf2.id)]},
                )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            # Only selected workflows should be started
            assert set(data["started"]) == {str(wf1.id), str(wf2.id)}

            # Verify wf3 is still pending
            not_selected = await test_repository.get(wf3.id)
            assert not_selected is not None
            assert not_selected.workflow_status == "pending"

    async def test_batch_start_empty_result_when_no_pending(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Batch start returns empty result when no pending workflows."""
        response = await test_client.post(
            "/api/workflows/start-batch",
            json={},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["started"] == []
        assert data["errors"] == {}


@pytest.mark.integration
class TestQueueThenStartFlow:
    """Integration tests for complete queue-then-start workflow."""

    async def test_queue_then_start_workflow_flow(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        active_test_profile: Profile,
        valid_worktree: str,
        langgraph_mock_factory: Any,
    ) -> None:
        """Complete flow: create queued, verify pending, start, verify in_progress."""
        # Step 1: Create workflow without starting (queue it)
        create_response = await test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-FLOW-001",
                "worktree_path": valid_worktree,
                "start": False,
                "task_title": "Test task",
            },
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        workflow_id = create_response.json()["id"]

        # Step 2: Verify it's in pending state
        get_response = await test_client.get(f"/api/workflows/{workflow_id}")
        assert get_response.status_code == status.HTTP_200_OK
        assert get_response.json()["status"] == "pending"

        # Step 3: Start the workflow
        mocks = langgraph_mock_factory(astream_items=[])
        with patch(
            "amelia.server.orchestrator.service.create_implementation_graph"
        ) as mock_create_graph:
            mock_create_graph.return_value = mocks.graph

            start_response = await test_client.post(f"/api/workflows/{workflow_id}/start")

        assert start_response.status_code == status.HTTP_202_ACCEPTED

        # Step 4: Verify workflow was started (started_at should be set)
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.started_at is not None, "Workflow should have started_at set"

    async def test_queue_workflow_after_cancelled_succeeds(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        active_test_profile: Profile,
        valid_worktree: str,
    ) -> None:
        """A new workflow can be queued after the previous one is cancelled.

        The system enforces one active workflow per worktree, but completed/cancelled
        workflows don't block new ones.
        """
        # Create first pending workflow
        response1 = await test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-FIRST-001",
                "worktree_path": valid_worktree,
                "start": False,
                "task_title": "First task",
            },
        )
        assert response1.status_code == status.HTTP_201_CREATED
        workflow_id = response1.json()["id"]

        # Cancel the first workflow
        cancel_response = await test_client.post(f"/api/workflows/{workflow_id}/cancel")
        assert cancel_response.status_code == status.HTTP_200_OK

        # Now create a second pending workflow - should succeed since first is cancelled
        response2 = await test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-SECOND-001",
                "worktree_path": valid_worktree,
                "start": False,
                "task_title": "Second task",
            },
        )
        assert response2.status_code == status.HTTP_201_CREATED

        # Verify second workflow is pending
        workflow2 = await test_repository.get(response2.json()["id"])
        assert workflow2 is not None
        assert workflow2.workflow_status == "pending"


@pytest.mark.integration
class TestQueueMultiplePendingWorkflows:
    """Tests for queuing multiple pending workflows on same worktree.

    Per design doc: "Multiple `pending` workflows per worktree allowed"
    This is distinct from running workflows which are limited to one per worktree.
    """

    async def test_queue_two_workflows_same_worktree_succeeds(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        active_test_profile: Profile,
        valid_worktree: str,
    ) -> None:
        """Two pending workflows on same worktree should be allowed.

        The uniqueness constraint should only apply to in_progress/blocked,
        not to pending workflows.
        """
        # Create first pending workflow
        response1 = await test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-MULTI-001",
                "worktree_path": valid_worktree,
                "start": False,
                "task_title": "First task",
            },
        )
        assert response1.status_code == status.HTTP_201_CREATED
        workflow1_id = response1.json()["id"]

        # Verify first workflow is pending
        workflow1 = await test_repository.get(workflow1_id)
        assert workflow1 is not None
        assert workflow1.workflow_status == "pending"

        # Create second pending workflow on SAME worktree - should succeed
        response2 = await test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-MULTI-002",
                "worktree_path": valid_worktree,
                "start": False,
                "task_title": "Second task",
            },
        )
        # This should succeed - multiple pending allowed per design
        assert response2.status_code == status.HTTP_201_CREATED
        workflow2_id = response2.json()["id"]

        # Verify second workflow is also pending
        workflow2 = await test_repository.get(workflow2_id)
        assert workflow2 is not None
        assert workflow2.workflow_status == "pending"

        # Both workflows should exist and be distinct
        assert workflow1_id != workflow2_id

    async def test_cannot_have_two_running_workflows_same_worktree(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        active_test_profile: Profile,
        valid_worktree: str,
        langgraph_mock_factory: Any,
    ) -> None:
        """Starting second workflow on same worktree should fail with 409.

        While multiple pending are allowed, only one can be in_progress/blocked.
        """
        # Create two pending workflows
        response1 = await test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-CONFLICT-001",
                "worktree_path": valid_worktree,
                "start": False,
                "task_title": "First task",
            },
        )
        assert response1.status_code == status.HTTP_201_CREATED
        workflow1_id = response1.json()["id"]

        response2 = await test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-CONFLICT-002",
                "worktree_path": valid_worktree,
                "start": False,
                "task_title": "Second task",
            },
        )
        assert response2.status_code == status.HTTP_201_CREATED
        workflow2_id = response2.json()["id"]

        # Start first workflow
        mocks = langgraph_mock_factory(astream_items=[])
        with patch(
            "amelia.server.orchestrator.service.create_implementation_graph"
        ) as mock_create_graph:
            mock_create_graph.return_value = mocks.graph

            start1_response = await test_client.post(f"/api/workflows/{workflow1_id}/start")
            assert start1_response.status_code == status.HTTP_202_ACCEPTED

            # Try to start second workflow - should fail with 409
            start2_response = await test_client.post(f"/api/workflows/{workflow2_id}/start")
            assert start2_response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.integration
class TestQueuedWorkflowExecution:
    """Tests for starting and executing queued workflows.

    Queued workflows must have proper state populated to run successfully.
    """

    async def test_queued_workflow_has_issue_cache(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        active_test_profile: Profile,
        valid_worktree: str,
    ) -> None:
        """Queued workflow must have issue_cache populated.

        Without issue_cache, the workflow cannot reconstruct initial state on start.
        """
        # Queue a workflow
        response = await test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-EXEC-001",
                "worktree_path": valid_worktree,
                "start": False,
                "task_title": "Test task",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        workflow_id = response.json()["id"]

        # Verify issue_cache and profile_id are set
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.workflow_status == "pending"
        # Issue cache must be set for workflow to start later
        assert workflow.issue_cache is not None, (
            "Queued workflow must have issue_cache populated"
        )
        assert workflow.profile_id is not None

    async def test_start_queued_workflow_succeeds(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        active_test_profile: Profile,
        valid_worktree: str,
        langgraph_mock_factory: Any,
    ) -> None:
        """Starting a queued workflow should transition to in_progress.

        The workflow should have all necessary state to execute without errors.
        """
        # Queue a workflow
        response = await test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-START-001",
                "worktree_path": valid_worktree,
                "start": False,
                "task_title": "Test task",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        workflow_id = response.json()["id"]

        # Start the workflow
        mocks = langgraph_mock_factory(astream_items=[])
        with patch(
            "amelia.server.orchestrator.service.create_implementation_graph"
        ) as mock_create_graph:
            mock_create_graph.return_value = mocks.graph

            start_response = await test_client.post(f"/api/workflows/{workflow_id}/start")

        # Should succeed
        assert start_response.status_code == status.HTTP_202_ACCEPTED

        # Verify workflow was started (started_at should be set)
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.started_at is not None, "Workflow should have started_at set"


@pytest.mark.integration
class TestQueuedWorkflowStateTransition:
    """Tests for state transition when starting queued workflows.

    Regression test for bug #84: Starting a queued workflow caused
    InvalidStateTransitionError because the status was set to 'in_progress'
    twice - once in start_pending_workflow and again in _run_workflow.

    NOTE: The actual state transition logic is tested in unit tests
    (TestStartPendingWorkflow in test_queue_workflow.py). Integration tests
    can only verify API contract due to async task execution.
    """

    async def test_start_queued_workflow_accepted_and_started_at_set(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        active_test_profile: Profile,
        valid_worktree: str,
        langgraph_mock_factory: Any,
    ) -> None:
        """Starting a queued workflow should return 202 and set started_at.

        This tests the API contract. The actual state transition logic
        (preventing double in_progress transition) is tested in unit tests.
        """
        # Queue a workflow
        response = await test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-TRANSITION-001",
                "worktree_path": valid_worktree,
                "start": False,
                "task_title": "Test task",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        workflow_id = response.json()["id"]

        # Verify workflow is pending
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.workflow_status == "pending"

        # Start the workflow (mocks apply to HTTP request context only)
        mocks = langgraph_mock_factory(astream_items=[])
        with patch(
            "amelia.server.orchestrator.service.create_implementation_graph"
        ) as mock_create_graph:
            mock_create_graph.return_value = mocks.graph

            start_response = await test_client.post(f"/api/workflows/{workflow_id}/start")

        # Key assertion: HTTP request was accepted
        assert start_response.status_code == status.HTTP_202_ACCEPTED

        # Verify started_at was set (proves start_pending_workflow ran)
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.started_at is not None, (
            "Workflow should have started_at set after start request"
        )
