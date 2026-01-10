# tests/unit/server/orchestrator/test_start_batch.py
"""Tests for start_batch_workflows orchestrator method."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.server.exceptions import WorkflowConflictError
from amelia.server.models.requests import BatchStartRequest
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
    repo.find_by_status = AsyncMock(return_value=[])
    repo.get = AsyncMock()
    repo.update = AsyncMock()
    repo.save_event = AsyncMock()
    repo.get_max_event_sequence = AsyncMock(return_value=0)
    repo.get_by_worktree = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def orchestrator(mock_event_bus: MagicMock, mock_repository: MagicMock) -> OrchestratorService:
    """Create orchestrator with mocked dependencies."""
    return OrchestratorService(
        event_bus=mock_event_bus,
        repository=mock_repository,
        max_concurrent=5,
    )


class TestStartBatchWorkflows:
    """Tests for start_batch_workflows method."""

    @pytest.mark.asyncio
    async def test_start_batch_all_pending(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """Start all pending workflows when no filter specified."""
        pending = [
            ServerExecutionState(
                id="wf-1",
                issue_id="ISSUE-1",
                worktree_path="/repo1",
                workflow_status="pending",
            ),
            ServerExecutionState(
                id="wf-2",
                issue_id="ISSUE-2",
                worktree_path="/repo2",
                workflow_status="pending",
            ),
        ]
        mock_repository.find_by_status.return_value = pending

        with patch.object(
            orchestrator, "start_pending_workflow", new_callable=AsyncMock
        ) as mock_start:
            request = BatchStartRequest()
            response = await orchestrator.start_batch_workflows(request)

        assert len(response.started) == 2
        assert "wf-1" in response.started
        assert "wf-2" in response.started
        assert response.errors == {}
        assert mock_start.call_count == 2

    @pytest.mark.asyncio
    async def test_start_batch_specific_ids(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """Start only specified workflow IDs."""

        def mock_get(workflow_id: str) -> ServerExecutionState:
            return ServerExecutionState(
                id=workflow_id,
                issue_id=f"ISSUE-{workflow_id}",
                worktree_path=f"/repo/{workflow_id}",
                workflow_status="pending",
            )

        mock_repository.get.side_effect = mock_get

        with patch.object(
            orchestrator, "start_pending_workflow", new_callable=AsyncMock
        ):
            request = BatchStartRequest(workflow_ids=["wf-1", "wf-2"])
            response = await orchestrator.start_batch_workflows(request)

        assert set(response.started) == {"wf-1", "wf-2"}
        assert response.errors == {}

    @pytest.mark.asyncio
    async def test_start_batch_filter_by_worktree(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """Filter pending workflows by worktree path."""
        pending = [
            ServerExecutionState(
                id="wf-1",
                issue_id="ISSUE-1",
                worktree_path="/repo/a",
                workflow_status="pending",
            ),
            ServerExecutionState(
                id="wf-2",
                issue_id="ISSUE-2",
                worktree_path="/repo/b",
                workflow_status="pending",
            ),
        ]
        mock_repository.find_by_status.return_value = pending

        with patch.object(
            orchestrator, "start_pending_workflow", new_callable=AsyncMock
        ):
            request = BatchStartRequest(worktree_path="/repo/a")
            response = await orchestrator.start_batch_workflows(request)

        assert response.started == ["wf-1"]
        assert response.errors == {}

    @pytest.mark.asyncio
    async def test_start_batch_partial_failure(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """Handle partial failures gracefully."""
        pending = [
            ServerExecutionState(
                id="wf-1",
                issue_id="ISSUE-1",
                worktree_path="/repo",
                workflow_status="pending",
            ),
            ServerExecutionState(
                id="wf-2",
                issue_id="ISSUE-2",
                worktree_path="/repo",
                workflow_status="pending",
            ),
        ]
        mock_repository.find_by_status.return_value = pending

        # wf-1 succeeds, wf-2 fails due to worktree conflict
        async def mock_start(wf_id: str) -> None:
            if wf_id == "wf-2":
                raise WorkflowConflictError("/repo", "wf-1")

        with patch.object(orchestrator, "start_pending_workflow", side_effect=mock_start):
            request = BatchStartRequest()
            response = await orchestrator.start_batch_workflows(request)

        assert response.started == ["wf-1"]
        assert "wf-2" in response.errors
        # Check for stable substrings from WorkflowConflictError("/repo", "wf-1")
        err = response.errors["wf-2"]
        assert "/repo" in err
        assert "wf-1" in err

    @pytest.mark.asyncio
    async def test_start_batch_empty_result(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """Return empty response when no pending workflows."""
        mock_repository.find_by_status.return_value = []

        request = BatchStartRequest()
        response = await orchestrator.start_batch_workflows(request)

        assert response.started == []
        assert response.errors == {}

    @pytest.mark.asyncio
    async def test_start_batch_workflow_not_found(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """Handle case when specified workflow ID doesn't exist."""
        mock_repository.get.return_value = None

        with patch.object(
            orchestrator, "start_pending_workflow", new_callable=AsyncMock
        ) as mock_start:
            from amelia.server.exceptions import WorkflowNotFoundError

            mock_start.side_effect = WorkflowNotFoundError("wf-nonexistent")

            request = BatchStartRequest(workflow_ids=["wf-nonexistent"])
            response = await orchestrator.start_batch_workflows(request)

        assert response.started == []
        assert "wf-nonexistent" in response.errors
