"""Unit tests for OrchestratorService."""

import asyncio
import contextlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.models import ServerExecutionState
from amelia.server.models.events import EventType
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
    with patch.object(orchestrator, "_run_workflow", new=AsyncMock()):
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
    with contextlib.suppress(asyncio.CancelledError):
        await orchestrator._active_tasks["/path/to/worktree"]


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
        with contextlib.suppress(asyncio.CancelledError):
            await task


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
    with contextlib.suppress(asyncio.CancelledError):
        await task

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


# =============================================================================
# Approval Flow Tests
# =============================================================================


@pytest.mark.asyncio
async def test_wait_for_approval(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    mock_event_bus: EventBus,
):
    """Should block until approval is granted."""
    received_events = []
    mock_event_bus.subscribe(lambda e: received_events.append(e))

    # Start waiting in background
    wait_task = asyncio.create_task(
        orchestrator._wait_for_approval("wf-1")
    )

    # Give it a moment to start waiting
    await asyncio.sleep(0.01)

    # Should be blocked
    assert not wait_task.done()

    # Should have created approval event
    assert "wf-1" in orchestrator._approval_events

    # Should have emitted APPROVAL_REQUIRED
    approval_required = [e for e in received_events if e.event_type == EventType.APPROVAL_REQUIRED]
    assert len(approval_required) == 1

    # Simulate approval
    orchestrator._approval_events["wf-1"].set()

    # Should complete
    await asyncio.wait_for(wait_task, timeout=1.0)
    assert wait_task.done()


@pytest.mark.asyncio
async def test_approve_workflow_success(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    mock_event_bus: EventBus,
):
    """Should approve blocked workflow."""
    received_events = []
    mock_event_bus.subscribe(lambda e: received_events.append(e))

    # Simulate workflow waiting for approval
    orchestrator._approval_events["wf-1"] = asyncio.Event()

    success = await orchestrator.approve_workflow("wf-1", correlation_id="corr-123")

    assert success is True

    # Should remove from approval events
    assert "wf-1" not in orchestrator._approval_events

    # Should update status
    mock_repository.set_status.assert_called_once_with("wf-1", "in_progress")

    # Should emit APPROVAL_GRANTED
    approval_granted = [e for e in received_events if e.event_type == EventType.APPROVAL_GRANTED]
    assert len(approval_granted) == 1
    assert approval_granted[0].correlation_id == "corr-123"


@pytest.mark.asyncio
async def test_approve_workflow_not_blocked(
    orchestrator: OrchestratorService,
):
    """Approve non-blocked workflow should return False."""
    success = await orchestrator.approve_workflow("wf-1")
    assert success is False


