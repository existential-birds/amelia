"""Tests for queue_workflow orchestrator method."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.models.state import ServerExecutionState
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
    repo = MagicMock()
    repo.save = AsyncMock()
    repo.create = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    repo.list_active = AsyncMock(return_value=[])
    repo.save_event = AsyncMock()
    repo.get_max_event_sequence = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def orchestrator(mock_event_bus: MagicMock, mock_repository: MagicMock) -> OrchestratorService:
    """Create orchestrator with mocked dependencies."""
    return OrchestratorService(
        event_bus=mock_event_bus,
        repository=mock_repository,
        max_concurrent=5,
    )


class TestQueueWorkflow:
    """Tests for queue_workflow method."""

    @pytest.mark.asyncio
    async def test_queue_workflow_creates_pending_state(
        self, orchestrator: OrchestratorService, mock_repository: MagicMock
    ) -> None:
        """queue_workflow creates workflow in pending state without starting."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            start=False,
            plan_now=False,
        )

        workflow_id = await orchestrator.queue_workflow(request)

        assert workflow_id.startswith("wf-")
        mock_repository.create.assert_called_once()
        saved_state: ServerExecutionState = mock_repository.create.call_args[0][0]
        assert saved_state.workflow_status == "pending"
        assert saved_state.started_at is None
        assert saved_state.planned_at is None

    @pytest.mark.asyncio
    async def test_queue_workflow_does_not_spawn_task(
        self, orchestrator: OrchestratorService
    ) -> None:
        """queue_workflow should not spawn an execution task."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            start=False,
        )

        await orchestrator.queue_workflow(request)

        # No active tasks should be spawned
        assert len(orchestrator._active_tasks) == 0

    @pytest.mark.asyncio
    async def test_queue_workflow_allows_multiple_pending_per_worktree(
        self, orchestrator: OrchestratorService, mock_repository: MagicMock
    ) -> None:
        """Multiple pending workflows allowed on same worktree."""
        # First workflow
        mock_repository.list_active.return_value = []
        request1 = CreateWorkflowRequest(
            issue_id="ISSUE-1",
            worktree_path="/path/to/repo",
            start=False,
        )
        await orchestrator.queue_workflow(request1)

        # Simulate first workflow exists as pending
        mock_repository.list_active.return_value = [
            ServerExecutionState(
                id="wf-1",
                issue_id="ISSUE-1",
                worktree_path="/path/to/repo",
                worktree_name="repo",
                workflow_status="pending",
            )
        ]

        # Second workflow on same worktree should succeed
        request2 = CreateWorkflowRequest(
            issue_id="ISSUE-2",
            worktree_path="/path/to/repo",
            start=False,
        )
        workflow_id = await orchestrator.queue_workflow(request2)
        assert workflow_id is not None

    @pytest.mark.asyncio
    async def test_queue_workflow_emits_created_event(
        self, orchestrator: OrchestratorService, mock_event_bus: MagicMock, mock_repository: MagicMock
    ) -> None:
        """queue_workflow should emit workflow_created event."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            start=False,
        )

        await orchestrator.queue_workflow(request)

        mock_event_bus.emit.assert_called()
        # Check event type in call args
        event = mock_event_bus.emit.call_args[0][0]
        assert event.event_type.value == "workflow_created"
