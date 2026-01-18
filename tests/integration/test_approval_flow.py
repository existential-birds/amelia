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
from unittest.mock import patch

import pytest

from amelia.pipelines.implementation.state import ImplementationState
from amelia.server.models.events import EventType, WorkflowEvent
from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.service import OrchestratorService


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


class TestMissingExecutionState:
    """Test error handling for missing execution_state."""

    async def test_missing_execution_state_sets_status_to_failed(
        self, event_tracker, mock_repository, temp_checkpoint_db
    ):
        """When execution_state is None, status is set to failed."""
        service = OrchestratorService(
            event_tracker,
            mock_repository,
            checkpoint_path=temp_checkpoint_db,
        )

        # Create state without execution_state
        server_state = ServerExecutionState(
            id="wf-error-test",
            issue_id="TEST-ERR",
            worktree_path="/tmp/test-error",
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
    @patch("amelia.server.orchestrator.service.create_implementation_graph")
    async def test_workflow_started_event_emitted(
        self,
        mock_create_graph,
        mock_saver_class,
        event_tracker,
        mock_repository,
        temp_checkpoint_db,
        mock_settings,
        langgraph_mock_factory,
    ):
        """WORKFLOW_STARTED event is emitted at the start."""
        # Setup LangGraph mocks using factory
        mocks = langgraph_mock_factory()
        mock_create_graph.return_value = mocks.graph
        mock_saver_class.from_conn_string.return_value = (
            mocks.saver_class.from_conn_string.return_value
        )

        service = OrchestratorService(
            event_tracker,
            mock_repository,
            checkpoint_path=temp_checkpoint_db,
        )

        core_state = ImplementationState(
            workflow_id="wf-lifecycle-test",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="pending",
        )
        server_state = ServerExecutionState(
            id="wf-lifecycle-test",
            issue_id="TEST-123",
            worktree_path="/tmp/test-lifecycle",
            started_at=datetime.now(UTC),
            execution_state=core_state,
        )

        await mock_repository.create(server_state)
        # Mock settings loading to return valid settings
        with patch.object(service, "_load_settings_for_worktree", return_value=mock_settings):
            await service._run_workflow("wf-lifecycle-test", server_state)

        # Check WORKFLOW_STARTED was emitted
        started_events = event_tracker.get_by_type(EventType.WORKFLOW_STARTED)
        assert len(started_events) == 1


class TestGraphInterruptHandling:
    """Test GraphInterrupt is handled correctly."""

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_implementation_graph")
    async def test_interrupt_sets_status_blocked(
        self,
        mock_create_graph,
        mock_saver_class,
        event_tracker,
        mock_repository,
        temp_checkpoint_db,
        mock_settings,
        langgraph_mock_factory,
    ):
        """__interrupt__ chunk sets status to blocked and emits APPROVAL_REQUIRED."""
        # Setup LangGraph mocks with custom interrupt sequence
        # Combined stream mode returns (mode, data) tuples
        interrupt_items = [
            ("updates", {"architect_node": {}}),  # First node completes
            ("updates", {"__interrupt__": ("Paused for approval",)}),  # Interrupt signal
        ]
        mocks = langgraph_mock_factory(astream_items=interrupt_items)
        mock_create_graph.return_value = mocks.graph
        mock_saver_class.from_conn_string.return_value = (
            mocks.saver_class.from_conn_string.return_value
        )

        service = OrchestratorService(
            event_tracker,
            mock_repository,
            checkpoint_path=temp_checkpoint_db,
        )

        core_state = ImplementationState(
            workflow_id="wf-interrupt-test",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="pending",
        )
        server_state = ServerExecutionState(
            id="wf-interrupt-test",
            issue_id="TEST-456",
            worktree_path="/tmp/test-interrupt",
            started_at=datetime.now(UTC),
            execution_state=core_state,
        )

        await mock_repository.create(server_state)
        # Mock settings loading to return valid settings
        with patch.object(service, "_load_settings_for_worktree", return_value=mock_settings):
            await service._run_workflow("wf-interrupt-test", server_state)

        # Verify status is blocked
        persisted = await mock_repository.get("wf-interrupt-test")
        assert persisted is not None
        assert persisted.workflow_status == "blocked"

        # Verify APPROVAL_REQUIRED was emitted
        approval_events = event_tracker.get_by_type(EventType.APPROVAL_REQUIRED)
        assert len(approval_events) == 1
