"""Tests for _run_workflow execution bridge."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.state import ExecutionState
from amelia.core.types import Profile, Settings
from amelia.server.models.events import EventType
from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.service import OrchestratorService
from tests.conftest import AsyncIteratorMock


@pytest.fixture
def mock_event_bus():
    """Create mock event bus."""
    return MagicMock()


@pytest.fixture
def mock_repository():
    """Create mock repository."""
    repo = AsyncMock()
    repo.get_max_event_sequence.return_value = 0
    repo.save_event = AsyncMock()
    repo.set_status = AsyncMock()
    return repo


@pytest.fixture
def service(mock_event_bus, mock_repository, mock_settings: Settings):
    """Create OrchestratorService with mocked dependencies."""
    svc = OrchestratorService(mock_event_bus, mock_repository, mock_settings)
    svc._checkpoint_path = "/tmp/test_checkpoints.db"
    return svc


@pytest.fixture
def server_state():
    """Create test ServerExecutionState."""
    core_state = ExecutionState(
        profile=Profile(name="test", driver="cli:claude"),
    )
    return ServerExecutionState(
        id="wf-123",
        issue_id="ISSUE-456",
        worktree_path="/tmp/test",
        worktree_name="test-branch",
        started_at=datetime.now(UTC),
        execution_state=core_state,
    )


class TestRunWorkflowEmitsLifecycleEvents:
    """Test _run_workflow emits lifecycle events."""

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_orchestrator_graph")
    async def test_emits_workflow_started_event(
        self, mock_create_graph, mock_saver_class, service, server_state
    ):
        """_run_workflow emits WORKFLOW_STARTED at beginning."""
        # Setup mock graph that completes immediately (empty stream)
        mock_graph = AsyncMock()
        mock_graph.astream = MagicMock(return_value=AsyncIteratorMock([]))
        mock_create_graph.return_value = mock_graph

        mock_saver = AsyncMock()
        mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
            return_value=mock_saver
        )
        mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

        emitted_events = []
        original_emit = service._emit

        async def capture_emit(*args, **kwargs):
            emitted_events.append(args)
            return await original_emit(*args, **kwargs)

        service._emit = capture_emit

        await service._run_workflow("wf-123", server_state)

        # Check WORKFLOW_STARTED was emitted
        started_events = [e for e in emitted_events if e[1] == EventType.WORKFLOW_STARTED]
        assert len(started_events) == 1

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_orchestrator_graph")
    async def test_emits_workflow_completed_on_success(
        self, mock_create_graph, mock_saver_class, service, server_state
    ):
        """_run_workflow emits WORKFLOW_COMPLETED on successful completion."""
        mock_graph = AsyncMock()
        # Simulate a graph that completes without interruption
        mock_graph.astream = MagicMock(return_value=AsyncIteratorMock([
            {"architect_node": {}},  # Node completes
        ]))
        mock_create_graph.return_value = mock_graph

        mock_saver = AsyncMock()
        mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
            return_value=mock_saver
        )
        mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

        emitted_events = []

        async def capture_emit(*args, **kwargs):
            emitted_events.append(args)

        service._emit = capture_emit

        await service._run_workflow("wf-123", server_state)

        completed_events = [e for e in emitted_events if e[1] == EventType.WORKFLOW_COMPLETED]
        assert len(completed_events) == 1


class TestRunWorkflowStateSerialization:
    """Test _run_workflow passes JSON-serializable state to LangGraph."""

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_orchestrator_graph")
    async def test_passes_json_serializable_state_to_astream(
        self, mock_create_graph, mock_saver_class, service, server_state
    ):
        """_run_workflow passes JSON-serializable dict to graph.astream().

        This is critical for SQLite checkpointing - LangGraph's AsyncSqliteSaver
        uses json.dumps() internally, which fails on Pydantic BaseModel objects.
        """
        import json

        mock_graph = AsyncMock()
        captured_input = []

        def capture_astream(input_state, **kwargs):
            captured_input.append(input_state)
            return AsyncIteratorMock([])

        mock_graph.astream = MagicMock(side_effect=capture_astream)
        mock_create_graph.return_value = mock_graph

        mock_saver = AsyncMock()
        mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
            return_value=mock_saver
        )
        mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

        service._emit = AsyncMock()

        await service._run_workflow("wf-123", server_state)

        # Verify astream was called
        assert len(captured_input) == 1
        state_input = captured_input[0]

        # State should be a dict, not a Pydantic model
        assert isinstance(state_input, dict), (
            f"Expected dict, got {type(state_input).__name__}. "
            "Pydantic models are not JSON-serializable for LangGraph checkpointing."
        )

        # State should be JSON-serializable (no Pydantic objects nested inside)
        try:
            json.dumps(state_input)
        except TypeError as e:
            pytest.fail(
                f"State passed to graph.astream() is not JSON-serializable: {e}. "
                "Use model_dump(mode='json') to ensure all nested objects are serializable."
            )


class TestRunWorkflowInterruptHandling:
    """Test _run_workflow handles __interrupt__ chunk correctly."""

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_orchestrator_graph")
    async def test_graph_interrupt_sets_status_to_blocked(
        self, mock_create_graph, mock_saver_class, service, server_state
    ):
        """__interrupt__ chunk sets workflow status to blocked, not failed."""
        # Simulate interrupt via __interrupt__ chunk (new astream API)
        mock_graph = AsyncMock()
        mock_graph.astream = MagicMock(return_value=AsyncIteratorMock([
            {"architect_node": {}},  # First node completes
            {"__interrupt__": ("Interrupted at human_approval_node",)},  # Interrupt signal
        ]))
        mock_create_graph.return_value = mock_graph

        mock_saver = AsyncMock()
        mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
            return_value=mock_saver
        )
        mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

        emitted_events = []

        async def capture_emit(*args, **kwargs):
            emitted_events.append(args)

        service._emit = capture_emit
        service._repository.set_status = AsyncMock()

        await service._run_workflow("wf-123", server_state)

        # Should emit APPROVAL_REQUIRED, not WORKFLOW_FAILED
        approval_events = [e for e in emitted_events if e[1] == EventType.APPROVAL_REQUIRED]
        failed_events = [e for e in emitted_events if e[1] == EventType.WORKFLOW_FAILED]
        assert len(approval_events) == 1
        assert len(failed_events) == 0

        # Should set status to blocked
        service._repository.set_status.assert_called_with("wf-123", "blocked")

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_orchestrator_graph")
    async def test_creates_graph_with_interrupt_before(
        self, mock_create_graph, mock_saver_class, service, server_state
    ):
        """_run_workflow passes interrupt_before to create_orchestrator_graph."""
        mock_graph = AsyncMock()
        mock_graph.astream = MagicMock(return_value=AsyncIteratorMock([]))
        mock_create_graph.return_value = mock_graph

        mock_saver = AsyncMock()
        mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
            return_value=mock_saver
        )
        mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

        service._emit = AsyncMock()

        await service._run_workflow("wf-123", server_state)

        # Verify interrupt_before was passed
        mock_create_graph.assert_called_once()
        call_kwargs = mock_create_graph.call_args[1]
        assert call_kwargs.get("interrupt_before") == ["human_approval_node"]


