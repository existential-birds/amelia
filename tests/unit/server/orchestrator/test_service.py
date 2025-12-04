"""Unit tests for OrchestratorService."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.server.events.bus import EventBus
from amelia.server.database.repository import WorkflowRepository
from amelia.server.models import ServerExecutionState
from amelia.server.orchestrator.exceptions import (
    ConcurrencyLimitError,
    WorkflowConflictError,
)
from amelia.server.orchestrator.service import OrchestratorService


@pytest.fixture
def mock_event_bus() -> EventBus:
    """Create mock event bus."""
    return EventBus()


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Create mock repository."""
    repo = AsyncMock(spec=WorkflowRepository)
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.set_status = AsyncMock()
    repo.save_event = AsyncMock()
    repo.get_max_event_sequence = AsyncMock(return_value=0)
    repo.get = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def orchestrator(
    mock_event_bus: EventBus,
    mock_repository: AsyncMock,
) -> OrchestratorService:
    """Create orchestrator service."""
    return OrchestratorService(
        event_bus=mock_event_bus,
        repository=mock_repository,
        max_concurrent=5,
    )


def test_orchestrator_initialization(orchestrator: OrchestratorService) -> None:
    """OrchestratorService should initialize with empty state."""
    assert orchestrator._max_concurrent == 5
    assert len(orchestrator._active_tasks) == 0
    assert len(orchestrator._approval_events) == 0
    assert len(orchestrator._sequence_counters) == 0
    assert len(orchestrator._sequence_locks) == 0


def test_get_active_workflows_empty(orchestrator: OrchestratorService) -> None:
    """Should return empty list when no active workflows."""
    assert orchestrator.get_active_workflows() == []


@pytest.mark.asyncio
async def test_start_workflow_success(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
) -> None:
    """Should start workflow and return workflow ID."""
    with patch.object(orchestrator, "_run_workflow", new=AsyncMock()) as mock_run:
        workflow_id = await orchestrator.start_workflow(
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            worktree_name="feat-123",
        )

        assert workflow_id  # Should return a UUID
        assert "/path/to/worktree" in orchestrator._active_tasks
        mock_repository.create.assert_called_once()

        # Verify state creation
        call_args = mock_repository.create.call_args
        state = call_args[0][0]
        assert state.id == workflow_id
        assert state.issue_id == "ISSUE-123"
        assert state.worktree_path == "/path/to/worktree"
        assert state.worktree_name == "feat-123"
        assert state.workflow_status == "pending"


@pytest.mark.asyncio
async def test_start_workflow_conflict(
    orchestrator: OrchestratorService,
) -> None:
    """Should raise WorkflowConflictError when worktree already active."""
    # Create a fake task to simulate active workflow
    orchestrator._active_tasks["/path/to/worktree"] = asyncio.create_task(
        asyncio.sleep(1)
    )

    with pytest.raises(WorkflowConflictError) as exc_info:
        await orchestrator.start_workflow(
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            worktree_name="feat-123",
        )

    assert "/path/to/worktree" in str(exc_info.value)

    # Cleanup
    orchestrator._active_tasks["/path/to/worktree"].cancel()
    try:
        await orchestrator._active_tasks["/path/to/worktree"]
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_start_workflow_concurrency_limit(
    orchestrator: OrchestratorService,
) -> None:
    """Should raise ConcurrencyLimitError when at max concurrent."""
    # Fill up to max concurrent
    tasks = []
    for i in range(5):
        task = asyncio.create_task(asyncio.sleep(1))
        orchestrator._active_tasks[f"/path/to/worktree{i}"] = task
        tasks.append(task)

    with pytest.raises(ConcurrencyLimitError) as exc_info:
        await orchestrator.start_workflow(
            issue_id="ISSUE-123",
            worktree_path="/path/to/new",
            worktree_name="feat-new",
        )

    assert exc_info.value.max_concurrent == 5

    # Cleanup
    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_cancel_workflow(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
) -> None:
    """Should cancel running workflow task."""
    # Create mock workflow state
    mock_state = ServerExecutionState(
        id="wf-1",
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
        worktree_name="feat-123",
        workflow_status="in_progress",
        started_at=datetime.now(UTC),
    )
    mock_repository.get.return_value = mock_state

    # Create a fake running task
    task = asyncio.create_task(asyncio.sleep(100))
    orchestrator._active_tasks["/path/to/worktree"] = task

    await orchestrator.cancel_workflow("wf-1")

    # Wait for the cancellation to complete
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Task should be cancelled
    assert task.cancelled()


@pytest.mark.asyncio
async def test_cancel_workflow_not_running(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
) -> None:
    """Cancel non-running workflow should be no-op."""
    mock_repository.get.return_value = None

    # Should not raise
    await orchestrator.cancel_workflow("nonexistent")


def test_get_active_workflows(orchestrator: OrchestratorService) -> None:
    """Should return list of active worktree paths."""
    orchestrator._active_tasks["/path/1"] = MagicMock()
    orchestrator._active_tasks["/path/2"] = MagicMock()

    active = orchestrator.get_active_workflows()
    assert set(active) == {"/path/1", "/path/2"}
