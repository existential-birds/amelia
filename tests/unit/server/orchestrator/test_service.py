# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for OrchestratorService."""

import asyncio
import contextlib
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.state import ExecutionState
from amelia.core.types import Settings
from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.exceptions import (
    ConcurrencyLimitError,
    InvalidStateError,
    InvalidWorktreeError,
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
    mock_settings: Settings,
) -> OrchestratorService:
    """Create orchestrator service."""
    return OrchestratorService(
        event_bus=mock_event_bus,
        repository=mock_repository,
        settings=mock_settings,
        max_concurrent=5,
    )


@pytest.fixture
def valid_worktree(tmp_path: Path) -> str:
    """Create a valid git worktree directory.

    Args:
        tmp_path: Pytest tmp_path fixture.

    Returns:
        Absolute path to the valid worktree.
    """
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").touch()  # Git worktrees have a .git file
    return str(worktree)


# =============================================================================
# Worktree Validation Tests
# =============================================================================


async def test_start_workflow_rejects_nonexistent_path(
    orchestrator: OrchestratorService,
) -> None:
    """Should raise InvalidWorktreeError when path doesn't exist."""
    with pytest.raises(InvalidWorktreeError) as exc_info:
        await orchestrator.start_workflow(
            issue_id="ISSUE-123",
            worktree_path="/nonexistent/path",
            worktree_name="test",
        )

    assert exc_info.value.worktree_path == "/nonexistent/path"
    assert "does not exist" in exc_info.value.reason


async def test_start_workflow_rejects_file_path(
    orchestrator: OrchestratorService,
    tmp_path: Path,
) -> None:
    """Should raise InvalidWorktreeError when path is a file, not directory."""
    file_path = tmp_path / "not-a-dir"
    file_path.touch()

    with pytest.raises(InvalidWorktreeError) as exc_info:
        await orchestrator.start_workflow(
            issue_id="ISSUE-123",
            worktree_path=str(file_path),
            worktree_name="test",
        )

    assert "not a directory" in exc_info.value.reason


async def test_start_workflow_rejects_non_git_directory(
    orchestrator: OrchestratorService,
    tmp_path: Path,
) -> None:
    """Should raise InvalidWorktreeError when directory lacks .git."""
    plain_dir = tmp_path / "plain-dir"
    plain_dir.mkdir()

    with pytest.raises(InvalidWorktreeError) as exc_info:
        await orchestrator.start_workflow(
            issue_id="ISSUE-123",
            worktree_path=str(plain_dir),
            worktree_name="test",
        )

    assert ".git missing" in exc_info.value.reason


async def test_start_workflow_success(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    valid_worktree: str,
) -> None:
    """Should start workflow and return workflow ID."""
    with patch.object(orchestrator, "_run_workflow", new=AsyncMock()):
        workflow_id = await orchestrator.start_workflow(
            issue_id="ISSUE-123",
            worktree_path=valid_worktree,
            worktree_name="feat-123",
        )

        assert workflow_id  # Should return a UUID
        assert valid_worktree in orchestrator._active_tasks
        mock_repository.create.assert_called_once()

        # Verify state creation
        call_args = mock_repository.create.call_args
        state = call_args[0][0]
        assert state.id == workflow_id
        assert state.issue_id == "ISSUE-123"
        assert state.worktree_path == valid_worktree
        assert state.worktree_name == "feat-123"
        assert state.workflow_status == "pending"
        # Verify execution_state is initialized with profile
        assert state.execution_state is not None
        assert state.execution_state.profile.name == "test"


