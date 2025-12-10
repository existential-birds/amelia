# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Integration tests for the complete approval flow.

These tests verify the interrupt/resume cycle works end-to-end:
1. Graph executes until interrupt_before human_approval_node
2. GraphInterrupt is raised, workflow status becomes "blocked"
3. User approves via approve_workflow()
4. Graph resumes with human_approved=True in state
5. Workflow completes successfully
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from amelia.core.state import ExecutionState
from amelia.core.types import Profile
from amelia.server.database.repository import WorkflowRepository
from amelia.server.models.events import EventType, WorkflowEvent
from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.service import OrchestratorService
from tests.conftest import AsyncIteratorMock


@pytest.fixture
def temp_checkpoint_db():
    """Create temporary checkpoint database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def event_tracker():
    """Create event bus that tracks all emitted events."""

    class EventTracker:
        def __init__(self):
            self.events: list[WorkflowEvent] = []

        def emit(self, event: WorkflowEvent) -> None:
            self.events.append(event)

        def get_by_type(self, event_type: EventType) -> list[WorkflowEvent]:
            return [e for e in self.events if e.event_type == event_type]

    return EventTracker()


@pytest.fixture
def mock_repository():
    """Create in-memory repository mock."""
    repo = AsyncMock(spec=WorkflowRepository)
    repo.workflows: dict[str, ServerExecutionState] = {}
    repo.events: list[WorkflowEvent] = []
    repo.event_sequence: dict[str, int] = {}

    async def create(state: ServerExecutionState) -> None:
        repo.workflows[state.id] = state

    async def get(workflow_id: str) -> ServerExecutionState | None:
        return repo.workflows.get(workflow_id)

    async def set_status(
        workflow_id: str, status: str, failure_reason: str | None = None
    ) -> None:
        if workflow_id in repo.workflows:
            repo.workflows[workflow_id] = repo.workflows[workflow_id].model_copy(
                update={"workflow_status": status, "failure_reason": failure_reason}
            )

    async def save_event(event: WorkflowEvent) -> None:
        repo.events.append(event)

    async def get_max_event_sequence(workflow_id: str) -> int:
        return repo.event_sequence.get(workflow_id, 0)

    repo.create = create
    repo.get = get
    repo.set_status = set_status
    repo.save_event = save_event
    repo.get_max_event_sequence = get_max_event_sequence

    return repo


class TestMissingExecutionState:
    """Test error handling for missing execution_state."""

    async def test_missing_execution_state_sets_status_to_failed(
        self, event_tracker, mock_repository, temp_checkpoint_db, mock_settings
    ):
        """When execution_state is None, status is set to failed."""
        service = OrchestratorService(
            event_tracker,
            mock_repository,
            settings=mock_settings,
            checkpoint_path=temp_checkpoint_db,
        )

        # Create state without execution_state
        server_state = ServerExecutionState(
            id="wf-error-test",
            issue_id="TEST-ERR",
            worktree_path="/tmp/test-error",
            worktree_name="test-error",
            started_at=datetime.now(UTC),
            execution_state=None,  # Missing - will cause error
        )

        await mock_repository.create(server_state)
        await service._run_workflow("wf-error-test", server_state)

        # Verify status is "failed"
        persisted = await mock_repository.get("wf-error-test")
        assert persisted is not None
        assert persisted.workflow_status == "failed"
        assert persisted.failure_reason is not None
        assert "Missing execution state" in persisted.failure_reason


class TestLifecycleEvents:
    """Test workflow lifecycle event emission."""

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_orchestrator_graph")
    async def test_workflow_started_event_emitted(
        self,
        mock_create_graph,
        mock_saver_class,
        event_tracker,
        mock_repository,
        temp_checkpoint_db,
        mock_settings,
    ):
        """WORKFLOW_STARTED event is emitted at the start."""
        # Setup mock graph that completes immediately
        mock_graph = AsyncMock()
        # Use lambda to return iterator directly without AsyncMock wrapper
        mock_graph.astream = lambda *args, **kwargs: AsyncIteratorMock([])
        mock_create_graph.return_value = mock_graph

        mock_saver = AsyncMock()
        mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
            return_value=mock_saver
        )
        mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

        service = OrchestratorService(
            event_tracker,
            mock_repository,
            settings=mock_settings,
            checkpoint_path=temp_checkpoint_db,
        )

        core_state = ExecutionState(
            profile=Profile(name="test", driver="cli:claude"),
        )
        server_state = ServerExecutionState(
            id="wf-lifecycle-test",
            issue_id="TEST-123",
            worktree_path="/tmp/test-lifecycle",
            worktree_name="test-lifecycle",
            started_at=datetime.now(UTC),
            execution_state=core_state,
        )

        await mock_repository.create(server_state)
        await service._run_workflow("wf-lifecycle-test", server_state)

        # Check WORKFLOW_STARTED was emitted
        started_events = event_tracker.get_by_type(EventType.WORKFLOW_STARTED)
        assert len(started_events) == 1


class TestGraphInterruptHandling:
    """Test GraphInterrupt is handled correctly."""

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_orchestrator_graph")
    async def test_interrupt_sets_status_blocked(
        self,
        mock_create_graph,
        mock_saver_class,
        event_tracker,
        mock_repository,
        temp_checkpoint_db,
        mock_settings,
    ):
        """__interrupt__ chunk sets status to blocked and emits APPROVAL_REQUIRED."""
        # Create async iterator that yields __interrupt__ chunk (new astream API)
        class InterruptIterator:
            def __init__(self):
                self._items = [
                    {"architect_node": {}},  # First node completes
                    {"__interrupt__": ("Paused for approval",)},  # Interrupt signal
                ]
                self._index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._index >= len(self._items):
                    raise StopAsyncIteration
                item = self._items[self._index]
                self._index += 1
                return item

        mock_graph = AsyncMock()
        # Use astream (not astream_events) to match the updated implementation
        mock_graph.astream = lambda *args, **kwargs: InterruptIterator()
        mock_create_graph.return_value = mock_graph

        mock_saver = AsyncMock()
        mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
            return_value=mock_saver
        )
        mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

        service = OrchestratorService(
            event_tracker,
            mock_repository,
            settings=mock_settings,
            checkpoint_path=temp_checkpoint_db,
        )

        core_state = ExecutionState(
            profile=Profile(name="test", driver="cli:claude"),
        )
        server_state = ServerExecutionState(
            id="wf-interrupt-test",
            issue_id="TEST-456",
            worktree_path="/tmp/test-interrupt",
            worktree_name="test-interrupt",
            started_at=datetime.now(UTC),
            execution_state=core_state,
        )

        await mock_repository.create(server_state)
        await service._run_workflow("wf-interrupt-test", server_state)

        # Verify status is blocked
        persisted = await mock_repository.get("wf-interrupt-test")
        assert persisted is not None
        assert persisted.workflow_status == "blocked"

        # Verify APPROVAL_REQUIRED was emitted
        approval_events = event_tracker.get_by_type(EventType.APPROVAL_REQUIRED)
        assert len(approval_events) >= 1
