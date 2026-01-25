"""Tests for queue_and_plan_workflow orchestrator method."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import AgentConfig, Profile
from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.orchestrator.service import OrchestratorService


@pytest.fixture
def mock_event_bus() -> MagicMock:
    """Create a mock event bus."""
    bus = MagicMock()
    bus.emit = MagicMock()
    return bus


@pytest.fixture
def mock_repository() -> MagicMock:
    """Create a mock repository."""
    from amelia.server.models.state import ServerExecutionState

    repo = MagicMock()
    # Track the created workflow so get() can return it
    created_workflow: dict[str, ServerExecutionState] = {}

    async def mock_create(state: ServerExecutionState) -> None:
        created_workflow[state.id] = state

    async def mock_get(workflow_id: str) -> ServerExecutionState | None:
        return created_workflow.get(workflow_id)

    async def mock_update(state: ServerExecutionState) -> None:
        created_workflow[state.id] = state

    repo.create = AsyncMock(side_effect=mock_create)
    repo.get = AsyncMock(side_effect=mock_get)
    repo.update = AsyncMock(side_effect=mock_update)
    repo.save_event = AsyncMock()
    repo.get_max_event_sequence = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_profile_repo() -> AsyncMock:
    """Create mock profile repository."""
    repo = AsyncMock()
    agent_config = AgentConfig(driver="cli", model="sonnet")
    default_profile = Profile(
        name="test",
        tracker="none",
        working_dir="/default/repo",
        agents={
            "architect": agent_config,
            "developer": agent_config,
            "reviewer": agent_config,
        },
    )
    repo.get_profile.return_value = default_profile
    repo.get_active_profile.return_value = default_profile
    return repo


@pytest.fixture
def orchestrator(
    mock_event_bus: MagicMock,
    mock_repository: MagicMock,
    mock_profile_repo: AsyncMock,
) -> OrchestratorService:
    """Create orchestrator with mocked dependencies."""
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
    (worktree / ".git").touch()
    # No settings.amelia.yaml needed - profiles are now in database
    return str(worktree)


def create_mock_graph(
    *,
    interrupt_immediately: bool = True,
    fail_with: Exception | None = None,
    planning_started_event: asyncio.Event | None = None,
    planning_complete_event: asyncio.Event | None = None,
    goal: str = "Implement the test feature",
    plan_markdown: str = "# Plan\n\n1. Do thing",
) -> MagicMock:
    """Create a mock LangGraph that simulates planning behavior.

    Args:
        interrupt_immediately: If True, yields interrupt chunk immediately.
        fail_with: If set, raise this exception during astream.
        planning_started_event: Event to set when planning starts.
        planning_complete_event: Event to wait for before completing.
        goal: The goal to include in checkpoint state.
        plan_markdown: The plan markdown to include in checkpoint state.

    Returns:
        Mock graph with astream and aget_state configured.
    """
    mock_graph = MagicMock()

    async def mock_astream(
        input_state: dict[str, Any] | None,
        config: dict[str, Any],
        stream_mode: list[str],
    ) -> AsyncGenerator[tuple[str, Any], None]:
        """Mock astream that simulates LangGraph behavior."""
        if planning_started_event:
            planning_started_event.set()

        if planning_complete_event:
            await planning_complete_event.wait()

        if fail_with:
            raise fail_with

        # Yield architect_node update
        yield ("updates", {"architect_node": {"goal": goal, "plan_markdown": plan_markdown}})

        if interrupt_immediately:
            # Yield interrupt chunk to signal waiting at human_approval_node
            yield ("updates", {"__interrupt__": [{"value": "Plan ready", "resumable": True}]})

    mock_graph.astream = mock_astream

    # Mock aget_state to return checkpoint with plan
    mock_state = MagicMock()
    mock_state.values = {
        "goal": goal,
        "plan_markdown": plan_markdown,
    }
    mock_graph.aget_state = AsyncMock(return_value=mock_state)

    return mock_graph


@asynccontextmanager
async def mock_checkpointer_and_graph(
    mock_graph: MagicMock,
) -> AsyncGenerator[MagicMock, None]:
    """Context manager that patches AsyncSqliteSaver and graph creation."""
    # Create a mock checkpointer context manager
    mock_checkpointer = MagicMock()

    @asynccontextmanager
    async def mock_from_conn_string(path: str) -> AsyncGenerator[MagicMock, None]:
        yield mock_checkpointer

    with (
        patch(
            "amelia.server.orchestrator.service.AsyncSqliteSaver.from_conn_string",
            mock_from_conn_string,
        ),
        patch.object(
            OrchestratorService,
            "_create_server_graph",
            return_value=mock_graph,
        ),
    ):
        yield mock_checkpointer


class TestQueueAndPlanWorkflow:
    """Tests for queue_and_plan_workflow method."""

    @pytest.mark.asyncio
    async def test_queue_and_plan_runs_architect(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        valid_worktree: str,
    ) -> None:
        """queue_and_plan_workflow runs Architect via LangGraph and stores plan."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path=valid_worktree,
            start=False,
            plan_now=True,
        )

        mock_graph = create_mock_graph(
            goal="Implement the test feature",
            plan_markdown="# Plan\n\n1. Do thing\n2. Do other thing",
        )

        async with mock_checkpointer_and_graph(mock_graph):
            workflow_id = await orchestrator.queue_and_plan_workflow(request)

            # Wait for the background planning task to complete
            if workflow_id in orchestrator._planning_tasks:
                await orchestrator._planning_tasks[workflow_id]

        assert workflow_id is not None

        # Check state was saved with plan and planned_at
        # create() is called once for initial workflow creation
        # update() may be called multiple times (_sync_plan_from_checkpoint + status update)
        mock_repository.create.assert_called_once()
        assert mock_repository.update.call_count >= 1

        # Check the final updated state (last call to update)
        updated_state = mock_repository.update.call_args[0][0]
        assert updated_state.workflow_status == "blocked"
        assert updated_state.planned_at is not None
        # execution_state is synced from checkpoint via _sync_plan_from_checkpoint
        assert updated_state.execution_state is not None

    @pytest.mark.asyncio
    async def test_queue_and_plan_transitions_to_blocked(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        valid_worktree: str,
    ) -> None:
        """Workflow transitions to blocked after planning completes (waiting for approval)."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path=valid_worktree,
            start=False,
            plan_now=True,
        )

        mock_graph = create_mock_graph()

        async with mock_checkpointer_and_graph(mock_graph):
            workflow_id = await orchestrator.queue_and_plan_workflow(request)

            # Wait for the background planning task to complete
            if workflow_id in orchestrator._planning_tasks:
                await orchestrator._planning_tasks[workflow_id]

        # No active workflow task spawned (planning task is separate)
        assert len(orchestrator._active_tasks) == 0

    @pytest.mark.asyncio
    async def test_queue_and_plan_failure_marks_failed(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        valid_worktree: str,
    ) -> None:
        """If LangGraph fails during planning, workflow is marked failed."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path=valid_worktree,
            start=False,
            plan_now=True,
        )

        mock_graph = create_mock_graph(fail_with=Exception("LLM API error"))

        async with mock_checkpointer_and_graph(mock_graph):
            workflow_id = await orchestrator.queue_and_plan_workflow(request)

            # Wait for the background planning task to complete
            if workflow_id in orchestrator._planning_tasks:
                await orchestrator._planning_tasks[workflow_id]

        assert workflow_id is not None

        # Should be marked failed with reason
        update_call = mock_repository.update.call_args
        assert update_call is not None
        updated_state = update_call[0][0]
        assert updated_state.workflow_status == "failed"
        assert "LLM API error" in updated_state.failure_reason

    @pytest.mark.asyncio
    async def test_queue_and_plan_emits_events(
        self,
        orchestrator: OrchestratorService,
        mock_event_bus: MagicMock,
        mock_repository: MagicMock,
        valid_worktree: str,
    ) -> None:
        """queue_and_plan_workflow should emit workflow events."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path=valid_worktree,
            start=False,
            plan_now=True,
        )

        mock_graph = create_mock_graph()

        async with mock_checkpointer_and_graph(mock_graph):
            workflow_id = await orchestrator.queue_and_plan_workflow(request)

            # Wait for the background planning task to complete
            if workflow_id in orchestrator._planning_tasks:
                await orchestrator._planning_tasks[workflow_id]

        # Should have emitted events (workflow_created, stage events, approval_required)
        assert mock_event_bus.emit.called

    @pytest.mark.asyncio
    async def test_queue_and_plan_validates_worktree(
        self,
        orchestrator: OrchestratorService,
    ) -> None:
        """queue_and_plan_workflow should validate worktree exists."""
        from amelia.server.exceptions import InvalidWorktreeError

        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/nonexistent/path",
            start=False,
            plan_now=True,
        )

        with pytest.raises(InvalidWorktreeError):
            await orchestrator.queue_and_plan_workflow(request)

    @pytest.mark.asyncio
    async def test_queue_and_plan_returns_immediately(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        valid_worktree: str,
    ) -> None:
        """queue_and_plan_workflow returns immediately, planning runs in background."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path=valid_worktree,
            task_title="Test task",
            start=False,
            plan_now=True,
        )

        # Use events to track when planning starts and control when it completes
        planning_started = asyncio.Event()
        planning_complete = asyncio.Event()

        mock_graph = create_mock_graph(
            planning_started_event=planning_started,
            planning_complete_event=planning_complete,
        )

        async with mock_checkpointer_and_graph(mock_graph):
            # This should return immediately before planning completes
            workflow_id = await orchestrator.queue_and_plan_workflow(request)

            # Method returned - planning hasn't started yet or is just starting
            assert workflow_id is not None
            mock_repository.create.assert_called_once()

            # Planning should start in background
            await asyncio.wait_for(planning_started.wait(), timeout=1.0)

            # But update shouldn't have been called yet since planning is blocked
            mock_repository.update.assert_not_called()

            # Let planning complete
            planning_complete.set()

            # Wait for the background task to finish
            if workflow_id in orchestrator._planning_tasks:
                await orchestrator._planning_tasks[workflow_id]

            # Now update should have been called (at least once)
            assert mock_repository.update.call_count >= 1

    @pytest.mark.asyncio
    async def test_queue_and_plan_sets_planning_status_immediately(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        valid_worktree: str,
    ) -> None:
        """Workflow status is 'planning' immediately after queue_and_plan_workflow."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path=valid_worktree,
            start=False,
            plan_now=True,
        )

        # Use an event to block planning indefinitely
        planning_started = asyncio.Event()

        mock_graph = create_mock_graph(
            planning_started_event=planning_started,
            planning_complete_event=asyncio.Event(),  # Never set - blocks forever
        )

        async with mock_checkpointer_and_graph(mock_graph):
            workflow_id = await orchestrator.queue_and_plan_workflow(request)

            # Wait for planning to start
            await asyncio.wait_for(planning_started.wait(), timeout=1.0)

            # Check the created state has planning status
            created_state = mock_repository.create.call_args[0][0]
            assert created_state.workflow_status == "planning"
            assert created_state.current_stage == "architect"

            # Cancel the background task
            if workflow_id in orchestrator._planning_tasks:
                orchestrator._planning_tasks[workflow_id].cancel()