async def test_start_workflow_conflict(
    orchestrator: OrchestratorService,
    valid_worktree: str,
) -> None:
    """Should raise WorkflowConflictError when worktree already active."""
    # Create a fake task to simulate active workflow
    orchestrator._active_tasks[valid_worktree] = (
        "existing-wf",
        asyncio.create_task(asyncio.sleep(1)),
    )

    with pytest.raises(WorkflowConflictError) as exc_info:
        await orchestrator.start_workflow(
            issue_id="ISSUE-123",
            worktree_path=valid_worktree,
            worktree_name="feat-123",
        )

    assert valid_worktree in str(exc_info.value)

    # Cleanup
    _, task = orchestrator._active_tasks[valid_worktree]
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_start_workflow_concurrency_limit(
    orchestrator: OrchestratorService,
    valid_worktree: str,
) -> None:
    """Should raise ConcurrencyLimitError when at max concurrent."""
    # Fill up to max concurrent (use fake paths for active_tasks - validation
    # happens before conflict check, so these don't need to be real paths)
    tasks = []
    for i in range(5):
        task = asyncio.create_task(asyncio.sleep(1))
        orchestrator._active_tasks[f"/fake/worktree{i}"] = (f"wf-{i}", task)
        tasks.append(task)

    # Now try to start a workflow with a valid worktree path
    with pytest.raises(ConcurrencyLimitError) as exc_info:
        await orchestrator.start_workflow(
            issue_id="ISSUE-123",
            worktree_path=valid_worktree,
            worktree_name="feat-new",
        )

    assert exc_info.value.max_concurrent == 5

    # Cleanup
    for task in tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


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


@pytest.mark.parametrize(
    "operation,method_name,args,expected_exception,mock_state",
    [
        # Cancel workflow - not found
        (
            "cancel",
            "cancel_workflow",
            ("nonexistent",),
            WorkflowNotFoundError,
            None,
        ),
        # Cancel workflow - invalid state
        (
            "cancel",
            "cancel_workflow",
            ("wf-1",),
            InvalidStateError,
            ServerExecutionState(
                id="wf-1",
                issue_id="ISSUE-123",
                worktree_path="/path/to/worktree",
                worktree_name="feat-123",
                workflow_status="completed",
                started_at=datetime.now(UTC),
            ),
        ),
        # Approve workflow - not found
        (
            "approve",
            "approve_workflow",
            ("wf-1",),
            WorkflowNotFoundError,
            None,
        ),
        # Approve workflow - invalid state
        (
            "approve",
            "approve_workflow",
            ("wf-1",),
            InvalidStateError,
            ServerExecutionState(
                id="wf-1",
                issue_id="ISSUE-123",
                worktree_path="/path/to/worktree",
                worktree_name="feat-123",
                workflow_status="in_progress",
                started_at=datetime.now(UTC),
            ),
        ),
        # Reject workflow - not found
        (
            "reject",
            "reject_workflow",
            ("wf-1", "Nope"),
            WorkflowNotFoundError,
            None,
        ),
        # Reject workflow - invalid state
        (
            "reject",
            "reject_workflow",
            ("wf-1", "Nope"),
            InvalidStateError,
            ServerExecutionState(
                id="wf-1",
                issue_id="ISSUE-123",
                worktree_path="/path/to/worktree",
                worktree_name="feat-123",
                workflow_status="in_progress",
                started_at=datetime.now(UTC),
            ),
        ),
    ],
    ids=[
        "cancel-not_found",
        "cancel-invalid_state",
        "approve-not_found",
        "approve-invalid_state",
        "reject-not_found",
        "reject-invalid_state",
    ],
)
async def test_workflow_operation_exceptions(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    operation: str,
    method_name: str,
    args: tuple[str, ...],
    expected_exception: type[Exception],
    mock_state: ServerExecutionState | None,
) -> None:
    """Test exception handling for workflow operations (cancel/approve/reject).

    Args:
        orchestrator: Service under test.
        mock_repository: Mock repository.
        operation: Operation name for test identification.
        method_name: Name of the method to call on orchestrator.
        args: Arguments to pass to the method.
        expected_exception: Expected exception type.
        mock_state: Mock workflow state to return from repository.
    """
    mock_repository.get.return_value = mock_state

    with pytest.raises(expected_exception):
        method = getattr(orchestrator, method_name)
        await method(*args)


def test_get_active_workflows(orchestrator: OrchestratorService) -> None:
    """Should return list of active worktree paths."""
    orchestrator._active_tasks["/path/1"] = ("wf-1", MagicMock())
    orchestrator._active_tasks["/path/2"] = ("wf-2", MagicMock())

    active = orchestrator.get_active_workflows()
    assert set(active) == {"/path/1", "/path/2"}


