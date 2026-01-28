"""Unit tests for replan_workflow orchestrator method."""
import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import AgentConfig, Profile
from amelia.pipelines.implementation.state import ImplementationState, rebuild_implementation_state
from amelia.server.events.bus import EventBus
from amelia.server.exceptions import InvalidStateError, WorkflowConflictError, WorkflowNotFoundError
from amelia.server.models.events import EventType
from amelia.server.models.state import (
    ServerExecutionState,
    WorkflowStatus,
    rebuild_server_execution_state,
)
from amelia.server.orchestrator.service import OrchestratorService


# Rebuild Pydantic models so forward references resolve correctly
rebuild_implementation_state()
rebuild_server_execution_state()


@pytest.fixture
def mock_event_bus() -> EventBus:
    """Create event bus for testing."""
    return EventBus()


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Create mock repository."""
    repo = AsyncMock()
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
        # working_dir is overwritten by _update_profile_working_dir in replan_workflow
        working_dir="/tmp/test-repo",
        agents={
            "architect": agent_config,
            "developer": agent_config,
            "reviewer": agent_config,
            "task_reviewer": agent_config,
            "evaluator": agent_config,
            "plan_validator": agent_config,
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


def make_blocked_workflow(
    workflow_id: str = "wf-replan-1",
    issue_id: str = "ISSUE-REPLAN",
) -> ServerExecutionState:
    """Create a blocked workflow with a plan ready for replan testing."""
    return ServerExecutionState(
        id=workflow_id,
        issue_id=issue_id,
        worktree_path="/tmp/test-repo",
        workflow_status=WorkflowStatus.BLOCKED,
        current_stage=None,
        planned_at=datetime.now(UTC),
        execution_state=ImplementationState(
            workflow_id=workflow_id,
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            goal="Original goal",
            plan_markdown="# Original plan",
            plan_path=None,
            key_files=["original.py"],
            total_tasks=3,
        ),
    )


class TestDeleteCheckpoint:
    """Tests for _delete_checkpoint helper."""

    async def test_delete_checkpoint_removes_data(
        self,
        orchestrator: OrchestratorService,
    ) -> None:
        """_delete_checkpoint should open sqlite and delete checkpoint data."""
        mock_saver_instance = AsyncMock()

        mock_saver_ctx = AsyncMock()
        mock_saver_ctx.__aenter__ = AsyncMock(return_value=mock_saver_instance)
        mock_saver_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "amelia.server.orchestrator.service.AsyncSqliteSaver"
        ) as mock_saver_class:
            mock_saver_class.from_conn_string.return_value = mock_saver_ctx

            await orchestrator._delete_checkpoint("wf-123")

            # Should have opened connection with checkpoint path
            mock_saver_class.from_conn_string.assert_called_once()
            # Should have called adelete_thread with the workflow ID
            mock_saver_instance.adelete_thread.assert_awaited_once_with("wf-123")


class TestReplanWorkflow:
    """Tests for replan_workflow method."""

    async def test_replan_happy_path(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ) -> None:
        """replan_workflow should clear plan, delete checkpoint, and spawn planning task."""
        workflow = make_blocked_workflow()
        mock_repository.get.return_value = workflow

        with (
            patch.object(orchestrator, "_delete_checkpoint", new_callable=AsyncMock) as mock_delete,
            patch.object(orchestrator, "_run_planning_task", new_callable=AsyncMock),
        ):
            await orchestrator.replan_workflow("wf-replan-1")

        # Should have deleted checkpoint
        mock_delete.assert_awaited_once_with("wf-replan-1")

        # Should have updated workflow with cleared plan fields and PENDING status
        mock_repository.update.assert_called()
        updated = mock_repository.update.call_args[0][0]
        assert updated.workflow_status == WorkflowStatus.PENDING
        assert updated.current_stage == "architect"
        assert updated.planned_at is None
        assert updated.execution_state is not None
        assert updated.execution_state.goal is None
        assert updated.execution_state.plan_markdown is None
        assert updated.execution_state.key_files == []
        assert updated.execution_state.total_tasks == 1

    async def test_replan_resets_external_plan_flag(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ) -> None:
        """replan_workflow should reset external_plan to False so Architect runs."""
        workflow = make_blocked_workflow()
        # Simulate a workflow that was originally created with an external plan
        assert workflow.execution_state is not None
        workflow.execution_state = workflow.execution_state.model_copy(
            update={"external_plan": True},
        )
        mock_repository.get.return_value = workflow

        with (
            patch.object(orchestrator, "_delete_checkpoint", new_callable=AsyncMock),
            patch.object(orchestrator, "_run_planning_task", new_callable=AsyncMock),
        ):
            await orchestrator.replan_workflow("wf-replan-1")

        updated = mock_repository.update.call_args[0][0]
        assert updated.execution_state is not None
        assert updated.execution_state.external_plan is False

    async def test_replan_wrong_status_raises(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ) -> None:
        """replan_workflow should reject non-blocked workflows."""
        workflow = make_blocked_workflow()
        workflow.workflow_status = WorkflowStatus.IN_PROGRESS
        mock_repository.get.return_value = workflow

        with pytest.raises(InvalidStateError, match="blocked"):
            await orchestrator.replan_workflow("wf-replan-1")

    async def test_replan_not_found_raises(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ) -> None:
        """replan_workflow should raise for missing workflow."""
        mock_repository.get.return_value = None

        with pytest.raises(WorkflowNotFoundError):
            await orchestrator.replan_workflow("nonexistent")

    async def test_replan_conflict_when_planning_running(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ) -> None:
        """replan_workflow should raise conflict if planning task already active."""
        workflow = make_blocked_workflow()
        mock_repository.get.return_value = workflow

        # Simulate an active planning task
        orchestrator._planning_tasks["wf-replan-1"] = MagicMock(spec=asyncio.Task)

        with pytest.raises(WorkflowConflictError, match="already running"):
            await orchestrator.replan_workflow("wf-replan-1")

    async def test_replan_emits_event(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        mock_event_bus: EventBus,
    ) -> None:
        """replan_workflow should emit a stage_started event."""
        workflow = make_blocked_workflow()
        mock_repository.get.return_value = workflow

        received_events = []
        mock_event_bus.subscribe(lambda e: received_events.append(e))

        with (
            patch.object(orchestrator, "_delete_checkpoint", new_callable=AsyncMock),
            patch.object(orchestrator, "_run_planning_task", new_callable=AsyncMock),
        ):
            await orchestrator.replan_workflow("wf-replan-1")

        # Should have emitted replanning event
        stage_events = [e for e in received_events if e.event_type == EventType.STAGE_STARTED]
        assert len(stage_events) >= 1
        assert any("replan" in (e.message or "").lower() for e in stage_events)

    async def test_replan_missing_profile_raises_without_failing_workflow(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        mock_profile_repo: AsyncMock,
    ) -> None:
        """replan_workflow should raise ValueError for missing profile without setting FAILED."""
        workflow = make_blocked_workflow()
        mock_repository.get.return_value = workflow
        mock_profile_repo.get_profile.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await orchestrator.replan_workflow("wf-replan-1")

        # Workflow should NOT be set to FAILED — the user should be able to
        # fix the profile and retry since the workflow is still BLOCKED.
        mock_repository.set_status.assert_not_called()

    async def test_cancel_terminates_planning_task(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ) -> None:
        """cancel_workflow should cancel an active planning task."""
        workflow = make_blocked_workflow()
        # Set to PENDING (as if planning is in progress)
        workflow.workflow_status = WorkflowStatus.PENDING
        workflow.current_stage = "architect"
        mock_repository.get.return_value = workflow

        # Simulate an active planning task
        mock_task = MagicMock(spec=asyncio.Task)
        orchestrator._planning_tasks["wf-replan-1"] = mock_task

        await orchestrator.cancel_workflow("wf-replan-1")

        # Planning task should have been cancelled
        mock_task.cancel.assert_called_once()
        # Status should be set to cancelled
        mock_repository.set_status.assert_awaited_once_with(
            "wf-replan-1", WorkflowStatus.CANCELLED
        )
