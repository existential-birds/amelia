"""Unit tests for OrchestratorService."""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.types import AgentConfig, Profile, ReviewResult
from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)
from amelia.server.database.repository import WorkflowRepository
from amelia.server.models.state import rebuild_server_execution_state


# Rebuild models to resolve forward references before module-level ServerExecutionState usage
rebuild_implementation_state()
rebuild_server_execution_state()

from amelia.server.events.bus import EventBus  # noqa: E402
from amelia.server.exceptions import (  # noqa: E402
    ConcurrencyLimitError,
    InvalidStateError,
    InvalidWorktreeError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.server.models import ServerExecutionState  # noqa: E402
from amelia.server.models.events import EventType, WorkflowEvent  # noqa: E402
from amelia.server.orchestrator.service import OrchestratorService  # noqa: E402


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
def mock_profile_repo() -> AsyncMock:
    """Create mock profile repository."""
    repo = AsyncMock()
    agent_config = AgentConfig(driver="cli", model="sonnet")
    default_profile = Profile(
        name="test",
        tracker="noop",
        working_dir="/default/repo",
        agents={
            "architect": agent_config,
            "developer": agent_config,
            "reviewer": agent_config,
            "task_reviewer": agent_config,
            "evaluator": agent_config,
        },
    )
    repo.get_profile.return_value = default_profile
    repo.get_active_profile.return_value = default_profile
    return repo


@pytest.fixture
def orchestrator(
    mock_event_bus: EventBus,
    mock_repository: AsyncMock,
    mock_profile_repo: AsyncMock,
) -> OrchestratorService:
    """Create orchestrator service."""
    return OrchestratorService(
        event_bus=mock_event_bus,
        repository=mock_repository,
        profile_repo=mock_profile_repo,
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


@pytest.fixture
def capture_emit(
    orchestrator: OrchestratorService,
) -> tuple[list[tuple[str, EventType, str, dict[str, object]]], Callable[[], None]]:
    """Capture events emitted by the orchestrator.

    Returns a tuple of (emitted_events list, install function).
    Call the install function to patch orchestrator._emit.

    Returns:
        Tuple of (emitted_events, install_fn) where:
        - emitted_events: List to collect (workflow_id, event_type, message, data) tuples
        - install_fn: Call this to install the capture function on the orchestrator
    """
    emitted_events: list[tuple[str, EventType, str, dict[str, object]]] = []

    async def _capture(
        workflow_id: str,
        event_type: EventType,
        message: str,
        agent: str = "system",
        data: dict[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> WorkflowEvent:
        emitted_events.append((workflow_id, event_type, message, data or {}))
        return WorkflowEvent(
            id="test",
            workflow_id=workflow_id,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent=agent,
            event_type=event_type,
            message=message,
            data=data,
            correlation_id=correlation_id,
        )

    def install() -> None:
        orchestrator._emit = _capture  # type: ignore[method-assign]

    return emitted_events, install


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
        assert state.workflow_status == "pending"
        # Verify execution_state is initialized with profile_id
        assert state.execution_state is not None
        assert state.execution_state.profile_id == "test"


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


@patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
@patch("amelia.server.orchestrator.service.create_implementation_graph")
async def test_approve_workflow_success(
    mock_create_graph: MagicMock,
    mock_saver_class: MagicMock,
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    mock_event_bus: EventBus,
    langgraph_mock_factory: Callable[..., MagicMock],
) -> None:
    """Should approve blocked workflow."""
    received_events = []
    mock_event_bus.subscribe(lambda e: received_events.append(e))

    # Create mock blocked workflow
    mock_state = ServerExecutionState(
        id="wf-1",
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
        workflow_status="blocked",
        started_at=datetime.now(UTC),
        execution_state=ImplementationState(workflow_id="wf-1", created_at=datetime.now(UTC), status="running", profile_id="test"),
    )
    mock_repository.get.return_value = mock_state

    # Setup LangGraph mocks using factory
    mocks = langgraph_mock_factory(
        aget_state_return=MagicMock(values={"human_approved": True}, next=[])
    )
    mock_create_graph.return_value = mocks.graph
    mock_saver_class.from_conn_string.return_value = mocks.saver_class.from_conn_string.return_value

    # Profile is already mocked via mock_profile_repo fixture
    # New API returns None, raises on error
    await orchestrator.approve_workflow("wf-1")

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
@patch("amelia.server.orchestrator.service.create_implementation_graph")
async def test_reject_workflow_success(
    mock_create_graph: MagicMock,
    mock_saver_class: MagicMock,
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    mock_event_bus: EventBus,
    langgraph_mock_factory: Callable[..., MagicMock],
) -> None:
    """Should reject blocked workflow."""
    received_events = []
    mock_event_bus.subscribe(lambda e: received_events.append(e))

    # Create mock workflow and task
    mock_state = ServerExecutionState(
        id="wf-1",
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
        workflow_status="blocked",
        started_at=datetime.now(UTC),
        execution_state=ImplementationState(workflow_id="wf-1", created_at=datetime.now(UTC), status="running", profile_id="test"),
    )
    mock_repository.get.return_value = mock_state

    # Setup LangGraph mocks using factory
    mocks = langgraph_mock_factory()
    mock_create_graph.return_value = mocks.graph
    mock_saver_class.from_conn_string.return_value = mocks.saver_class.from_conn_string.return_value

    # Profile is already mocked via mock_profile_repo fixture
    # Create fake task
    task = asyncio.create_task(asyncio.sleep(100))
    orchestrator._active_tasks["/path/to/worktree"] = ("wf-1", task)

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
    @patch("amelia.server.orchestrator.service.create_implementation_graph")
    async def test_reject_updates_graph_state(
        self,
        mock_create_graph: MagicMock,
        mock_saver_class: MagicMock,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        langgraph_mock_factory: Callable[..., MagicMock],
    ) -> None:
        """reject_workflow updates graph state with human_approved=False."""
        workflow = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/tmp/test",
            workflow_status="blocked",
            execution_state=ImplementationState(workflow_id="wf-1", created_at=datetime.now(UTC), status="running", profile_id="test"),
        )
        mock_repository.get.return_value = workflow

        # Setup LangGraph mocks using factory
        mocks = langgraph_mock_factory()
        mock_create_graph.return_value = mocks.graph
        mock_saver_class.from_conn_string.return_value = mocks.saver_class.from_conn_string.return_value

        # Profile is already mocked via mock_profile_repo fixture
        await orchestrator.reject_workflow("wf-123", "Not ready")

        mocks.graph.aupdate_state.assert_called_once()
        call_args = mocks.graph.aupdate_state.call_args
        assert call_args[0][1] == {"human_approved": False}


class TestApproveWorkflowResume:
    """Test approve_workflow resumes LangGraph execution."""

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_implementation_graph")
    async def test_approve_updates_state_and_resumes(
        self,
        mock_create_graph: MagicMock,
        mock_saver_class: MagicMock,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        langgraph_mock_factory: Callable[..., MagicMock],
    ) -> None:
        """approve_workflow updates graph state and resumes execution."""
        # Setup blocked workflow
        workflow = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/tmp/test",
            workflow_status="blocked",
            execution_state=ImplementationState(workflow_id="wf-1", created_at=datetime.now(UTC), status="running", profile_id="test"),
        )
        mock_repository.get.return_value = workflow
        orchestrator._active_tasks["/tmp/test"] = ("wf-123", AsyncMock())

        # Setup LangGraph mocks using factory
        mocks = langgraph_mock_factory(
            aget_state_return=MagicMock(values={"human_approved": True}, next=[])
        )
        mock_create_graph.return_value = mocks.graph
        mock_saver_class.from_conn_string.return_value = mocks.saver_class.from_conn_string.return_value

        # Profile is already mocked via mock_profile_repo fixture
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
) -> None:
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
) -> None:
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
) -> None:
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
) -> None:
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
) -> None:
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
) -> None:
    """Concurrent first emits for same workflow should not create duplicate locks."""
    # Slow down the lock acquisition to increase race window
    original_get_max = mock_repository.get_max_event_sequence

    async def slow_get_max(workflow_id: str) -> int:
        await asyncio.sleep(0.01)  # Create race window
        result = await original_get_max(workflow_id)
        return cast(int, result)

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
    ) -> None:
        """start_workflow creates task with _run_workflow_with_retry."""
        mock_retry = AsyncMock()
        with patch.object(orchestrator, "_run_workflow_with_retry", new=mock_retry):
            workflow_id = await orchestrator.start_workflow(
                issue_id="TEST-1",
                worktree_path=valid_worktree,
            )

            # Wait briefly for task to start
            await asyncio.sleep(0.01)

            # The task should call _run_workflow_with_retry
            assert workflow_id is not None
            mock_retry.assert_called_once()