# =============================================================================
# Approval Flow Tests
# =============================================================================


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


@patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
@patch("amelia.server.orchestrator.service.create_orchestrator_graph")
async def test_approve_workflow_success(
    mock_create_graph,
    mock_saver_class,
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    mock_event_bus: EventBus,
    langgraph_mock_factory,
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

    # Setup LangGraph mocks using factory
    mocks = langgraph_mock_factory(
        aget_state_return=MagicMock(values={"human_approved": True}, next=[])
    )
    mock_create_graph.return_value = mocks.graph
    mock_saver_class.from_conn_string.return_value = mocks.saver_class.from_conn_string.return_value

    # Simulate workflow waiting for approval
    orchestrator._approval_events["wf-1"] = asyncio.Event()

    # New API returns None, raises on error
    await orchestrator.approve_workflow("wf-1")

    # Should remove the approval event after setting it
    assert "wf-1" not in orchestrator._approval_events

    # Should update status - now called twice: once for in_progress, once for completed
    assert mock_repository.set_status.call_count == 2
    # First call is in_progress, second is completed
    calls = mock_repository.set_status.call_args_list
    assert calls[0][0] == ("wf-1", "in_progress")
    assert calls[1][0] == ("wf-1", "completed")

    # Should emit APPROVAL_GRANTED
    approval_granted = [e for e in received_events if e.event_type == EventType.APPROVAL_GRANTED]
    assert len(approval_granted) == 1


@patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
@patch("amelia.server.orchestrator.service.create_orchestrator_graph")
async def test_reject_workflow_success(
    mock_create_graph,
    mock_saver_class,
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    mock_event_bus: EventBus,
    langgraph_mock_factory,
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

    # Setup LangGraph mocks using factory
    mocks = langgraph_mock_factory()
    mock_create_graph.return_value = mocks.graph
    mock_saver_class.from_conn_string.return_value = mocks.saver_class.from_conn_string.return_value

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


class TestRejectWorkflowGraphState:
    """Test reject_workflow updates LangGraph state."""

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_orchestrator_graph")
    async def test_reject_updates_graph_state(
        self, mock_create_graph, mock_saver_class, orchestrator, mock_repository, langgraph_mock_factory
    ):
        """reject_workflow updates graph state with human_approved=False."""
        workflow = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/tmp/test",
            worktree_name="test",
            workflow_status="blocked",
        )
        mock_repository.get.return_value = workflow

        # Setup LangGraph mocks using factory
        mocks = langgraph_mock_factory()
        mock_create_graph.return_value = mocks.graph
        mock_saver_class.from_conn_string.return_value = mocks.saver_class.from_conn_string.return_value

        await orchestrator.reject_workflow("wf-123", "Not ready")

        mocks.graph.aupdate_state.assert_called_once()
        call_args = mocks.graph.aupdate_state.call_args
        assert call_args[0][1] == {"human_approved": False}


class TestApproveWorkflowResume:
    """Test approve_workflow resumes LangGraph execution."""

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_orchestrator_graph")
    async def test_approve_updates_state_and_resumes(
        self, mock_create_graph, mock_saver_class, orchestrator, mock_repository, langgraph_mock_factory
    ):
        """approve_workflow updates graph state and resumes execution."""
        # Setup blocked workflow
        workflow = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/tmp/test",
            worktree_name="test",
            workflow_status="blocked",
        )
        mock_repository.get.return_value = workflow
        orchestrator._active_tasks["/tmp/test"] = ("wf-123", AsyncMock())

        # Setup LangGraph mocks using factory
        mocks = langgraph_mock_factory(
            aget_state_return=MagicMock(values={"human_approved": True}, next=[])
        )
        mock_create_graph.return_value = mocks.graph
        mock_saver_class.from_conn_string.return_value = mocks.saver_class.from_conn_string.return_value

        await orchestrator.approve_workflow("wf-123")

        # Verify state was updated with approval
        mocks.graph.aupdate_state.assert_called_once()
        call_args = mocks.graph.aupdate_state.call_args
        assert call_args[0][1] == {"human_approved": True}


