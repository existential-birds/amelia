"""Integration tests for queue workflow flow.

Tests the complete queue workflow lifecycle:
- Queue workflows without starting
- Start individual queued workflows
- Batch start multiple workflows

Uses real OrchestratorService with real WorkflowRepository (in-memory SQLite).
Only mocks at external boundaries (LangGraph checkpoint/resume).

Mock boundaries:
- AsyncSqliteSaver: Prevents actual graph execution
- create_implementation_graph: Returns mock graph

Real components:
- FastAPI route handlers
- OrchestratorService
- WorkflowRepository with in-memory SQLite
- Request/Response model validation
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
from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.service import OrchestratorService

# init_git_repo is imported from conftest.py via pytest fixture auto-discovery
from tests.conftest import init_git_repo


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


async def create_pending_workflow(
    repository: WorkflowRepository,
    workflow_id: str = "wf-001",
    issue_id: str = "TEST-001",
    worktree_path: str = "/tmp/test-repo",
    profile_id: str = "test",
) -> ServerExecutionState:
    """Create and persist a pending workflow for testing.

    Args:
        repository: Repository to persist to.
        workflow_id: Workflow ID.
        issue_id: Issue ID.
        worktree_path: Worktree path.
        profile_id: Profile ID for execution state.

    Returns:
        Created ServerExecutionState in pending status.
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
        workflow_status="pending",
        # Note: started_at is None for pending workflows (set when started)
        execution_state=execution_state,
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
        test_client: TestClient,
        test_repository: WorkflowRepository,
        tmp_path: Path,
    ) -> None:
        """Creating workflow with start=False creates it in pending state."""
        # Initialize a git repo with settings
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        init_git_repo(git_dir)
        resolved_path = str(git_dir.resolve())

        # Create settings file in git repo
        settings_content = """
active_profile: test
profiles:
  test:
    name: test
    driver: "cli"
    model: sonnet
    validator_model: sonnet
    tracker: noop
    strategy: single
"""
        (git_dir / "settings.amelia.yaml").write_text(settings_content)

        response = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-QUEUE-001",
                "worktree_path": resolved_path,
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
        test_client: TestClient,
        test_repository: WorkflowRepository,
        mock_settings: MagicMock,
        langgraph_mock_factory: Any,
        tmp_path: Path,
    ) -> None:
        """Creating workflow without start param defaults to start=True."""
        # Initialize a git repo (required for worktree validation)
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        init_git_repo(git_dir)
        resolved_path = str(git_dir.resolve())

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

            response = test_client.post(
                "/api/workflows",
                json={
                    "issue_id": "TEST-IMMEDIATE-001",
                    "worktree_path": resolved_path,
                    # No start param - defaults to True
                },
            )

        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.integration
class TestStartPendingWorkflow:
    """Tests for POST /api/workflows/{id}/start endpoint."""

    async def test_start_pending_workflow_returns_202(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        mock_settings: MagicMock,
        langgraph_mock_factory: Any,
    ) -> None:
        """Starting a pending workflow returns 202 Accepted."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            resolved_path = str(Path(tmp_dir).resolve())

            # Create pending workflow
            await create_pending_workflow(
                test_repository,
                workflow_id="wf-pending-start",
                issue_id="TEST-START",
                worktree_path=resolved_path,
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

                response = test_client.post("/api/workflows/wf-pending-start/start")

            assert response.status_code == status.HTTP_202_ACCEPTED
            data = response.json()
            assert data["workflow_id"] == "wf-pending-start"
            assert data["status"] == "started"

    async def test_start_nonexistent_workflow_returns_404(
        self,
        test_client: TestClient,
    ) -> None:
        """Starting a non-existent workflow returns 404."""
        response = test_client.post("/api/workflows/wf-ghost/start")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_start_already_running_workflow_returns_409(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Starting a workflow that's not pending returns 409."""
        # Create workflow in in_progress state
        execution_state = ImplementationState(
            workflow_id="wf-running",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="pending",
        )
        workflow = ServerExecutionState(
            id="wf-running",
            issue_id="TEST-RUNNING",
            worktree_path="/tmp/running",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
            execution_state=execution_state,
        )
        await test_repository.create(workflow)

        response = test_client.post("/api/workflows/wf-running/start")

        assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.integration
