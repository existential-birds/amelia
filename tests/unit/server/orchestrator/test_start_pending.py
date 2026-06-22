# tests/unit/server/orchestrator/test_start_pending.py
"""Tests for start_pending_workflow orchestrator method."""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from amelia.core.types import AgentConfig, DriverType, Issue, Profile, TrackerType
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
    repo.get_by_worktree = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def pending_workflow() -> ServerExecutionState:
    """Create a pending workflow state."""
    return ServerExecutionState(
        id=uuid4(),
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

        with patch.object(orchestrator._runner, "run_workflow_with_retry", new_callable=AsyncMock):
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
            id=uuid4(),
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
            id=uuid4(),
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

        with patch.object(orchestrator._runner, "run_workflow_with_retry", new_callable=AsyncMock
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

        with patch.object(orchestrator._runner, "run_workflow_with_retry", new_callable=AsyncMock
        ):
            # Should succeed - no active (in_progress/blocked) workflow on worktree
            await orchestrator.start_pending_workflow("wf-pending123")

        # Workflow should have started
        assert "/path/to/repo" in orchestrator._active_tasks


class _SlowBlockingTracker:
    """A tracker whose ``get_issue`` blocks the calling thread (issue #644).

    Mirrors the helper in ``test_tracker_offloading``: if the fetch runs on
    the event loop, a concurrent coroutine cannot advance and the call times
    out; if it runs in a worker thread, the loop keeps spinning and the
    concurrent coroutine releases it.
    """

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def get_issue(self, issue_id: str, *, cwd: str | None = None) -> Issue:
        self.started.set()
        if not self.release.wait(timeout=5.0):
            raise AssertionError(
                "get_issue was never released by a concurrent coroutine"
            )
        return Issue(id=issue_id, title="slow", description="slow", status="open")


@pytest.mark.asyncio
async def test_prepare_workflow_state_tracker_fetch_does_not_stall_concurrent_coroutine(
    orchestrator: OrchestratorService,
) -> None:
    """_prepare_workflow_state's tracker fetch must not freeze the loop (issue #644).

    When no ``task_title`` is supplied, ``_prepare_workflow_state`` fetches the
    issue from the tracker. That fetch must run off the loop so concurrent
    coroutines keep advancing. Mirrors ``test_tracker_offloading`` for the
    ``_prepare_workflow_state`` call site.
    """
    tracker = _SlowBlockingTracker()
    profile = Profile(
        name="test",
        tracker=TrackerType.NOOP,
        repo_root="/tmp/test-repo",
        agents={"architect": AgentConfig(driver=DriverType.CLAUDE, model="sonnet")},
    )

    progressed = False

    async def concurrent_work() -> None:
        nonlocal progressed
        while not tracker.started.is_set():
            await asyncio.sleep(0.005)
        progressed = True
        tracker.release.set()

    with (
        patch.object(
            orchestrator,
            "_resolve_profile",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch.object(
            orchestrator,
            "_setup_workflow_branch",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "amelia.trackers.factory.create_tracker",
            return_value=tracker,
        ),
        patch(
            "amelia.server.orchestrator.service.get_git_head",
            new_callable=AsyncMock,
            return_value="abc123",
        ),
    ):
        gathered = await asyncio.wait_for(
            asyncio.gather(
                orchestrator._prepare_workflow_state(
                    uuid4(), "/tmp/test-repo", "ISSUE-644"
                ),
                concurrent_work(),
            ),
            timeout=10.0,
        )

    assert progressed, "concurrent coroutine never advanced — fetch blocked the loop"
    _, _, execution_state, _ = gathered[0]
    assert execution_state.issue is not None
    assert execution_state.issue.id == "ISSUE-644"