# =============================================================================
# Event Emission Tests
# =============================================================================


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


class TestStartWorkflowWithRetry:
    """Test start_workflow uses retry wrapper."""

    async def test_start_workflow_calls_retry_wrapper(
        self, orchestrator: OrchestratorService, mock_repository: AsyncMock, valid_worktree: str
    ):
        """start_workflow creates task with _run_workflow_with_retry."""
        orchestrator._run_workflow_with_retry = AsyncMock()

        workflow_id = await orchestrator.start_workflow(
            issue_id="TEST-1",
            worktree_path=valid_worktree,
        )

        # Wait briefly for task to start
        await asyncio.sleep(0.01)

        # The task should call _run_workflow_with_retry
        assert workflow_id is not None
        orchestrator._run_workflow_with_retry.assert_called_once()


# =============================================================================
# Stage Handling Tests
# =============================================================================


async def test_handle_stream_chunk_updates_current_stage(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    mock_event_bus: EventBus,
):
    """_handle_stream_chunk should update current_stage when stage starts."""
    # Setup mock workflow state
    mock_state = ServerExecutionState(
        id="wf-1",
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
        worktree_name="feat-123",
        workflow_status="in_progress",
        started_at=datetime.now(UTC),
        current_stage=None,  # Initially null
    )
    mock_repository.get.return_value = mock_state

    # Process a stage node chunk
    chunk = {"architect_node": {"some": "output"}}
    await orchestrator._handle_stream_chunk("wf-1", chunk)

    # Should fetch state, update current_stage, and persist
    mock_repository.get.assert_called_with("wf-1")
    mock_repository.update.assert_called_once()

    # Verify the state was updated with correct stage
    updated_state = mock_repository.update.call_args[0][0]
    assert updated_state.current_stage == "architect_node"


