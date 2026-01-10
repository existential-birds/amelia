# tests/unit/server/orchestrator/test_start_pending.py
"""Tests for start_pending_workflow orchestrator method."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.server.exceptions import (
    ConcurrencyLimitError,
    InvalidStateError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.service import OrchestratorService


@pytest.fixture
def mock_event_bus() -> MagicMock:
    """Create a mock event bus."""
    bus = MagicMock()
    bus.emit = MagicMock()  # emit() is synchronous
    return bus


@pytest.fixture
def mock_repository() -> MagicMock:
    """Create a mock repository."""
    repo = MagicMock()
    repo.save = AsyncMock()
    repo.get = AsyncMock()
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.list_active = AsyncMock(return_value=[])
    repo.save_event = AsyncMock()
    repo.get_max_event_sequence = AsyncMock(return_value=0)
    repo.get_by_worktree = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def pending_workflow() -> ServerExecutionState:
    """Create a pending workflow state."""
    return ServerExecutionState(
        id="wf-pending123",
        issue_id="ISSUE-123",
        worktree_path="/path/to/repo",
        workflow_status="pending",
    )


@pytest.fixture
def orchestrator(mock_event_bus: MagicMock, mock_repository: MagicMock) -> OrchestratorService:
    """Create orchestrator with mocked dependencies."""
    return OrchestratorService(
        event_bus=mock_event_bus,
        repository=mock_repository,
        max_concurrent=5,
    )


class TestStartPendingWorkflow:
    """Tests for start_pending_workflow method."""

    @pytest.mark.asyncio
    async def test_start_pending_workflow_success(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        pending_workflow: ServerExecutionState,
    ) -> None:
        """Successfully start a pending workflow.

        Note: start_pending_workflow only sets started_at, not workflow_status.
        The status transition (pending -> in_progress) happens in _run_workflow
        to prevent double transition errors (bug #84).
        """
        mock_repository.get.return_value = pending_workflow

        with patch.object(orchestrator, "_run_workflow_with_retry", new_callable=AsyncMock):
            await orchestrator.start_pending_workflow("wf-pending123")

        # Workflow should have started_at set but status unchanged
        # (status transition happens in _run_workflow, not start_pending_workflow)
        update_call = mock_repository.update.call_args
        updated_state = update_call[0][0]
        assert updated_state.workflow_status == "pending"  # Not changed here
        assert updated_state.started_at is not None

    @pytest.mark.asyncio
    async def test_start_pending_not_found(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """Raise error when workflow not found."""
        mock_repository.get.return_value = None

        with pytest.raises(WorkflowNotFoundError):
            await orchestrator.start_pending_workflow("wf-nonexistent")

    @pytest.mark.asyncio
    async def test_start_pending_wrong_state(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """Raise error when workflow not in pending state."""
        in_progress = ServerExecutionState(
            id="wf-running",
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            workflow_status="in_progress",
        )
        mock_repository.get.return_value = in_progress

        with pytest.raises(InvalidStateError):
            await orchestrator.start_pending_workflow("wf-running")

    @pytest.mark.asyncio
    async def test_start_pending_worktree_conflict(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        pending_workflow: ServerExecutionState,
    ) -> None:
        """Raise error when worktree has active workflow."""
        mock_repository.get.return_value = pending_workflow

        # Another workflow is active on same worktree
        active_workflow = ServerExecutionState(
            id="wf-active",
            issue_id="ISSUE-999",
            worktree_path="/path/to/repo",
            workflow_status="in_progress",
        )
        mock_repository.get_by_worktree.return_value = active_workflow

        with pytest.raises(WorkflowConflictError):
            await orchestrator.start_pending_workflow("wf-pending123")

    @pytest.mark.asyncio
    async def test_start_pending_concurrency_limit(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        pending_workflow: ServerExecutionState,
    ) -> None:
        """Raise error when at max concurrent workflows."""
        mock_repository.get.return_value = pending_workflow

        # Simulate max concurrent workflows reached via _active_tasks
        orchestrator._active_tasks = {
            f"/worktree/{i}": (f"wf-{i}", MagicMock()) for i in range(5)
        }

        with pytest.raises(ConcurrencyLimitError):
            await orchestrator.start_pending_workflow("wf-pending123")

    @pytest.mark.asyncio
    async def test_start_pending_spawns_task(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        pending_workflow: ServerExecutionState,
    ) -> None:
        """Starting pending workflow spawns execution task."""
        mock_repository.get.return_value = pending_workflow

        with patch.object(
            orchestrator, "_run_workflow_with_retry", new_callable=AsyncMock
        ):
            await orchestrator.start_pending_workflow("wf-pending123")

        # Task should be tracked
        assert "/path/to/repo" in orchestrator._active_tasks

    @pytest.mark.asyncio
    async def test_start_pending_allows_another_pending_on_same_worktree(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        pending_workflow: ServerExecutionState,
    ) -> None:
        """Starting pending workflow succeeds when another pending workflow exists on same worktree.

        Multiple pending workflows on the same worktree are allowed by design.
        Only in_progress or blocked workflows should block starting a new one.
        """
        mock_repository.get.return_value = pending_workflow
        # get_by_worktree returns None because it excludes pending by default
        mock_repository.get_by_worktree.return_value = None

        with patch.object(
            orchestrator, "_run_workflow_with_retry", new_callable=AsyncMock
        ):
            # Should succeed - no active (in_progress/blocked) workflow on worktree
            await orchestrator.start_pending_workflow("wf-pending123")

        # Workflow should have started
        assert "/path/to/repo" in orchestrator._active_tasks
