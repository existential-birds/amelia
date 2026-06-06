"""Unit tests for OrchestratorService."""

import asyncio
import contextlib
import uuid
from collections.abc import Callable, Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from amelia.core.types import AgentConfig, DriverType, Profile, TrackerType
from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)
from amelia.server.database.repository import WorkflowRepository


# Rebuild models to resolve forward references before module-level ServerExecutionState usage
rebuild_implementation_state()

from amelia.core.exceptions import ModelProviderError  # noqa: E402
from amelia.core.types import RetryConfig  # noqa: E402
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
from amelia.server.models.state import WorkflowStatus  # noqa: E402
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
    repo.update_plan_cache = AsyncMock()
    repo.set_status = AsyncMock()
    repo.save_event = AsyncMock()
    repo.get_max_event_sequence = AsyncMock(return_value=0)
    repo.get = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_profile_repo() -> AsyncMock:
    """Create mock profile repository."""
    repo = AsyncMock()
    agent_config = AgentConfig(driver=DriverType.CLAUDE, model="sonnet")
    default_profile = Profile(
        name="test",
        tracker=TrackerType.NOOP,
        repo_root="/default/repo",
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
) -> tuple[list[tuple[uuid.UUID, EventType, str, dict[str, object]]], Callable[[], None]]:
    """Capture events emitted by the orchestrator.

    Returns a tuple of (emitted_events list, install function).
    Call the install function to patch orchestrator._events.emit.

    Returns:
        Tuple of (emitted_events, install_fn) where:
        - emitted_events: List to collect (workflow_id, event_type, message, data) tuples
        - install_fn: Call this to install the capture function on the orchestrator
    """
    emitted_events: list[tuple[uuid.UUID, EventType, str, dict[str, object]]] = []

    async def _capture(
        workflow_id: uuid.UUID,
        event_type: EventType,
        message: str,
        agent: str = "system",
        data: dict[str, object] | None = None,
        correlation_id: uuid.UUID | None = None,
    ) -> WorkflowEvent:
        emitted_events.append((workflow_id, event_type, message, data or {}))
        return WorkflowEvent(
            id=uuid4(),
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
        setattr(orchestrator._events, "emit", _capture)  # noqa: B010

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
    with patch.object(orchestrator._runner, "run_workflow", new=AsyncMock()):
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
        assert state.workflow_status == WorkflowStatus.PENDING
        # Verify profile_id is stored on ServerExecutionState
        assert state.profile_id == "test"


async def test_start_workflow_conflict(
    orchestrator: OrchestratorService,
    valid_worktree: str,
) -> None:
    """Should raise WorkflowConflictError when worktree already active."""
    # Create a fake task to simulate active workflow
    orchestrator._active_tasks[valid_worktree] = (
        uuid4(),
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
        orchestrator._active_tasks[f"/fake/worktree{i}"] = (uuid4(), task)
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


async def test_assert_can_acquire_raises_on_active_worktree(
    orchestrator: OrchestratorService,
) -> None:
    """Guard raises WorkflowConflictError when worktree already active."""
    existing_id = uuid4()
    orchestrator._active_tasks["/wt"] = (existing_id, AsyncMock())
    with pytest.raises(WorkflowConflictError) as exc_info:
        orchestrator._assert_can_acquire_worktree("/wt")

    assert exc_info.value.worktree_path == "/wt"
    assert exc_info.value.workflow_id == existing_id


async def test_assert_can_acquire_raises_at_concurrency_limit(
    orchestrator: OrchestratorService,
) -> None:
    """Guard raises ConcurrencyLimitError when at max concurrent."""
    orchestrator._max_concurrent = 1
    orchestrator._active_tasks["/other"] = (uuid4(), AsyncMock())
    with pytest.raises(ConcurrencyLimitError) as exc_info:
        orchestrator._assert_can_acquire_worktree("/wt")

    assert exc_info.value.max_concurrent == 1
    assert exc_info.value.current_count == 1


async def test_cancel_workflow(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
) -> None:
    """Should cancel running workflow task and persist status."""
    # Create mock workflow state
    cancel_wf_id = uuid4()
    mock_state = ServerExecutionState(
        id=cancel_wf_id,
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
        workflow_status=WorkflowStatus.IN_PROGRESS,
        started_at=datetime.now(UTC),
    )
    mock_repository.get.return_value = mock_state

    # Create a fake running task
    task = asyncio.create_task(asyncio.sleep(100))
    orchestrator._active_tasks["/path/to/worktree"] = (cancel_wf_id, task)

    await orchestrator.cancel_workflow(cancel_wf_id)

    # Wait for the cancellation to complete
    with contextlib.suppress(asyncio.CancelledError):
        await task

    # Task should be cancelled
    assert task.cancelled()

    # Status should be persisted to database
    mock_repository.set_status.assert_called_once_with(cancel_wf_id, WorkflowStatus.CANCELLED)


@pytest.mark.parametrize(
    "operation,method_name,args,expected_exception,mock_state",
    [
        # Cancel workflow - not found
        (
            "cancel",
            "cancel_workflow",
            (uuid4(),),
            WorkflowNotFoundError,
            None,
        ),
        # Cancel workflow - invalid state
        (
            "cancel",
            "cancel_workflow",
            (uuid4(),),
            InvalidStateError,
            ServerExecutionState(
                id=uuid4(),
                issue_id="ISSUE-123",
                worktree_path="/path/to/worktree",
                    workflow_status=WorkflowStatus.COMPLETED,
                started_at=datetime.now(UTC),
            ),
        ),
        # Approve workflow - not found
        (
            "approve",
            "approve_workflow",
            (uuid4(),),
            WorkflowNotFoundError,
            None,
        ),
        # Approve workflow - invalid state
        (
            "approve",
            "approve_workflow",
            (uuid4(),),
            InvalidStateError,
            ServerExecutionState(
                id=uuid4(),
                issue_id="ISSUE-123",
                worktree_path="/path/to/worktree",
                    workflow_status=WorkflowStatus.IN_PROGRESS,
                started_at=datetime.now(UTC),
            ),
        ),
        # Reject workflow - not found
        (
            "reject",
            "reject_workflow",
            (uuid4(), "Nope"),
            WorkflowNotFoundError,
            None,
        ),
        # Reject workflow - invalid state
        (
            "reject",
            "reject_workflow",
            (uuid4(), "Nope"),
            InvalidStateError,
            ServerExecutionState(
                id=uuid4(),
                issue_id="ISSUE-123",
                worktree_path="/path/to/worktree",
                    workflow_status=WorkflowStatus.IN_PROGRESS,
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
    args: tuple[uuid.UUID, ...] | tuple[uuid.UUID, str],
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
    orchestrator._active_tasks["/path/1"] = (uuid4(), MagicMock())
    orchestrator._active_tasks["/path/2"] = (uuid4(), MagicMock())

    active = orchestrator.get_active_workflows()
    assert set(active) == {"/path/1", "/path/2"}


# =============================================================================
# Approval Flow Tests
# =============================================================================


@patch("amelia.server.orchestrator.runner.create_implementation_graph")
async def test_approve_workflow_success(
    mock_create_graph: MagicMock,
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
        id=uuid4(),
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
        workflow_status=WorkflowStatus.BLOCKED,
        started_at=datetime.now(UTC),
        profile_id="test",
    )
    mock_repository.get.return_value = mock_state

    # Setup LangGraph mocks using factory
    mocks = langgraph_mock_factory(
        aget_state_return=MagicMock(values={"human_approved": True}, next=[])
    )
    mock_create_graph.return_value = mocks.graph

    # Profile is already mocked via mock_profile_repo fixture
    # New API returns None, raises on error
    await orchestrator.approve_workflow(mock_state.id)

    # Should update status - now called twice: once for in_progress, once for completed
    assert mock_repository.set_status.call_count == 2
    # First call is in_progress, second is completed
    calls = mock_repository.set_status.call_args_list
    assert calls[0][0] == (mock_state.id, WorkflowStatus.IN_PROGRESS)
    assert calls[1][0] == (mock_state.id, WorkflowStatus.COMPLETED)

    # Should emit APPROVAL_GRANTED
    approval_granted = [e for e in received_events if e.event_type == EventType.APPROVAL_GRANTED]
    assert len(approval_granted) == 1


@patch("amelia.server.orchestrator.runner.create_implementation_graph")
async def test_reject_workflow_success(
    mock_create_graph: MagicMock,
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
        id=uuid4(),
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
        workflow_status=WorkflowStatus.BLOCKED,
        started_at=datetime.now(UTC),
        profile_id="test",
    )
    mock_repository.get.return_value = mock_state

    # Setup LangGraph mocks using factory
    mocks = langgraph_mock_factory()
    mock_create_graph.return_value = mocks.graph

    # Profile is already mocked via mock_profile_repo fixture
    # Create fake task
    task = asyncio.create_task(asyncio.sleep(100))
    orchestrator._active_tasks["/path/to/worktree"] = (mock_state.id, task)

    # New API returns None, raises on error
    await orchestrator.reject_workflow(mock_state.id, feedback="Plan too complex")

    # Should update status to failed
    mock_repository.set_status.assert_called_once_with(
        mock_state.id, WorkflowStatus.FAILED, failure_reason="Plan too complex"
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

    @patch("amelia.server.orchestrator.runner.create_implementation_graph")
    async def test_reject_updates_graph_state(
        self,
        mock_create_graph: MagicMock,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        langgraph_mock_factory: Callable[..., MagicMock],
    ) -> None:
        """reject_workflow updates graph state with human_approved=False."""
        workflow = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-456",
            worktree_path="/tmp/test",
            workflow_status=WorkflowStatus.BLOCKED,
            profile_id="test",
        )
        mock_repository.get.return_value = workflow

        # Setup LangGraph mocks using factory
        mocks = langgraph_mock_factory()
        mock_create_graph.return_value = mocks.graph

        # Profile is already mocked via mock_profile_repo fixture
        await orchestrator.reject_workflow(workflow.id, "Not ready")

        mocks.graph.aupdate_state.assert_called_once()
        call_args = mocks.graph.aupdate_state.call_args
        assert call_args[0][1] == {"human_approved": False}


class TestApproveWorkflowResume:
    """Test approve_workflow resumes LangGraph execution."""

    @patch("amelia.server.orchestrator.runner.create_implementation_graph")
    async def test_approve_updates_state_and_resumes(
        self,
        mock_create_graph: MagicMock,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        langgraph_mock_factory: Callable[..., MagicMock],
    ) -> None:
        """approve_workflow updates graph state and resumes execution."""
        # Setup blocked workflow
        workflow = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-456",
            worktree_path="/tmp/test",
            workflow_status=WorkflowStatus.BLOCKED,
            profile_id="test",
        )
        mock_repository.get.return_value = workflow
        orchestrator._active_tasks["/tmp/test"] = (workflow.id, AsyncMock())

        # Setup LangGraph mocks using factory
        mocks = langgraph_mock_factory(
            aget_state_return=MagicMock(values={"human_approved": True}, next=[])
        )
        mock_create_graph.return_value = mocks.graph

        # Profile is already mocked via mock_profile_repo fixture
        await orchestrator.approve_workflow(workflow.id)

        # Verify state was updated with approval
        mocks.graph.aupdate_state.assert_called_once()
        call_args = mocks.graph.aupdate_state.call_args
        assert call_args[0][1] == {"human_approved": True}

    @patch("amelia.server.orchestrator.runner.create_implementation_graph")
    async def test_resume_retries_transient_via_with_retry(
        self,
        mock_create_graph: MagicMock,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        langgraph_mock_factory: Callable[..., MagicMock],
        async_iterator_mock_factory: Callable[[list[Any]], Any],
        capture_emit: tuple[
            list[tuple[uuid.UUID, EventType, str, dict[str, object]]],
            Callable[[], None],
        ],
    ) -> None:
        """Approval resume routes retry through with_retry (jittered).

        Drives the astream body to raise a transient error once, then
        succeed. Asserts with_retry sleeps exactly once and that the
        observable completion (WORKFLOW_COMPLETED event + COMPLETED status)
        happens after the retry — pinning the new retry behavior.
        """
        emitted_events, install = capture_emit
        install()

        workflow = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-789",
            worktree_path="/tmp/resume-retry",
            workflow_status=WorkflowStatus.BLOCKED,
            profile_id="test",
        )
        mock_repository.get.return_value = workflow
        orchestrator._active_tasks["/tmp/resume-retry"] = (workflow.id, AsyncMock())

        mocks = langgraph_mock_factory(
            aget_state_return=MagicMock(values={"human_approved": True}, next=[])
        )
        mock_create_graph.return_value = mocks.graph

        # First astream call raises a transient error; the second succeeds
        # (empty stream → workflow completes).
        astream_calls = 0

        def astream_side_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal astream_calls
            astream_calls += 1
            if astream_calls == 1:
                raise ModelProviderError("transient resume failure")
            return async_iterator_mock_factory([])

        mocks.graph.astream = MagicMock(side_effect=astream_side_effect)

        # Force a deterministic, non-zero jitter so the slept delay is
        # strictly greater than the un-jittered base_delay. The OLD hand-rolled
        # resume loop sleeps exactly base_delay (no jitter) and fails this; the
        # new with_retry path sleeps base_delay + jitter and passes.
        with (
            patch(
                "amelia.core.retry.random.uniform",
                return_value=0.2,  # 0 < 0.2 <= 0.25 * base_delay(1.0)
            ),
            patch(
                "amelia.core.retry.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep,
        ):
            await orchestrator.approve_workflow(workflow.id)

        # with_retry slept exactly once (one transient retry, jittered).
        assert mock_sleep.call_count == 1
        # Jittered delay: base_delay(1.0) + jitter(0.2) = 1.2 — strictly above
        # the un-jittered 1.0 the old loop produced.
        slept_delay = mock_sleep.call_args_list[0][0][0]
        assert slept_delay == pytest.approx(1.2)
        # Observable completion emitted after the retry.
        assert any(
            e[1] == EventType.WORKFLOW_COMPLETED for e in emitted_events
        )
        # And the repository recorded COMPLETED.
        completed_calls = [
            c
            for c in mock_repository.set_status.call_args_list
            if len(c[0]) >= 2 and c[0][1] == WorkflowStatus.COMPLETED
        ]
        assert len(completed_calls) == 1


class TestStartWorkflowWithRetry:
    """Test start_workflow uses retry wrapper."""

    async def test_start_workflow_calls_retry_wrapper(
        self, orchestrator: OrchestratorService, mock_repository: AsyncMock, valid_worktree: str
    ) -> None:
        """start_workflow creates task with _run_workflow_with_retry."""
        mock_retry = AsyncMock()
        with patch.object(orchestrator._runner, "run_workflow_with_retry", new=mock_retry):
            workflow_id = await orchestrator.start_workflow(
                issue_id="TEST-1",
                worktree_path=valid_worktree,
            )

            # Wait briefly for task to start
            await asyncio.sleep(0.01)

            # The task should call _run_workflow_with_retry
            assert workflow_id is not None
            mock_retry.assert_called_once()


async def test_get_workflow_by_worktree_uses_cache(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
) -> None:
    """get_workflow_by_worktree should use cached workflow_id, not DB."""
    # Create workflow state
    cached_wf_id = uuid4()
    mock_state = ServerExecutionState(
        id=cached_wf_id,
        issue_id="ISSUE-123",
        worktree_path="/cached/worktree",
        workflow_status=WorkflowStatus.IN_PROGRESS,
        started_at=datetime.now(UTC),
    )
    mock_repository.get.return_value = mock_state

    # Simulate active workflow with cached ID
    task = asyncio.create_task(asyncio.sleep(100))
    orchestrator._active_tasks["/cached/worktree"] = (cached_wf_id, task)

    # Reset mock to track calls
    mock_repository.list_active.reset_mock()

    # Get workflow by worktree
    result = await orchestrator.get_workflow_by_worktree("/cached/worktree")

    # Should NOT call list_active (O(n) query)
    mock_repository.list_active.assert_not_called()

    # Should call get() with cached workflow_id
    mock_repository.get.assert_called_once_with(cached_wf_id)

    # Should return the workflow
    assert result is not None
    assert result.id == cached_wf_id

    # Cleanup
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


# =============================================================================
# Task Title/Description Tests
# =============================================================================


class TestTaskProgressEvents:
    """Tests for task progress event emission."""

    @pytest.mark.asyncio
    async def test_emits_task_started_when_developer_starts_in_task_mode(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        capture_emit: tuple[list[tuple[uuid.UUID, EventType, str, dict[str, object]]], Callable[[], None]],
    ) -> None:
        """Should emit TASK_STARTED when developer_node starts with total_tasks set."""
        emitted_events, install = capture_emit
        install()

        # Simulate developer_node task start event with Pydantic state
        # (LangGraph passes ImplementationState as input, not a dict)
        input_state = ImplementationState(
            workflow_id=uuid4(),
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
        await orchestrator._events.handle_tasks_event(uuid4(), task_data)

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
        capture_emit: tuple[list[tuple[uuid.UUID, EventType, str, dict[str, object]]], Callable[[], None]],
    ) -> None:
        """Should emit TASK_COMPLETED when next_task_node finishes."""
        emitted_events, install = capture_emit
        install()

        # Setup workflow in task-based mode (mock_repository.get not used by _handle_stream_chunk,
        # but kept for consistency in case the method changes)
        from amelia.server.models.state import PlanCache

        mock_state = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            workflow_status=WorkflowStatus.IN_PROGRESS,
            started_at=datetime.now(UTC),
            profile_id="test",
            plan_cache=PlanCache(total_tasks=5, current_task_index=0),
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

        await orchestrator._events.handle_stream_chunk(uuid4(), chunk)

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
        from amelia.core.types import Issue

        # Create valid worktree (just needs .git, no settings.amelia.yaml needed)
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / ".git").touch()

        # mock_profile_repo fixture already returns a profile with tracker="noop"
        with patch.object(orchestrator._runner, "run_workflow_with_retry", new=AsyncMock()):
            workflow_id = await orchestrator.start_workflow(
                issue_id="TASK-1",
                worktree_path=str(worktree),
                task_title="Add logout button",
                task_description="Add to navbar with confirmation",
            )

            assert workflow_id is not None

            # Verify the issue_cache contains our custom issue
            call_args = mock_repository.create.call_args
            state = call_args[0][0]
            assert state.issue_cache is not None
            issue = Issue.model_validate(state.issue_cache)
            assert issue.title == "Add logout button"
            assert issue.description == "Add to navbar with confirmation"

    async def test_task_title_with_non_noop_tracker_skips_fetch(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        mock_profile_repo: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """start_workflow with task_title and non-noop tracker uses provided title."""
        from amelia.core.types import Issue

        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / ".git").touch()

        agent_config = AgentConfig(driver=DriverType.CLAUDE, model="sonnet")
        mock_profile_repo.get_profile.return_value = Profile(
            name="github",
            tracker=TrackerType.GITHUB,
            repo_root="/default/repo",
            agents={
                "architect": agent_config,
                "developer": agent_config,
                "reviewer": agent_config,
            },
        )

        with (
            patch(
                "amelia.server.orchestrator.service.create_tracker"
            ) as mock_create_tracker,
            patch.object(orchestrator._runner, "run_workflow_with_retry", new=AsyncMock()),
        ):
            await orchestrator.start_workflow(
                issue_id="TASK-1",
                worktree_path=str(worktree),
                profile="github",
                task_title="Add logout button",
                task_description="Users need a logout option",
            )

        # Tracker should not be called when task_title is provided
        mock_create_tracker.assert_not_called()

        # Verify the issue was constructed from the provided fields
        call_args = mock_repository.create.call_args
        state = call_args[0][0]
        issue = Issue.model_validate(state.issue_cache)
        assert issue.title == "Add logout button"
        assert issue.description == "Users need a logout option"

    async def test_task_title_defaults_description_to_title(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        mock_profile_repo: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """task_description defaults to task_title when not provided."""
        from amelia.core.types import Issue

        # Create valid worktree
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / ".git").touch()

        # mock_profile_repo fixture already returns a profile with tracker="noop"
        with patch.object(orchestrator._runner, "run_workflow_with_retry", new=AsyncMock()):
            await orchestrator.start_workflow(
                issue_id="TASK-1",
                worktree_path=str(worktree),
                task_title="Fix typo in README",
                # No task_description provided
            )

            call_args = mock_repository.create.call_args
            state = call_args[0][0]
            # Description should default to title
            assert state.issue_cache is not None
            issue = Issue.model_validate(state.issue_cache)
            assert issue.description == "Fix typo in README"


# =============================================================================
# ModelProviderError Retry Tests
# =============================================================================


class ModelProviderErrorSetup:
    """Shared setup for ModelProviderError retry tests."""

    def __init__(self, mock_graph: MagicMock, mock_profile: Profile) -> None:
        self.mock_graph = mock_graph
        self.mock_profile = mock_profile


@pytest.fixture
def model_provider_error_setup(mock_repository: AsyncMock) -> ModelProviderErrorSetup:
    """Shared setup for ModelProviderError retry tests."""
    # Setup blocked workflow with real ServerExecutionState
    mock_workflow = ServerExecutionState(
        id=uuid4(),
        issue_id="ISSUE-TEST",
        worktree_path="/tmp",
        workflow_status=WorkflowStatus.BLOCKED,
        profile_id="prof-1",
        started_at=datetime.now(UTC),
    )
    mock_repository.get.return_value = mock_workflow

    # Profile with fast retry config
    agent_config = AgentConfig(driver=DriverType.CLAUDE, model="sonnet")
    mock_profile = Profile(
        name="test",
        tracker=TrackerType.NOOP,
        repo_root="/tmp",
        retry=RetryConfig(max_retries=2, base_delay=0.1, max_delay=1.0),
        agents={
            "architect": agent_config,
            "developer": agent_config,
            "reviewer": agent_config,
        },
    )

    # Mock graph whose astream always raises ModelProviderError
    mock_graph = MagicMock()
    mock_graph.aupdate_state = AsyncMock()
    mock_graph.aget_state = AsyncMock()
    mock_graph.astream = MagicMock(side_effect=ModelProviderError("provider blew up"))

    return ModelProviderErrorSetup(mock_graph, mock_profile)


@contextlib.contextmanager
def model_provider_error_patches(
    orchestrator: OrchestratorService, setup: ModelProviderErrorSetup
) -> Generator[AsyncMock, None, None]:
    """Context manager for common patches in ModelProviderError tests."""
    with (
        patch.object(
            orchestrator._runner, "get_profile_or_fail", return_value=setup.mock_profile
        ),
        patch.object(
            orchestrator._runner, "create_server_graph", return_value=setup.mock_graph
        ),
        patch.object(orchestrator._runner, "resolve_prompts", return_value={}),
        # with_retry sleeps in amelia.core.retry, not in service.
        patch(
            "amelia.core.retry.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep,
    ):
        yield mock_sleep


async def test_model_provider_error_retried(
    orchestrator: OrchestratorService,
    model_provider_error_setup: ModelProviderErrorSetup,
) -> None:
    """Verify that when graph.astream raises ModelProviderError, approve_workflow retries before failing."""
    setup = model_provider_error_setup

    with (
        model_provider_error_patches(orchestrator, setup) as mock_sleep,
        pytest.raises(ModelProviderError),
    ):
        await orchestrator.approve_workflow(uuid4())

    # max_retries=2 means attempts 0, 1, 2 → astream called 3 times
    assert setup.mock_graph.astream.call_count == 3
    # Verify asyncio.sleep was called 2 times (after attempt 0 and attempt 1)
    assert mock_sleep.call_count == 2


async def test_model_provider_error_friendly_failure_reason(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    model_provider_error_setup: ModelProviderErrorSetup,
) -> None:
    """Verify that after retries exhausted, the failure_reason in the DB contains the friendly message."""
    setup = model_provider_error_setup

    with (
        model_provider_error_patches(orchestrator, setup),
        pytest.raises(ModelProviderError),
    ):
        await orchestrator.approve_workflow(uuid4())

    # Verify set_status was called with FAILED and a friendly failure_reason
    failed_calls = [
        call
        for call in mock_repository.set_status.call_args_list
        if len(call[0]) >= 2 and call[0][1] == WorkflowStatus.FAILED
    ]
    assert len(failed_calls) == 1
    # set_status is called as positional + keyword: set_status(wf_id, status, failure_reason=...)
    failure_reason = failed_calls[0].kwargs.get("failure_reason", "")
    assert "Failed after" in failure_reason
    assert "attempts" in failure_reason


async def test_httpx_connect_error_retried(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
) -> None:
    """Verify that httpx.ConnectError triggers retry logic like ModelProviderError."""
    import httpx

    mock_workflow = ServerExecutionState(
        id=uuid4(),
        issue_id="ISSUE-TEST",
        worktree_path="/tmp",
        workflow_status=WorkflowStatus.BLOCKED,
        profile_id="prof-1",
        started_at=datetime.now(UTC),
    )
    mock_repository.get.return_value = mock_workflow

    agent_config = AgentConfig(driver=DriverType.CLAUDE, model="sonnet")
    mock_profile = Profile(
        name="test",
        tracker=TrackerType.NOOP,
        repo_root="/tmp",
        retry=RetryConfig(max_retries=2, base_delay=0.1, max_delay=1.0),
        agents={
            "architect": agent_config,
            "developer": agent_config,
            "reviewer": agent_config,
        },
    )

    mock_graph = MagicMock()
    mock_graph.aupdate_state = AsyncMock()
    mock_graph.aget_state = AsyncMock()
    mock_graph.astream = MagicMock(side_effect=httpx.ConnectError("Connection refused"))

    with (
        patch.object(orchestrator._runner, "get_profile_or_fail", return_value=mock_profile),
        patch.object(orchestrator._runner, "create_server_graph", return_value=mock_graph),
        patch.object(orchestrator._runner, "resolve_prompts", return_value={}),
        # with_retry sleeps in amelia.core.retry, not in service.
        patch(
            "amelia.core.retry.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep,
        pytest.raises(httpx.ConnectError),
    ):
        await orchestrator.approve_workflow(uuid4())

    # max_retries=2 means attempts 0, 1, 2 → astream called 3 times
    assert mock_graph.astream.call_count == 3
    assert mock_sleep.call_count == 2


# =============================================================================
# Resume Workflow Tests
# =============================================================================


async def test_resume_workflow_corrupted_checkpoint_raises_invalid_state(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
) -> None:
    """resume_workflow should raise InvalidStateError when graph.aget_state() throws a database error."""
    wf_id = uuid4()
    workflow = ServerExecutionState(
        id=wf_id,
        issue_id="ISSUE-123",
        created_at=datetime.now(UTC),
        profile_id="test",
        workflow_status=WorkflowStatus.FAILED,
        worktree_path="/tmp/test-worktree",
    )
    mock_repository.get.return_value = workflow

    # Mock graph whose aget_state raises a database error
    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(
        side_effect=Exception("invalid memory alloc request size 1227985520")
    )

    with (
        patch.object(orchestrator._runner, "create_server_graph", return_value=mock_graph),
        pytest.raises(InvalidStateError) as exc_info,
    ):
        await orchestrator.resume_workflow(wf_id)

    assert "corrupted" in str(exc_info.value).lower()