async def test_handle_stream_chunk_updates_stage_for_each_stage_node(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """_handle_stream_chunk should update current_stage for all STAGE_NODES."""
    from amelia.server.orchestrator.service import STAGE_NODES

    for stage_node in STAGE_NODES:
        # Reset mocks for each iteration
        mock_repository.reset_mock()

        mock_state = ServerExecutionState(
            id="wf-1",
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            worktree_name="feat-123",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        mock_repository.get.return_value = mock_state

        chunk = {stage_node: {"output": "data"}}
        await orchestrator._handle_stream_chunk("wf-1", chunk)

        # Should update state with this stage
        mock_repository.update.assert_called_once()
        updated_state = mock_repository.update.call_args[0][0]
        assert updated_state.current_stage == stage_node, f"Failed for {stage_node}"


async def test_handle_stream_chunk_ignores_non_stage_nodes(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """_handle_stream_chunk should not update current_stage for non-stage nodes."""
    # Process a non-stage node chunk
    chunk = {"some_other_node": {"output": "data"}}
    await orchestrator._handle_stream_chunk("wf-1", chunk)

    # Should not try to update state
    mock_repository.get.assert_not_called()
    mock_repository.update.assert_not_called()


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


# =============================================================================
# Policy Hook Tests
# =============================================================================


async def test_start_workflow_denied_by_policy_hook(
    orchestrator: OrchestratorService,
    valid_worktree: str,
) -> None:
    """Should raise PolicyDeniedError when policy hook denies workflow start."""
    from amelia.ext.exceptions import PolicyDeniedError
    from amelia.ext.registry import get_registry

    # Create a denying policy hook
    class DenyingPolicyHook:
        """Policy hook that denies all workflow starts."""

        async def on_workflow_start(
            self,
            workflow_id: str,
            profile: object,
            issue_id: str,
        ) -> bool:
            return False

        async def on_approval_request(
            self,
            workflow_id: str,
            approval_type: str,
        ) -> bool | None:
            return None

    registry = get_registry()
    denying_hook = DenyingPolicyHook()
    registry.register_policy_hook(denying_hook)

    try:
        with pytest.raises(PolicyDeniedError) as exc_info:
            await orchestrator.start_workflow(
                issue_id="ISSUE-123",
                worktree_path=valid_worktree,
                worktree_name="feat-123",
            )

        assert "denied by policy" in exc_info.value.reason.lower()
        assert exc_info.value.hook_name == "DenyingPolicyHook"
    finally:
        # Cleanup: remove the hook to avoid affecting other tests
        registry.clear()


# =============================================================================
# Plan Sync Tests
# =============================================================================


class TestSyncPlanFromCheckpoint:
    """Tests for _sync_plan_from_checkpoint method."""

    async def test_sync_plan_updates_execution_state(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        mock_execution_plan_factory,
        mock_profile_factory,
    ):
        """_sync_plan_from_checkpoint should update execution_state with plan from checkpoint."""
        # Create execution plan
        execution_plan = mock_execution_plan_factory(goal="Test goal", num_batches=2)

        # Create mock workflow with execution_state (no plan yet)
        profile = mock_profile_factory()
        mock_state = ServerExecutionState(
            id="wf-sync",
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            worktree_name="feat-123",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
            execution_state=ExecutionState(profile=profile),
        )
        mock_repository.get.return_value = mock_state

        # Create mock graph with checkpoint containing execution_plan
        mock_graph = MagicMock()
        checkpoint_values = {"execution_plan": execution_plan.model_dump()}
        mock_graph.aget_state = AsyncMock(
            return_value=MagicMock(values=checkpoint_values)
        )

        config: RunnableConfig = {"configurable": {"thread_id": "wf-sync"}}

        # Call _sync_plan_from_checkpoint
        await orchestrator._sync_plan_from_checkpoint("wf-sync", mock_graph, config)

        # Verify repository.update was called
        mock_repository.update.assert_called_once()

        # Verify the updated state has the execution_plan
        updated_state = mock_repository.update.call_args[0][0]
        assert updated_state.execution_state.execution_plan is not None
        assert updated_state.execution_state.execution_plan.goal == "Test goal"

    async def test_sync_plan_no_checkpoint_state(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ):
        """_sync_plan_from_checkpoint should return early if no checkpoint state."""
        mock_graph = MagicMock()
        mock_graph.aget_state = AsyncMock(return_value=None)

        config: RunnableConfig = {"configurable": {"thread_id": "wf-no-state"}}

        # Should not raise, just return early
        await orchestrator._sync_plan_from_checkpoint("wf-no-state", mock_graph, config)

        # Repository should not be called
        mock_repository.get.assert_not_called()
        mock_repository.update.assert_not_called()

    async def test_sync_plan_no_execution_plan_in_checkpoint(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ):
        """_sync_plan_from_checkpoint should return early if no execution_plan in checkpoint."""
        mock_graph = MagicMock()
        mock_graph.aget_state = AsyncMock(
            return_value=MagicMock(values={"some_other_key": "value"})
        )

        config: RunnableConfig = {"configurable": {"thread_id": "wf-no-plan"}}

        # Should not raise, just return early
        await orchestrator._sync_plan_from_checkpoint("wf-no-plan", mock_graph, config)

        # Repository.get should not be called since we exit before that
        mock_repository.get.assert_not_called()

    async def test_sync_plan_workflow_not_found(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        mock_execution_plan_factory,
    ):
        """_sync_plan_from_checkpoint should return early if workflow not found."""
        execution_plan = mock_execution_plan_factory()
        mock_graph = MagicMock()
        mock_graph.aget_state = AsyncMock(
            return_value=MagicMock(values={"execution_plan": execution_plan.model_dump()})
        )

        mock_repository.get.return_value = None  # Workflow not found

        config: RunnableConfig = {"configurable": {"thread_id": "wf-missing"}}

        # Should not raise, just log warning and return
        await orchestrator._sync_plan_from_checkpoint("wf-missing", mock_graph, config)

        # Repository.update should not be called
        mock_repository.update.assert_not_called()
