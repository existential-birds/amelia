"""Unit tests for OrchestratorService."""

import asyncio
import contextlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.exceptions import (
    ConcurrencyLimitError,
    InvalidStateError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.server.models import ServerExecutionState
from amelia.server.models.events import EventType
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
    orchestrator._active_tasks["/path/to/worktree"] = (
        "existing-wf",
        asyncio.create_task(asyncio.sleep(1)),
    )

    with pytest.raises(WorkflowConflictError) as exc_info:
        await orchestrator.start_workflow(
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            worktree_name="feat-123",
        )

    assert "/path/to/worktree" in str(exc_info.value)

    # Cleanup
    _, task = orchestrator._active_tasks["/path/to/worktree"]
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_start_workflow_concurrency_limit(
    orchestrator: OrchestratorService,
) -> None:
    """Should raise ConcurrencyLimitError when at max concurrent."""
    # Fill up to max concurrent
    tasks = []
    for i in range(5):
        task = asyncio.create_task(asyncio.sleep(1))
        orchestrator._active_tasks[f"/path/to/worktree{i}"] = (f"wf-{i}", task)
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
    """Should cancel running workflow task and persist status."""
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
    orchestrator._active_tasks["/path/to/worktree"] = ("wf-1", task)

    await orchestrator.cancel_workflow("wf-1")

    # Wait for the cancellation to complete
    with contextlib.suppress(asyncio.CancelledError):
        await task

    # Task should be cancelled
    assert task.cancelled()

    # Status should be persisted to database
    mock_repository.set_status.assert_called_once_with("wf-1", "cancelled")


@pytest.mark.asyncio
async def test_cancel_workflow_not_found(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
) -> None:
    """Cancel nonexistent workflow should raise WorkflowNotFoundError."""
    mock_repository.get.return_value = None

    with pytest.raises(WorkflowNotFoundError):
        await orchestrator.cancel_workflow("nonexistent")


@pytest.mark.asyncio
async def test_cancel_workflow_invalid_state(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
) -> None:
    """Cancel completed workflow should raise InvalidStateError."""
    mock_state = ServerExecutionState(
        id="wf-1",
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
        worktree_name="feat-123",
        workflow_status="completed",
        started_at=datetime.now(UTC),
    )
    mock_repository.get.return_value = mock_state

    with pytest.raises(InvalidStateError):
        await orchestrator.cancel_workflow("wf-1")


def test_get_active_workflows(orchestrator: OrchestratorService) -> None:
    """Should return list of active worktree paths."""
    orchestrator._active_tasks["/path/1"] = ("wf-1", MagicMock())
    orchestrator._active_tasks["/path/2"] = ("wf-2", MagicMock())

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

    # Create mock blocked workflow
    mock_state = ServerExecutionState(
        id="wf-1",
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
        worktree_name="feat-123",
        workflow_status="blocked",
        started_at=datetime.now(UTC),
    )
    mock_repository.get.return_value = mock_state

    # Simulate workflow waiting for approval
    orchestrator._approval_events["wf-1"] = asyncio.Event()

    # New API returns None, raises on error
    await orchestrator.approve_workflow("wf-1")

    # Should remove the approval event after setting it
    assert "wf-1" not in orchestrator._approval_events

    # Should update status
    mock_repository.set_status.assert_called_once_with("wf-1", "in_progress")

    # Should emit APPROVAL_GRANTED
    approval_granted = [e for e in received_events if e.event_type == EventType.APPROVAL_GRANTED]
    assert len(approval_granted) == 1


@pytest.mark.asyncio
async def test_approve_workflow_not_found(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Approve non-existent workflow should raise WorkflowNotFoundError."""
    mock_repository.get.return_value = None

    with pytest.raises(WorkflowNotFoundError):
        await orchestrator.approve_workflow("wf-1")


@pytest.mark.asyncio
async def test_approve_workflow_not_blocked(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Approve non-blocked workflow should raise InvalidStateError."""
    mock_state = ServerExecutionState(
        id="wf-1",
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
        worktree_name="feat-123",
        workflow_status="in_progress",  # Not blocked
        started_at=datetime.now(UTC),
    )
    mock_repository.get.return_value = mock_state

    with pytest.raises(InvalidStateError):
        await orchestrator.approve_workflow("wf-1")


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
    orchestrator._active_tasks["/path/to/worktree"] = ("wf-1", task)
    orchestrator._approval_events["wf-1"] = asyncio.Event()

    # New API returns None, raises on error
    await orchestrator.reject_workflow("wf-1", feedback="Plan too complex")

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
async def test_reject_workflow_not_found(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Reject non-existent workflow should raise WorkflowNotFoundError."""
    mock_repository.get.return_value = None

    with pytest.raises(WorkflowNotFoundError):
        await orchestrator.reject_workflow("wf-1", feedback="Nope")


@pytest.mark.asyncio
async def test_reject_workflow_not_blocked(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Reject non-blocked workflow should raise InvalidStateError."""
    mock_state = ServerExecutionState(
        id="wf-1",
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
        worktree_name="feat-123",
        workflow_status="in_progress",  # Not blocked
        started_at=datetime.now(UTC),
    )
    mock_repository.get.return_value = mock_state

    with pytest.raises(InvalidStateError):
        await orchestrator.reject_workflow("wf-1", feedback="Nope")


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


@pytest.mark.asyncio
async def test_emit_concurrent_lock_creation_race(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Concurrent first emits for same workflow should not create duplicate locks."""
    # Slow down the lock acquisition to increase race window
    original_get_max = mock_repository.get_max_event_sequence

    async def slow_get_max(workflow_id: str) -> int:
        await asyncio.sleep(0.01)  # Create race window
        return await original_get_max(workflow_id)

    mock_repository.get_max_event_sequence = slow_get_max

    # Fire many concurrent emits for a NEW workflow (no lock exists yet)
    tasks = [
        orchestrator._emit("race-wf", EventType.FILE_CREATED, f"File {i}")
        for i in range(10)
    ]
    await asyncio.gather(*tasks)

    # All sequences must be unique (1-10)
    calls = mock_repository.save_event.call_args_list
    sequences = [call[0][0].sequence for call in calls]
    assert len(set(sequences)) == 10, f"Duplicate sequences found: {sequences}"
    assert set(sequences) == set(range(1, 11))


@pytest.mark.asyncio
async def test_get_workflow_by_worktree_uses_cache(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """get_workflow_by_worktree should use cached workflow_id, not DB."""
    # Create workflow state
    mock_state = ServerExecutionState(
        id="wf-cached",
        issue_id="ISSUE-123",
        worktree_path="/cached/worktree",
        worktree_name="cached",
        workflow_status="in_progress",
        started_at=datetime.now(UTC),
    )
    mock_repository.get.return_value = mock_state

    # Simulate active workflow with cached ID
    task = asyncio.create_task(asyncio.sleep(100))
    orchestrator._active_tasks["/cached/worktree"] = ("wf-cached", task)

    # Reset mock to track calls
    mock_repository.list_active.reset_mock()

    # Get workflow by worktree
    result = await orchestrator.get_workflow_by_worktree("/cached/worktree")

    # Should NOT call list_active (O(n) query)
    mock_repository.list_active.assert_not_called()

    # Should call get() with cached workflow_id
    mock_repository.get.assert_called_once_with("wf-cached")

    # Should return the workflow
    assert result is not None
    assert result.id == "wf-cached"

    # Cleanup
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