@pytest.mark.asyncio
async def test_approve_workflow_race_condition(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Concurrent approvals should be idempotent."""
    orchestrator._approval_events["wf-1"] = asyncio.Event()

    # Simulate concurrent approvals
    results = await asyncio.gather(
        orchestrator.approve_workflow("wf-1"),
        orchestrator.approve_workflow("wf-1"),
    )

    # Only one should succeed
    assert results.count(True) == 1
    assert results.count(False) == 1


@pytest.mark.asyncio
async def test_reject_workflow_success(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    mock_event_bus: EventBus,
):
    """Should reject blocked workflow."""
    received_events = []
    mock_event_bus.subscribe(lambda e: received_events.append(e))

    # Create mock workflow and task
    mock_state = ServerExecutionState(
        id="wf-1",
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
        worktree_name="feat-123",
        workflow_status="blocked",
        started_at=datetime.now(UTC),
    )
    mock_repository.get.return_value = mock_state

    # Create fake task
    task = asyncio.create_task(asyncio.sleep(100))
    orchestrator._active_tasks["/path/to/worktree"] = task
    orchestrator._approval_events["wf-1"] = asyncio.Event()

    success = await orchestrator.reject_workflow("wf-1", feedback="Plan too complex")

    assert success is True

    # Should update status to failed
    mock_repository.set_status.assert_called_once_with(
        "wf-1", "failed", failure_reason="Plan too complex"
    )

    # Should cancel task - wait for cancellation to complete
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert task.cancelled()

    # Should emit APPROVAL_REJECTED
    approval_rejected = [e for e in received_events if e.event_type == EventType.APPROVAL_REJECTED]
    assert len(approval_rejected) == 1
    assert "rejected" in approval_rejected[0].message.lower()


@pytest.mark.asyncio
async def test_reject_workflow_not_blocked(
    orchestrator: OrchestratorService,
):
    """Reject non-blocked workflow should return False."""
    success = await orchestrator.reject_workflow("wf-1", feedback="Nope")
    assert success is False


# =============================================================================
# Event Emission Tests
# =============================================================================


@pytest.mark.asyncio
async def test_emit_event(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    mock_event_bus: EventBus,
):
    """Should emit event with sequence number and persist to DB."""
    received = []
    mock_event_bus.subscribe(lambda e: received.append(e))

    await orchestrator._emit(
        workflow_id="wf-1",
        event_type=EventType.WORKFLOW_STARTED,
        message="Test message",
    )

    # Should persist to DB
    mock_repository.save_event.assert_called_once()
    saved_event = mock_repository.save_event.call_args[0][0]
    assert saved_event.workflow_id == "wf-1"
    assert saved_event.event_type == EventType.WORKFLOW_STARTED
    assert saved_event.message == "Test message"
    assert saved_event.sequence == 1
    assert saved_event.agent == "system"

    # Should broadcast to event bus
    assert len(received) == 1
    assert received[0] == saved_event


@pytest.mark.asyncio
async def test_emit_sequence_increment(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Sequence numbers should increment per workflow."""
    await orchestrator._emit("wf-1", EventType.WORKFLOW_STARTED, "Event 1")
    await orchestrator._emit("wf-1", EventType.STAGE_STARTED, "Event 2")
    await orchestrator._emit("wf-1", EventType.STAGE_COMPLETED, "Event 3")

    # Check sequences
    calls = mock_repository.save_event.call_args_list
    assert calls[0][0][0].sequence == 1
    assert calls[1][0][0].sequence == 2
    assert calls[2][0][0].sequence == 3


@pytest.mark.asyncio
async def test_emit_different_workflows(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Different workflows should have independent sequence counters."""
    await orchestrator._emit("wf-1", EventType.WORKFLOW_STARTED, "WF1 Event 1")
    await orchestrator._emit("wf-2", EventType.WORKFLOW_STARTED, "WF2 Event 1")
    await orchestrator._emit("wf-1", EventType.STAGE_STARTED, "WF1 Event 2")

    calls = mock_repository.save_event.call_args_list
    # wf-1 sequences: 1, 2
    assert calls[0][0][0].workflow_id == "wf-1"
    assert calls[0][0][0].sequence == 1
    assert calls[2][0][0].workflow_id == "wf-1"
    assert calls[2][0][0].sequence == 2
    # wf-2 sequences: 1
    assert calls[1][0][0].workflow_id == "wf-2"
    assert calls[1][0][0].sequence == 1


@pytest.mark.asyncio
async def test_emit_with_correlation_id(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Should propagate correlation_id to event."""
    await orchestrator._emit(
        workflow_id="wf-1",
        event_type=EventType.APPROVAL_GRANTED,
        message="Approved",
        correlation_id="corr-123",
    )

    saved_event = mock_repository.save_event.call_args[0][0]
    assert saved_event.correlation_id == "corr-123"


@pytest.mark.asyncio
async def test_emit_with_data(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Should include structured data in event."""
    data = {"stage": "architect", "tasks": 5}

    await orchestrator._emit(
        workflow_id="wf-1",
        event_type=EventType.STAGE_STARTED,
        message="Planning started",
        data=data,
    )

    saved_event = mock_repository.save_event.call_args[0][0]
    assert saved_event.data == data


@pytest.mark.asyncio
async def test_emit_concurrent_same_workflow(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Concurrent emits for same workflow should have unique sequences."""
    # Simulate concurrent emits
    await asyncio.gather(
        orchestrator._emit("wf-1", EventType.FILE_CREATED, "File 1"),
        orchestrator._emit("wf-1", EventType.FILE_CREATED, "File 2"),
        orchestrator._emit("wf-1", EventType.FILE_CREATED, "File 3"),
    )

    calls = mock_repository.save_event.call_args_list
    sequences = [call[0][0].sequence for call in calls]

    # All sequences should be unique
    assert len(set(sequences)) == 3
    assert set(sequences) == {1, 2, 3}


@pytest.mark.asyncio
async def test_emit_resumes_from_db_max_sequence(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """First emit should query DB for max sequence."""
    mock_repository.get_max_event_sequence.return_value = 42

    await orchestrator._emit("wf-1", EventType.WORKFLOW_STARTED, "Resume")

    # Should query DB once
    mock_repository.get_max_event_sequence.assert_called_once_with("wf-1")

    # Next sequence should be 43
    saved_event = mock_repository.save_event.call_args[0][0]
    assert saved_event.sequence == 43