class TestBatchStartWorkflows:
    """Tests for POST /api/workflows/start-batch endpoint."""

    async def test_batch_start_all_pending_workflows(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        mock_settings: MagicMock,
        langgraph_mock_factory: Any,
    ) -> None:
        """Batch start with no filters starts all pending workflows."""
        # Create pending workflows in different temp directories to avoid conflicts
        with tempfile.TemporaryDirectory() as tmp_dir1, \
             tempfile.TemporaryDirectory() as tmp_dir2:
            path1 = str(Path(tmp_dir1).resolve())
            path2 = str(Path(tmp_dir2).resolve())

            await create_pending_workflow(
                test_repository,
                workflow_id="wf-batch-1",
                issue_id="TEST-BATCH-1",
                worktree_path=path1,
            )
            await create_pending_workflow(
                test_repository,
                workflow_id="wf-batch-2",
                issue_id="TEST-BATCH-2",
                worktree_path=path2,
            )

            # Mock LangGraph
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

                response = test_client.post(
                    "/api/workflows/start-batch",
                    json={},
                )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "started" in data
            assert "errors" in data
            # Both workflows should be started
            assert len(data["started"]) == 2
            assert "wf-batch-1" in data["started"]
            assert "wf-batch-2" in data["started"]
            assert data["errors"] == {}

    async def test_batch_start_specific_workflow_ids(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        mock_settings: MagicMock,
        langgraph_mock_factory: Any,
    ) -> None:
        """Batch start with workflow_ids only starts specified workflows."""
        with tempfile.TemporaryDirectory() as tmp_dir1, \
             tempfile.TemporaryDirectory() as tmp_dir2, \
             tempfile.TemporaryDirectory() as tmp_dir3:
            path1 = str(Path(tmp_dir1).resolve())
            path2 = str(Path(tmp_dir2).resolve())
            path3 = str(Path(tmp_dir3).resolve())

            await create_pending_workflow(
                test_repository,
                workflow_id="wf-selected-1",
                issue_id="TEST-SEL-1",
                worktree_path=path1,
            )
            await create_pending_workflow(
                test_repository,
                workflow_id="wf-selected-2",
                issue_id="TEST-SEL-2",
                worktree_path=path2,
            )
            await create_pending_workflow(
                test_repository,
                workflow_id="wf-not-selected",
                issue_id="TEST-NOT-SEL",
                worktree_path=path3,
            )

            # Mock LangGraph
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

                response = test_client.post(
                    "/api/workflows/start-batch",
                    json={"workflow_ids": ["wf-selected-1", "wf-selected-2"]},
                )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            # Only selected workflows should be started
            assert set(data["started"]) == {"wf-selected-1", "wf-selected-2"}

            # Verify wf-not-selected is still pending
            not_selected = await test_repository.get("wf-not-selected")
            assert not_selected is not None
            assert not_selected.workflow_status == "pending"

    async def test_batch_start_empty_result_when_no_pending(
        self,
        test_client: TestClient,
    ) -> None:
        """Batch start returns empty result when no pending workflows."""
        response = test_client.post(
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
        test_client: TestClient,
        test_repository: WorkflowRepository,
        langgraph_mock_factory: Any,
        tmp_path: Path,
    ) -> None:
        """Complete flow: create queued, verify pending, start, verify in_progress."""
        # Initialize a git repo with settings
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        init_git_repo(git_dir)
        resolved_path = str(git_dir.resolve())

        # Create settings file in git repo
        settings_content = """
active_profile: test
profiles:
  test:
    name: test
    driver: "cli"
    model: sonnet
    validator_model: sonnet
    tracker: noop
    strategy: single
"""
        (git_dir / "settings.amelia.yaml").write_text(settings_content)

        # Step 1: Create workflow without starting (queue it)
        create_response = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-FLOW-001",
                "worktree_path": resolved_path,
                "start": False,
                "task_title": "Test task",
            },
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        workflow_id = create_response.json()["id"]

        # Step 2: Verify it's in pending state
        get_response = test_client.get(f"/api/workflows/{workflow_id}")
        assert get_response.status_code == status.HTTP_200_OK
        assert get_response.json()["status"] == "pending"

        # Step 3: Start the workflow
        mocks = langgraph_mock_factory(astream_items=[])
        with (
            patch(
                "amelia.server.orchestrator.service.AsyncSqliteSaver"
            ) as mock_saver_class,
            patch(
                "amelia.server.orchestrator.service.create_implementation_graph"
            ) as mock_create_graph,
        ):
            mock_create_graph.return_value = mocks.graph
            mock_saver_class.from_conn_string.return_value = (
                mocks.saver_class.from_conn_string.return_value
            )

            start_response = test_client.post(f"/api/workflows/{workflow_id}/start")

        assert start_response.status_code == status.HTTP_202_ACCEPTED

        # Step 4: Verify workflow was started (started_at should be set)
        # NOTE: We can't reliably verify final status because the spawned task
        # runs asynchronously outside the mock context. The unit test
        # TestStartPendingWorkflow verifies the actual state transition logic.
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.started_at is not None, "Workflow should have started_at set"

    async def test_queue_workflow_after_cancelled_succeeds(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        tmp_path: Path,
    ) -> None:
        """A new workflow can be queued after the previous one is cancelled.

        The system enforces one active workflow per worktree, but completed/cancelled
        workflows don't block new ones.
        """
        # Initialize a git repo with settings
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        init_git_repo(git_dir)
        resolved_path = str(git_dir.resolve())

        # Create settings file in git repo
        settings_content = """
active_profile: test
profiles:
  test:
    name: test
    driver: "cli"
    model: sonnet
    validator_model: sonnet
    tracker: noop
    strategy: single
"""
        (git_dir / "settings.amelia.yaml").write_text(settings_content)

        # Create first pending workflow
        response1 = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-FIRST-001",
                "worktree_path": resolved_path,
                "start": False,
                "task_title": "First task",
            },
        )
        assert response1.status_code == status.HTTP_201_CREATED
        workflow_id = response1.json()["id"]

        # Cancel the first workflow
        cancel_response = test_client.post(f"/api/workflows/{workflow_id}/cancel")
        assert cancel_response.status_code == status.HTTP_200_OK

        # Now create a second pending workflow - should succeed since first is cancelled
        response2 = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-SECOND-001",
                "worktree_path": resolved_path,
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
        test_client: TestClient,
        test_repository: WorkflowRepository,
        tmp_path: Path,
    ) -> None:
        """Two pending workflows on same worktree should be allowed.

        The uniqueness constraint should only apply to in_progress/blocked,
        not to pending workflows.
        """
        # Initialize a git repo with settings
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        init_git_repo(git_dir)
        resolved_path = str(git_dir.resolve())

        # Create settings file in git repo
        settings_content = """
active_profile: test
profiles:
  test:
    name: test
    driver: "cli"
    model: sonnet
    validator_model: sonnet
    tracker: noop
    strategy: single
"""
        (git_dir / "settings.amelia.yaml").write_text(settings_content)

        # Create first pending workflow
        response1 = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-MULTI-001",
                "worktree_path": resolved_path,
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
        response2 = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-MULTI-002",
                "worktree_path": resolved_path,
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
        test_client: TestClient,
        test_repository: WorkflowRepository,
        langgraph_mock_factory: Any,
        tmp_path: Path,
    ) -> None:
        """Starting second workflow on same worktree should fail with 409.

        While multiple pending are allowed, only one can be in_progress/blocked.
        """
        # Initialize a git repo with settings
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        init_git_repo(git_dir)
        resolved_path = str(git_dir.resolve())

        # Create settings file in git repo
        settings_content = """
active_profile: test
profiles:
  test:
    name: test
    driver: "cli"
    model: sonnet
    validator_model: sonnet
    tracker: noop
    strategy: single
"""
        (git_dir / "settings.amelia.yaml").write_text(settings_content)

        # Create two pending workflows
        response1 = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-CONFLICT-001",
                "worktree_path": resolved_path,
                "start": False,
                "task_title": "First task",
            },
        )
        assert response1.status_code == status.HTTP_201_CREATED
        workflow1_id = response1.json()["id"]

        response2 = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-CONFLICT-002",
                "worktree_path": resolved_path,
                "start": False,
                "task_title": "Second task",
            },
        )
        assert response2.status_code == status.HTTP_201_CREATED
        workflow2_id = response2.json()["id"]

        # Start first workflow
        mocks = langgraph_mock_factory(astream_items=[])
        with (
            patch(
                "amelia.server.orchestrator.service.AsyncSqliteSaver"
            ) as mock_saver_class,
            patch(
                "amelia.server.orchestrator.service.create_implementation_graph"
            ) as mock_create_graph,
        ):
            mock_create_graph.return_value = mocks.graph
            mock_saver_class.from_conn_string.return_value = (
                mocks.saver_class.from_conn_string.return_value
            )

            start1_response = test_client.post(f"/api/workflows/{workflow1_id}/start")
            assert start1_response.status_code == status.HTTP_202_ACCEPTED

            # Try to start second workflow - should fail with 409
            start2_response = test_client.post(f"/api/workflows/{workflow2_id}/start")
            assert start2_response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.integration
