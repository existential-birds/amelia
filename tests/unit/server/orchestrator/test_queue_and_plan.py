"""Tests for queue_and_plan_workflow orchestrator method."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.state import ExecutionState
from amelia.core.types import Issue
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
def orchestrator(
    mock_event_bus: MagicMock,
    mock_repository: MagicMock,
) -> OrchestratorService:
    """Create orchestrator with mocked dependencies."""
    return OrchestratorService(
        event_bus=mock_event_bus,
        repository=mock_repository,
        max_concurrent=5,
    )


@pytest.fixture
def valid_worktree(tmp_path: Path) -> str:
    """Create a valid git worktree directory with required settings file.

    Args:
        tmp_path: Pytest tmp_path fixture.

    Returns:
        Absolute path to the valid worktree.
    """
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").touch()
    # Worktree settings are required (no fallback to server settings)
    settings_content = """
active_profile: test
profiles:
  test:
    name: test
    driver: cli:claude
    model: sonnet
    tracker: noop
"""
    (worktree / "settings.amelia.yaml").write_text(settings_content)
    return str(worktree)


class TestQueueAndPlanWorkflow:
    """Tests for queue_and_plan_workflow method."""

    @pytest.mark.asyncio
    async def test_queue_and_plan_runs_architect(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        valid_worktree: str,
    ) -> None:
        """queue_and_plan_workflow runs Architect and stores plan."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path=valid_worktree,
            start=False,
            plan_now=True,
        )

        # Mock the architect to return an execution state with a plan
        mock_architect = MagicMock()

        async def mock_plan_gen(*args, **kwargs):
            """Mock async generator that yields plan result."""
            state = ExecutionState(
                profile_id="test",
                issue=Issue(id="ISSUE-123", title="Test", description="Test desc"),
                goal="Implement the test feature",
                plan_markdown="# Plan\n\n1. Do thing\n2. Do other thing",
            )
            from amelia.server.models.events import EventType, WorkflowEvent

            event = WorkflowEvent(
                id="evt-1",
                workflow_id="wf-test",
                sequence=1,
                timestamp=datetime.now(UTC),
                agent="architect",
                event_type=EventType.AGENT_OUTPUT,
                message="Plan generated",
            )
            yield state, event

        mock_architect.plan = mock_plan_gen

        # Patch architect creation and tracker
        with (
            patch.object(
                orchestrator, "_create_architect_for_planning", return_value=mock_architect
            ),
            patch(
                "amelia.server.orchestrator.service.create_tracker"
            ) as mock_create_tracker,
        ):
            # Setup mock tracker
            mock_tracker = MagicMock()
            mock_tracker.get_issue = MagicMock(
                return_value=Issue(id="ISSUE-123", title="Test", description="Test desc")
            )
            mock_create_tracker.return_value = mock_tracker

            workflow_id = await orchestrator.queue_and_plan_workflow(request)

            # Wait for the background planning task to complete
            if workflow_id in orchestrator._planning_tasks:
                await orchestrator._planning_tasks[workflow_id]

        assert workflow_id is not None

        # Check state was saved with plan and planned_at
        # First call should be create(), second should be update()
        mock_repository.create.assert_called_once()
        mock_repository.update.assert_called_once()

        updated_state = mock_repository.update.call_args[0][0]
        assert updated_state.workflow_status == "pending"
        assert updated_state.planned_at is not None
        assert updated_state.execution_state is not None
        assert updated_state.execution_state.goal is not None

    @pytest.mark.asyncio
    async def test_queue_and_plan_stays_pending(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        valid_worktree: str,
    ) -> None:
        """Workflow remains pending after planning (not started)."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path=valid_worktree,
            start=False,
            plan_now=True,
        )

        # Mock the architect
        mock_architect = MagicMock()

        async def mock_plan_gen(*args, **kwargs):
            """Mock async generator that yields plan result."""
            state = ExecutionState(
                profile_id="test",
                issue=Issue(id="ISSUE-123", title="Test", description="Test desc"),
                goal="Implement the test feature",
                plan_markdown="# Plan",
            )
            from amelia.server.models.events import EventType, WorkflowEvent

            event = WorkflowEvent(
                id="evt-1",
                workflow_id="wf-test",
                sequence=1,
                timestamp=datetime.now(UTC),
                agent="architect",
                event_type=EventType.AGENT_OUTPUT,
                message="Plan generated",
            )
            yield state, event

        mock_architect.plan = mock_plan_gen

        with (
            patch.object(
                orchestrator, "_create_architect_for_planning", return_value=mock_architect
            ),
            patch(
                "amelia.server.orchestrator.service.create_tracker"
            ) as mock_create_tracker,
        ):
            mock_tracker = MagicMock()
            mock_tracker.get_issue = MagicMock(
                return_value=Issue(id="ISSUE-123", title="Test", description="Test desc")
            )
            mock_create_tracker.return_value = mock_tracker

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
        """If Architect fails, workflow is marked failed."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path=valid_worktree,
            start=False,
            plan_now=True,
        )

        # Mock architect that raises an exception
        mock_architect = MagicMock()

        async def mock_plan_gen_fail(*args, **kwargs):
            """Mock async generator that raises."""
            raise Exception("LLM API error")
            yield  # Make it an async generator

        mock_architect.plan = mock_plan_gen_fail

        with (
            patch.object(
                orchestrator, "_create_architect_for_planning", return_value=mock_architect
            ),
            patch(
                "amelia.server.orchestrator.service.create_tracker"
            ) as mock_create_tracker,
        ):
            mock_tracker = MagicMock()
            mock_tracker.get_issue = MagicMock(
                return_value=Issue(id="ISSUE-123", title="Test", description="Test desc")
            )
            mock_create_tracker.return_value = mock_tracker

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

        mock_architect = MagicMock()

        async def mock_plan_gen(*args, **kwargs):
            """Mock async generator that yields plan result."""
            state = ExecutionState(
                profile_id="test",
                issue=Issue(id="ISSUE-123", title="Test", description="Test desc"),
                goal="Implement the test feature",
                plan_markdown="# Plan",
            )
            from amelia.server.models.events import EventType, WorkflowEvent

            event = WorkflowEvent(
                id="evt-1",
                workflow_id="wf-test",
                sequence=1,
                timestamp=datetime.now(UTC),
                agent="architect",
                event_type=EventType.AGENT_OUTPUT,
                message="Plan generated",
            )
            yield state, event

        mock_architect.plan = mock_plan_gen

        with (
            patch.object(
                orchestrator, "_create_architect_for_planning", return_value=mock_architect
            ),
            patch(
                "amelia.server.orchestrator.service.create_tracker"
            ) as mock_create_tracker,
        ):
            mock_tracker = MagicMock()
            mock_tracker.get_issue = MagicMock(
                return_value=Issue(id="ISSUE-123", title="Test", description="Test desc")
            )
            mock_create_tracker.return_value = mock_tracker

            workflow_id = await orchestrator.queue_and_plan_workflow(request)

            # Wait for the background planning task to complete
            if workflow_id in orchestrator._planning_tasks:
                await orchestrator._planning_tasks[workflow_id]

        # Should have emitted events (workflow_created, plan events, etc.)
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

        # Use an event to track when planning starts
        planning_started = asyncio.Event()
        planning_complete = asyncio.Event()

        mock_architect = MagicMock()

        async def slow_plan_gen(*args, **kwargs):
            """Mock async generator that signals when planning starts."""
            planning_started.set()
            # Wait to simulate slow planning
            await planning_complete.wait()
            state = ExecutionState(
                profile_id="test",
                issue=Issue(id="ISSUE-123", title="Test", description="Test desc"),
                goal="Implement the test feature",
                plan_markdown="# Plan",
            )
            yield state, None

        mock_architect.plan = slow_plan_gen

        with patch.object(
            orchestrator, "_create_architect_for_planning", return_value=mock_architect
        ):
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

            # Now update should have been called
            mock_repository.update.assert_called_once()
