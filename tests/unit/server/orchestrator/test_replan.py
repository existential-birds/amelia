"""Unit tests for replan_workflow orchestrator method."""
import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import AgentConfig, Profile
from amelia.pipelines.implementation.state import ImplementationState
from amelia.server.events.bus import EventBus
from amelia.server.exceptions import InvalidStateError, WorkflowConflictError, WorkflowNotFoundError
from amelia.server.models.events import EventType
from amelia.server.models.state import ServerExecutionState, WorkflowStatus
from amelia.server.orchestrator.service import OrchestratorService


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
        working_dir="/tmp/test-repo",
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
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        mock_saver = AsyncMock()
        mock_saver_ctx = AsyncMock()
        mock_saver_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_saver_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "amelia.server.orchestrator.service.AsyncSqliteSaver"
        ) as mock_saver_class:
            mock_saver_class.from_conn_string.return_value = mock_saver_ctx

            await orchestrator._delete_checkpoint("wf-123")

            # Should have opened connection with checkpoint path
            mock_saver_class.from_conn_string.assert_called_once()
            # Should have executed delete queries
            assert mock_conn.execute.call_count >= 1
