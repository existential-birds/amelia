"""Tests for queue_workflow orchestrator method."""

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.service import OrchestratorService


def init_git_repo(path: Path) -> Path:
    """Initialize a git repo with initial commit for testing."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=path,
        capture_output=True,
        check=True,
    )
    (path / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"],
        cwd=path,
        capture_output=True,
        check=True,
    )
    return path


def create_settings_file(path: Path) -> None:
    """Create a settings.amelia.yaml file in the given path."""
    settings_content = """
active_profile: test
profiles:
  test:
    name: test
    driver: "cli:claude"
    model: sonnet
    tracker: noop
    strategy: single
"""
    (path / "settings.amelia.yaml").write_text(settings_content)


@pytest.fixture
def mock_event_bus() -> MagicMock:
    """Create a mock event bus."""
    bus = MagicMock()
    bus.emit = MagicMock()
    return bus


@pytest.fixture
def mock_repository() -> MagicMock:
    """Create a mock repository."""
    repo = MagicMock()
    repo.save = AsyncMock()
    repo.create = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    repo.list_active = AsyncMock(return_value=[])
    repo.save_event = AsyncMock()
    repo.get_max_event_sequence = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def orchestrator(mock_event_bus: MagicMock, mock_repository: MagicMock) -> OrchestratorService:
    """Create orchestrator with mocked dependencies."""
    return OrchestratorService(
        event_bus=mock_event_bus,
        repository=mock_repository,
        max_concurrent=5,
    )


class TestQueueWorkflow:
    """Tests for queue_workflow method."""

    @pytest.mark.asyncio
    async def test_queue_workflow_creates_pending_state(
        self, orchestrator: OrchestratorService, mock_repository: MagicMock, tmp_path: Path
    ) -> None:
        """queue_workflow creates workflow in pending state without starting."""
        # Set up git repo with settings
        git_dir = tmp_path / "repo"
        git_dir.mkdir()
        init_git_repo(git_dir)
        create_settings_file(git_dir)

        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path=str(git_dir),
            start=False,
            plan_now=False,
            task_title="Test task",
        )

        workflow_id = await orchestrator.queue_workflow(request)

        # Verify workflow_id is a valid UUID
        from uuid import UUID
        UUID(workflow_id)  # Raises ValueError if not valid UUID
        mock_repository.create.assert_called_once()
        saved_state: ServerExecutionState = mock_repository.create.call_args[0][0]
        assert saved_state.workflow_status == "pending"
        assert saved_state.started_at is None
        assert saved_state.planned_at is None
        # Verify execution_state is populated
        assert saved_state.execution_state is not None
        assert saved_state.execution_state.profile_id == "test"

    @pytest.mark.asyncio
    async def test_queue_workflow_does_not_spawn_task(
        self, orchestrator: OrchestratorService, tmp_path: Path
    ) -> None:
        """queue_workflow should not spawn an execution task."""
        # Set up git repo with settings
        git_dir = tmp_path / "repo"
        git_dir.mkdir()
        init_git_repo(git_dir)
        create_settings_file(git_dir)

        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path=str(git_dir),
            start=False,
            task_title="Test task",
        )

        await orchestrator.queue_workflow(request)

        # No active tasks should be spawned
        assert len(orchestrator._active_tasks) == 0

    @pytest.mark.asyncio
    async def test_queue_workflow_allows_multiple_pending_per_worktree(
        self, orchestrator: OrchestratorService, mock_repository: MagicMock, tmp_path: Path
    ) -> None:
        """Multiple pending workflows allowed on same worktree.

        Note: This is a unit test that verifies queue_workflow doesn't enforce
        uniqueness at the application level. The database constraint
        (idx_workflows_active_worktree) only restricts in_progress/blocked,
        allowing multiple pending workflows. That's tested in integration tests.
        """
        # Set up git repo with settings
        git_dir = tmp_path / "repo"
        git_dir.mkdir()
        init_git_repo(git_dir)
        create_settings_file(git_dir)

        # First workflow
        mock_repository.list_active.return_value = []
        request1 = CreateWorkflowRequest(
            issue_id="ISSUE-1",
            worktree_path=str(git_dir),
            start=False,
            task_title="Task 1",
        )
        await orchestrator.queue_workflow(request1)

        # Simulate first workflow exists as pending in DB
        mock_repository.list_active.return_value = [
            ServerExecutionState(
                id="wf-1",
                issue_id="ISSUE-1",
                worktree_path=str(git_dir),
                workflow_status="pending",
            )
        ]

        # Second workflow on same worktree should succeed
        request2 = CreateWorkflowRequest(
            issue_id="ISSUE-2",
            worktree_path=str(git_dir),
            start=False,
            task_title="Task 2",
        )
        workflow_id = await orchestrator.queue_workflow(request2)
        assert workflow_id is not None

    @pytest.mark.asyncio
    async def test_queue_workflow_emits_created_event(
        self, orchestrator: OrchestratorService, mock_event_bus: MagicMock, mock_repository: MagicMock, tmp_path: Path
    ) -> None:
        """queue_workflow should emit workflow_created event."""
        # Set up git repo with settings
        git_dir = tmp_path / "repo"
        git_dir.mkdir()
        init_git_repo(git_dir)
        create_settings_file(git_dir)

        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path=str(git_dir),
            start=False,
            task_title="Test task",
        )

        await orchestrator.queue_workflow(request)

        mock_event_bus.emit.assert_called()
        # Check event type in call args
        event = mock_event_bus.emit.call_args[0][0]
        assert event.event_type.value == "workflow_created"


class TestStartPendingWorkflow:
    """Tests for start_pending_workflow method.

    Regression tests for bug #84: Starting a queued workflow caused
    InvalidStateTransitionError because status was set to 'in_progress'
    twice - once in start_pending_workflow and again in _run_workflow.
    """

    @pytest.mark.asyncio
    async def test_start_pending_workflow_updates_started_at_not_status(
        self, orchestrator: OrchestratorService, mock_repository: MagicMock, tmp_path: Path
    ) -> None:
        """start_pending_workflow should update started_at but not status.

        The status transition (pending -> in_progress) happens in _run_workflow,
        not in start_pending_workflow. This ensures consistent behavior with
        start_workflow and prevents double transition errors.
        """
        from datetime import datetime
        from unittest.mock import patch

        from amelia.core.state import ExecutionState

        # Set up git repo with settings
        git_dir = tmp_path / "repo"
        git_dir.mkdir()
        init_git_repo(git_dir)
        create_settings_file(git_dir)

        # Create a pending workflow in the mock repository
        pending_workflow = ServerExecutionState(
            id="wf-pending-test",
            issue_id="ISSUE-123",
            worktree_path=str(git_dir),
            workflow_status="pending",
            execution_state=ExecutionState(profile_id="test"),
        )
        mock_repository.get = AsyncMock(return_value=pending_workflow)
        mock_repository.update = AsyncMock()
        mock_repository.get_by_worktree = AsyncMock(return_value=None)  # No active workflow
        mock_repository.find_by_status_and_worktree = AsyncMock(return_value=[])

        # Mock LangGraph to prevent actual execution
        mock_graph = MagicMock()
        mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={}, next=[]))
        mock_graph.astream = AsyncMock(return_value=iter([]))

        with (
            patch(
                "amelia.server.orchestrator.service.AsyncSqliteSaver"
            ),
            patch(
                "amelia.server.orchestrator.service.create_orchestrator_graph",
                return_value=mock_graph,
            ),
        ):
            await orchestrator.start_pending_workflow("wf-pending-test")

        # Verify update was called (to set started_at)
        mock_repository.update.assert_called_once()
        updated_workflow = mock_repository.update.call_args[0][0]

        # Key assertion: The workflow passed to update should NOT have
        # workflow_status changed. The status transition happens in _run_workflow.
        # If start_pending_workflow set status, this would be "in_progress"
        assert updated_workflow.workflow_status == "pending", (
            "start_pending_workflow should NOT set workflow_status. "
            "The status transition happens in _run_workflow to prevent "
            "double transition errors (bug #84)."
        )

        # Verify started_at WAS set
        assert updated_workflow.started_at is not None
        assert isinstance(updated_workflow.started_at, datetime)