class TestQueuedWorkflowExecution:
    """Tests for starting and executing queued workflows.

    Queued workflows must have execution_state populated to run successfully.
    """

    async def test_queued_workflow_has_execution_state(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        tmp_path: Path,
    ) -> None:
        """Queued workflow must have execution_state populated.

        Without execution_state, the workflow will fail immediately on start
        with 'Missing execution state' error.
        """
        # Initialize a git repo with settings
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        init_git_repo(git_dir)
        resolved_path = str(git_dir.resolve())

        # Create settings file in git repo
        settings_content = """
active_profile: test
profiles:
  test:
    name: test
    driver: "cli"
    model: sonnet
    validator_model: sonnet
    tracker: noop
    strategy: single
"""
        (git_dir / "settings.amelia.yaml").write_text(settings_content)

        # Queue a workflow
        response = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-EXEC-001",
                "worktree_path": resolved_path,
                "start": False,
                "task_title": "Test task",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        workflow_id = response.json()["id"]

        # Verify execution_state exists
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.workflow_status == "pending"
        # This is the critical assertion - execution_state must be set
        assert workflow.execution_state is not None, (
            "Queued workflow must have execution_state populated"
        )
        assert workflow.execution_state.profile_id is not None

    async def test_start_queued_workflow_succeeds(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        langgraph_mock_factory: Any,
        tmp_path: Path,
    ) -> None:
        """Starting a queued workflow should transition to in_progress.

        The workflow should have all necessary state to execute without errors.
        """
        # Initialize a git repo with settings
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        init_git_repo(git_dir)
        resolved_path = str(git_dir.resolve())

        # Create settings file in git repo
        settings_content = """
active_profile: test
profiles:
  test:
    name: test
    driver: "cli"
    model: sonnet
    validator_model: sonnet
    tracker: noop
    strategy: single
"""
        (git_dir / "settings.amelia.yaml").write_text(settings_content)

        # Queue a workflow
        response = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-START-001",
                "worktree_path": resolved_path,
                "start": False,
                "task_title": "Test task",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        workflow_id = response.json()["id"]

        # Start the workflow
        mocks = langgraph_mock_factory(astream_items=[])
        with (
            patch(
                "amelia.server.orchestrator.service.AsyncSqliteSaver"
            ) as mock_saver_class,
            patch(
                "amelia.server.orchestrator.service.create_implementation_graph"
            ) as mock_create_graph,
        ):
            mock_create_graph.return_value = mocks.graph
            mock_saver_class.from_conn_string.return_value = (
                mocks.saver_class.from_conn_string.return_value
            )

            start_response = test_client.post(f"/api/workflows/{workflow_id}/start")

        # Should succeed, not fail with "Missing execution state"
        assert start_response.status_code == status.HTTP_202_ACCEPTED

        # Verify workflow was started (started_at should be set)
        # NOTE: We can't reliably verify final status because the spawned task
        # runs asynchronously outside the mock context.
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
        test_client: TestClient,
        test_repository: WorkflowRepository,
        langgraph_mock_factory: Any,
        tmp_path: Path,
    ) -> None:
        """Starting a queued workflow should return 202 and set started_at.

        This tests the API contract. The actual state transition logic
        (preventing double in_progress transition) is tested in unit tests.
        """
        # Initialize a git repo with settings
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        init_git_repo(git_dir)
        resolved_path = str(git_dir.resolve())

        # Create settings file in git repo
        settings_content = """
active_profile: test
profiles:
  test:
    name: test
    driver: "cli"
    model: sonnet
    validator_model: sonnet
    tracker: noop
    strategy: single
"""
        (git_dir / "settings.amelia.yaml").write_text(settings_content)

        # Queue a workflow
        response = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-TRANSITION-001",
                "worktree_path": resolved_path,
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
        with (
            patch(
                "amelia.server.orchestrator.service.AsyncSqliteSaver"
            ) as mock_saver_class,
            patch(
                "amelia.server.orchestrator.service.create_implementation_graph"
            ) as mock_create_graph,
        ):
            mock_create_graph.return_value = mocks.graph
            mock_saver_class.from_conn_string.return_value = (
                mocks.saver_class.from_conn_string.return_value
            )

            start_response = test_client.post(f"/api/workflows/{workflow_id}/start")

        # Key assertion: HTTP request was accepted
        assert start_response.status_code == status.HTTP_202_ACCEPTED

        # Verify started_at was set (proves start_pending_workflow ran)
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.started_at is not None, (
            "Workflow should have started_at set after start request"
        )