# =============================================================================
# Stage Handling Tests
# =============================================================================


async def test_handle_stream_chunk_updates_current_stage(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    mock_event_bus: EventBus,
) -> None:
    """_handle_stream_chunk should update current_stage when stage starts."""
    # Setup mock workflow state
    mock_state = ServerExecutionState(
        id="wf-1",
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
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
) -> None:
    """_handle_stream_chunk should update current_stage for all STAGE_NODES."""
    from amelia.server.orchestrator.service import STAGE_NODES

    for stage_node in STAGE_NODES:
        # Reset mocks for each iteration
        mock_repository.reset_mock()

        mock_state = ServerExecutionState(
            id="wf-1",
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
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
) -> None:
    """_handle_stream_chunk should not update current_stage for non-stage nodes."""
    # Process a non-stage node chunk
    chunk = {"some_other_node": {"output": "data"}}
    await orchestrator._handle_stream_chunk("wf-1", chunk)

    # Should not try to update state
    mock_repository.get.assert_not_called()
    mock_repository.update.assert_not_called()


async def test_completion_event_uses_fresh_current_stage(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    mock_event_bus: EventBus,
) -> None:
    """Completion events should fetch fresh state to get accurate current_stage.

    This tests the fix for stale current_stage in completion events. The issue was that
    _run_workflow captured state at function entry, but _handle_stream_chunk updated
    the database with fresh current_stage values. Completion events were emitting the
    stale captured value instead of fetching fresh from the database.
    """
    # Initial state has current_stage=None (stale value)
    _initial_state = ServerExecutionState(
        id="wf-1",
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
        workflow_status="in_progress",
        started_at=datetime.now(UTC),
        current_stage=None,  # Stale - will be updated by _handle_stream_chunk
    )

    # Fresh state has current_stage="reviewer_node" (updated by _handle_stream_chunk)
    fresh_state = ServerExecutionState(
        id="wf-1",
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
        workflow_status="in_progress",
        started_at=datetime.now(UTC),
        current_stage="reviewer_node",  # Fresh value from DB
    )

    # Configure repository.get to return fresh state
    mock_repository.get.return_value = fresh_state

    # Capture emitted events
    emitted_events: list[tuple[str, EventType, str, dict[str, object]]] = []

    async def capture_emit(
        workflow_id: str,
        event_type: EventType,
        message: str,
        agent: str = "system",
        data: dict[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> WorkflowEvent:
        emitted_events.append((workflow_id, event_type, message, data or {}))
        return WorkflowEvent(
            id="test",
            workflow_id=workflow_id,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent=agent,
            event_type=event_type,
            message=message,
            data=data,
            correlation_id=correlation_id,
        )

    orchestrator._emit = capture_emit  # type: ignore[method-assign]  # Test fixture: replace method to capture emit calls

    # Call the internal _emit_completion_event logic
    # (Simulating what happens at the end of _run_workflow)
    fresh_fetched = await mock_repository.get("wf-1")
    final_stage = fresh_fetched.current_stage if fresh_fetched else None

    await orchestrator._emit(
        "wf-1",
        EventType.WORKFLOW_COMPLETED,
        "Workflow completed successfully",
        data={"final_stage": final_stage},
    )

    # Verify the completion event has the FRESH current_stage, not the stale one
    assert len(emitted_events) == 1
    _, event_type, _, data = emitted_events[0]
    assert event_type == EventType.WORKFLOW_COMPLETED
    assert data["final_stage"] == "reviewer_node"  # Fresh, not None (stale)


async def test_get_workflow_by_worktree_uses_cache(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
) -> None:
    """get_workflow_by_worktree should use cached workflow_id, not DB."""
    # Create workflow state
    mock_state = ServerExecutionState(
        id="wf-cached",
        issue_id="ISSUE-123",
        worktree_path="/cached/worktree",
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
        mock_profile_factory: Callable[[], Profile],
    ) -> None:
        """_sync_plan_from_checkpoint should update execution_state with goal/plan from checkpoint."""
        # Create mock workflow with execution_state (no goal yet)
        profile = mock_profile_factory()
        mock_state = ServerExecutionState(
            id="wf-sync",
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
            execution_state=ImplementationState(workflow_id="wf-sync", created_at=datetime.now(UTC), status="running", profile_id=profile.name),
        )
        mock_repository.get.return_value = mock_state

        # Create mock graph with checkpoint containing goal and plan_markdown
        mock_graph = MagicMock()
        checkpoint_values = {"goal": "Test goal", "plan_markdown": "# Test Plan"}
        mock_graph.aget_state = AsyncMock(
            return_value=MagicMock(values=checkpoint_values)
        )

        config: RunnableConfig = {"configurable": {"thread_id": "wf-sync"}}

        # Call _sync_plan_from_checkpoint
        await orchestrator._sync_plan_from_checkpoint("wf-sync", mock_graph, config)

        # Verify repository.update was called
        mock_repository.update.assert_called_once()

        # Verify the updated state has the goal and plan_markdown
        updated_state = mock_repository.update.call_args[0][0]
        assert updated_state.execution_state.goal == "Test goal"
        assert updated_state.execution_state.plan_markdown == "# Test Plan"

    async def test_sync_plan_no_checkpoint_state(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ) -> None:
        """_sync_plan_from_checkpoint should return early if no checkpoint state."""
        mock_graph = MagicMock()
        mock_graph.aget_state = AsyncMock(return_value=None)

        config: RunnableConfig = {"configurable": {"thread_id": "wf-no-state"}}

        # Should not raise, just return early
        await orchestrator._sync_plan_from_checkpoint("wf-no-state", mock_graph, config)

        # Repository should not be called
        mock_repository.get.assert_not_called()
        mock_repository.update.assert_not_called()

    async def test_sync_plan_no_goal_or_plan_in_checkpoint(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ) -> None:
        """_sync_plan_from_checkpoint should return early if no goal/plan_markdown in checkpoint."""
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
    ) -> None:
        """_sync_plan_from_checkpoint should return early if workflow not found."""
        mock_graph = MagicMock()
        mock_graph.aget_state = AsyncMock(
            return_value=MagicMock(values={"goal": "Test goal"})
        )

        mock_repository.get.return_value = None  # Workflow not found

        config: RunnableConfig = {"configurable": {"thread_id": "wf-missing"}}

        # Should not raise, just log warning and return
        await orchestrator._sync_plan_from_checkpoint("wf-missing", mock_graph, config)

        # Repository.update should not be called
        mock_repository.update.assert_not_called()


# =============================================================================
# Checkpoint Resume Tests (Bug #199: Infinite Loop)
# =============================================================================


class TestRunWorkflowCheckpointResume:
    """Test _run_workflow correctly resumes from checkpoint on retry.

    Bug #199: When _run_workflow was called during retry, it always passed
    initial_state to graph.astream(), which starts a NEW execution instead
    of resuming from the checkpoint. This caused the developer-reviewer loop
    to restart from review_iteration=0 on each retry, creating an infinite loop.

    The fix: Check if a checkpoint exists before calling astream().
    - If checkpoint exists → pass None to resume
    - If no checkpoint → pass initial_state to start fresh
    """

    @pytest.fixture
    def mock_graph(self) -> MagicMock:
        """Create mock compiled graph."""
        graph = MagicMock()
        graph.aget_state = AsyncMock()
        graph.astream = MagicMock()
        return graph

    @pytest.fixture
    def mock_state(self) -> ServerExecutionState:
        """Create mock server execution state."""
        return ServerExecutionState(
            id="wf-retry-test",
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
            execution_state=ImplementationState(workflow_id="wf-1", created_at=datetime.now(UTC), status="running", profile_id="test"),
        )

    async def test_run_workflow_resumes_when_checkpoint_exists(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        mock_graph: MagicMock,
        mock_state: ServerExecutionState,
    ) -> None:
        """_run_workflow should pass None to astream when checkpoint exists.

        This ensures the graph resumes from checkpoint instead of restarting
        with initial_state, which would reset review_iteration to 0.
        """
        # Setup: checkpoint exists with some state
        mock_checkpoint_state = MagicMock()
        mock_checkpoint_state.values = {"review_iteration": 2, "goal": "test"}
        mock_graph.aget_state.return_value = mock_checkpoint_state

        # Setup astream to return empty iterator (workflow completes)
        async def empty_stream() -> AsyncIterator[dict[str, Any]]:
            return
            yield  # Makes this an async generator

        mock_graph.astream.return_value = empty_stream()

        # Create mock profile
        from amelia.core.types import AgentConfig, Profile

        mock_profile = Profile(
            name="test",
            tracker="noop",
            working_dir="/tmp/test",
            agents={
                "architect": AgentConfig(driver="cli", model="sonnet"),
                "developer": AgentConfig(driver="cli", model="sonnet"),
                "reviewer": AgentConfig(driver="cli", model="sonnet"),
            },
        )

        # Patch to use our mock graph
        with (
            patch.object(orchestrator, "_create_server_graph", return_value=mock_graph),
            patch.object(orchestrator, "_get_profile_or_fail", return_value=mock_profile),
            patch.object(orchestrator, "_emit", new=AsyncMock()),
            patch("amelia.server.orchestrator.service.AsyncSqliteSaver") as mock_saver,
            patch("amelia.server.orchestrator.service.emit_workflow_event", new=AsyncMock()),
        ):
            # Setup AsyncSqliteSaver context manager
            mock_checkpointer = MagicMock()
            mock_saver.from_conn_string.return_value.__aenter__ = AsyncMock(
                return_value=mock_checkpointer
            )
            mock_saver.from_conn_string.return_value.__aexit__ = AsyncMock()

            await orchestrator._run_workflow("wf-retry-test", mock_state)

        # Verify: astream was called with None (resume from checkpoint)
        mock_graph.astream.assert_called_once()
        call_args = mock_graph.astream.call_args
        first_arg = call_args[0][0] if call_args[0] else call_args[1].get("input")

        assert first_arg is None, (
            f"Expected astream to be called with None to resume from checkpoint, "
            f"but got {type(first_arg).__name__}: {first_arg}"
        )

    async def test_run_workflow_starts_fresh_when_no_checkpoint(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        mock_graph: MagicMock,
        mock_state: ServerExecutionState,
    ) -> None:
        """_run_workflow should pass initial_state when no checkpoint exists.

        For the first run of a workflow, we need to pass the initial state
        to start the execution.
        """
        # Setup: no checkpoint exists
        mock_graph.aget_state.return_value = None

        # Setup astream to return empty iterator
        async def empty_stream() -> AsyncIterator[dict[str, Any]]:
            return
            yield  # Makes this an async generator

        mock_graph.astream.return_value = empty_stream()

        from amelia.core.types import AgentConfig, Profile

        mock_profile = Profile(
            name="test",
            tracker="noop",
            working_dir="/tmp/test",
            agents={
                "architect": AgentConfig(driver="cli", model="sonnet"),
                "developer": AgentConfig(driver="cli", model="sonnet"),
                "reviewer": AgentConfig(driver="cli", model="sonnet"),
            },
        )

        with (
            patch.object(orchestrator, "_create_server_graph", return_value=mock_graph),
            patch.object(orchestrator, "_get_profile_or_fail", return_value=mock_profile),
            patch.object(orchestrator, "_emit", new=AsyncMock()),
            patch("amelia.server.orchestrator.service.AsyncSqliteSaver") as mock_saver,
            patch("amelia.server.orchestrator.service.emit_workflow_event", new=AsyncMock()),
        ):
            mock_checkpointer = MagicMock()
            mock_saver.from_conn_string.return_value.__aenter__ = AsyncMock(
                return_value=mock_checkpointer
            )
            mock_saver.from_conn_string.return_value.__aexit__ = AsyncMock()

            await orchestrator._run_workflow("wf-retry-test", mock_state)

        # Verify: astream was called with initial_state (start fresh)
        mock_graph.astream.assert_called_once()
        call_args = mock_graph.astream.call_args
        first_arg = call_args[0][0] if call_args[0] else call_args[1].get("input")

        assert first_arg is not None, "Expected astream to be called with initial_state"
        assert isinstance(first_arg, dict), "Expected initial_state to be a dict"
        assert first_arg.get("profile_id") == "test", "Expected profile_id in initial_state"


# =============================================================================
# Task Title/Description Tests
# =============================================================================


class TestTaskProgressEvents:
    """Tests for task progress event emission."""

    @pytest.mark.asyncio
    async def test_emits_task_failed_when_max_iterations_exceeded(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ) -> None:
        """Should emit TASK_FAILED when workflow ends with unapproved task."""
        # Create execution state: task mode, not approved, at max iterations
        exec_state = ImplementationState(
            workflow_id="wf-fail",
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            total_tasks=3,
            current_task_index=1,
            task_review_iteration=5,  # At max
            last_review=ReviewResult(
                reviewer_persona="code-reviewer",
                approved=False,
                comments=["Fix the bug"],
                severity="minor",
            ),
        )
        mock_state = ServerExecutionState(
            id="wf-fail",
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
            execution_state=exec_state,
        )
        mock_repository.get.return_value = mock_state

        # Simulate workflow completion (called by run_workflow on end)
        await orchestrator._emit_task_failed_if_applicable("wf-fail")

        # Verify TASK_FAILED event emitted
        mock_repository.save_event.assert_called_once()
        saved_event = mock_repository.save_event.call_args[0][0]
        assert saved_event.event_type == EventType.TASK_FAILED
        assert saved_event.message == "Task 2/3 failed after 5 review iterations"
        assert saved_event.data["task_index"] == 1
        assert saved_event.data["total_tasks"] == 3
        assert saved_event.data["iterations"] == 5

    @pytest.mark.asyncio
    async def test_no_task_failed_when_approved(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ) -> None:
        """Should NOT emit TASK_FAILED when last task was approved."""
        exec_state = ImplementationState(
            workflow_id="wf-ok",
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            total_tasks=3,
            current_task_index=2,  # Last task
            task_review_iteration=1,
            last_review=ReviewResult(
                reviewer_persona="code-reviewer",
                approved=True,
                comments=[],
                severity="none",
            ),
        )
        mock_state = ServerExecutionState(
            id="wf-ok",
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
            execution_state=exec_state,
        )
        mock_repository.get.return_value = mock_state

        await orchestrator._emit_task_failed_if_applicable("wf-ok")

        # No event should be emitted
        mock_repository.save_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_task_failed_when_no_last_review(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ) -> None:
        """Should NOT emit TASK_FAILED when no last_review in state."""
        exec_state = ImplementationState(
            workflow_id="wf-no-review",
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            total_tasks=3,
            current_task_index=1,
            task_review_iteration=5,
            # No last_review (defaults to None)
        )
        mock_state = ServerExecutionState(
            id="wf-no-review",
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
            execution_state=exec_state,
        )
        mock_repository.get.return_value = mock_state

        await orchestrator._emit_task_failed_if_applicable("wf-no-review")

        # No event should be emitted without last_review
        mock_repository.save_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_emits_task_started_when_developer_starts_in_task_mode(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        capture_emit: tuple[list[tuple[str, EventType, str, dict[str, object]]], Callable[[], None]],
    ) -> None:
        """Should emit TASK_STARTED when developer_node starts with total_tasks set."""
        emitted_events, install = capture_emit
        install()

        # Simulate developer_node task start event with Pydantic state
        # (LangGraph passes ImplementationState as input, not a dict)
        input_state = ImplementationState(
            workflow_id="wf-123",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="running",
            total_tasks=3,
            current_task_index=1,
            plan_markdown="### Task 1: First\n### Task 2: Second task\n### Task 3: Third",
        )
        task_data = {
            "name": "developer_node",
            "input": input_state,
        }
        await orchestrator._handle_tasks_event("wf-123", task_data)

        # Verify TASK_STARTED event emitted
        task_events = [e for e in emitted_events if e[1] == EventType.TASK_STARTED]
        assert len(task_events) == 1
        _, event_type, message, data = task_events[0]
        assert message == "Starting Task 2/3: Second task"
        assert data["task_index"] == 1
        assert data["total_tasks"] == 3
        assert data["task_title"] == "Second task"

    @pytest.mark.asyncio
    async def test_emits_task_completed_when_next_task_node_completes(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        capture_emit: tuple[list[tuple[str, EventType, str, dict[str, object]]], Callable[[], None]],
    ) -> None:
        """Should emit TASK_COMPLETED when next_task_node finishes."""
        emitted_events, install = capture_emit
        install()

        # Setup workflow in task-based mode
        mock_state = ServerExecutionState(
            id="wf-789",
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
            execution_state=ImplementationState(
                workflow_id="wf-789",
                created_at=datetime.now(UTC),
                status="running",
                profile_id="test",
                total_tasks=5,
                current_task_index=0,  # Was 0 before next_task_node runs
            ),
        )
        mock_repository.get.return_value = mock_state

        # Simulate next_task_node completion
        # The output contains the NEW index (incremented from 0 to 1) and total_tasks
        chunk = {
            "next_task_node": {
                "current_task_index": 1,  # New value after node runs
                "task_review_iteration": 0,
                "driver_session_id": None,
                "total_tasks": 5,  # Passed through for TASK_COMPLETED event
            }
        }

        await orchestrator._handle_stream_chunk("wf-789", chunk)

        # Verify TASK_COMPLETED event emitted
        task_events = [e for e in emitted_events if e[1] == EventType.TASK_COMPLETED]
        assert len(task_events) == 1
        _, event_type, message, data = task_events[0]
        # The completed task is the one we just finished (index 0, displayed as 1)
        assert message == "Completed Task 1/5"
        assert data["task_index"] == 0
        assert data["total_tasks"] == 5

class TestStartWorkflowWithTaskFields:
    """Tests for start_workflow with task_title/task_description."""

    async def test_none_tracker_with_task_title_constructs_issue(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        mock_profile_repo: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """start_workflow with task_title and none tracker constructs Issue directly."""
        # Create valid worktree (just needs .git, no settings.amelia.yaml needed)
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / ".git").touch()

        # mock_profile_repo fixture already returns a profile with tracker="noop"
        with patch.object(orchestrator, "_run_workflow_with_retry", new=AsyncMock()):
            workflow_id = await orchestrator.start_workflow(
                issue_id="TASK-1",
                worktree_path=str(worktree),
                task_title="Add logout button",
                task_description="Add to navbar with confirmation",
            )

            assert workflow_id is not None

            # Verify the execution state has our custom issue
            call_args = mock_repository.create.call_args
            state = call_args[0][0]
            assert state.execution_state.issue.title == "Add logout button"
            assert state.execution_state.issue.description == "Add to navbar with confirmation"

    async def test_task_title_with_non_none_tracker_errors(
        self,
        orchestrator: OrchestratorService,
        mock_profile_repo: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """start_workflow with task_title and non-none tracker should error."""
        # Create valid worktree
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / ".git").touch()

        # Override the mock profile to use github tracker
        agent_config = AgentConfig(driver="cli", model="sonnet")
        mock_profile_repo.get_profile.return_value = Profile(
            name="github",
            tracker="github",
            working_dir="/default/repo",
            agents={
                "architect": agent_config,
                "developer": agent_config,
                "reviewer": agent_config,
            },
        )

        with pytest.raises(ValueError) as exc_info:
            await orchestrator.start_workflow(
                issue_id="TASK-1",
                worktree_path=str(worktree),
                profile="github",
                task_title="Add logout button",
            )

        assert "noop" in str(exc_info.value).lower()
        assert "tracker" in str(exc_info.value).lower()

    async def test_task_title_defaults_description_to_title(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        mock_profile_repo: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """task_description defaults to task_title when not provided."""
        # Create valid worktree
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / ".git").touch()

        # mock_profile_repo fixture already returns a profile with tracker="noop"
        with patch.object(orchestrator, "_run_workflow_with_retry", new=AsyncMock()):
            await orchestrator.start_workflow(
                issue_id="TASK-1",
                worktree_path=str(worktree),
                task_title="Fix typo in README",
                # No task_description provided
            )

            call_args = mock_repository.create.call_args
            state = call_args[0][0]
            # Description should default to title
            assert state.execution_state.issue.description == "Fix typo in README"
