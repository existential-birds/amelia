"""Tests for LangGraph to WorkflowEvent mapping."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.core.types import Settings
from amelia.server.models.events import EventType
from amelia.server.orchestrator.service import STAGE_NODES, OrchestratorService


class TestStageNodesConstant:
    """Test STAGE_NODES constant."""

    def test_stage_nodes_contains_expected_nodes(self):
        """STAGE_NODES contains all workflow stage nodes."""
        expected = {"architect_node", "human_approval_node", "developer_node", "reviewer_node"}
        assert expected == STAGE_NODES

    def test_stage_nodes_is_frozenset(self):
        """STAGE_NODES is immutable."""
        assert isinstance(STAGE_NODES, frozenset)


class TestHandleGraphEvent:
    """Test _handle_graph_event method."""

    @pytest.fixture
    def service(self, mock_settings: Settings):
        """Create OrchestratorService with mocked dependencies."""
        event_bus = MagicMock()
        repository = AsyncMock()
        repository.get_max_event_sequence.return_value = 0
        return OrchestratorService(event_bus, repository, mock_settings)

    async def test_on_chain_start_emits_stage_started(self, service):
        """on_chain_start for stage node emits STAGE_STARTED event."""
        service._emit = AsyncMock()
        event = {"event": "on_chain_start", "name": "architect_node"}

        await service._handle_graph_event("wf-123", event)

        service._emit.assert_called_once()
        call_args = service._emit.call_args
        assert call_args[0][1] == EventType.STAGE_STARTED
        assert "architect_node" in call_args[0][2]

    async def test_on_chain_end_emits_stage_completed(self, service):
        """on_chain_end for stage node emits STAGE_COMPLETED event."""
        service._emit = AsyncMock()
        event = {"event": "on_chain_end", "name": "developer_node", "data": {"result": "ok"}}

        await service._handle_graph_event("wf-123", event)

        service._emit.assert_called_once()
        call_args = service._emit.call_args
        assert call_args[0][1] == EventType.STAGE_COMPLETED

    async def test_on_chain_error_emits_system_error(self, service):
        """on_chain_error emits SYSTEM_ERROR event."""
        service._emit = AsyncMock()
        event = {
            "event": "on_chain_error",
            "name": "reviewer_node",
            "data": {"error": "Connection timeout"},
        }

        await service._handle_graph_event("wf-123", event)

        service._emit.assert_called_once()
        call_args = service._emit.call_args
        assert call_args[0][1] == EventType.SYSTEM_ERROR
        assert "Connection timeout" in call_args[0][2]

    async def test_non_stage_node_not_emitted(self, service):
        """Events from non-stage nodes are not emitted."""
        service._emit = AsyncMock()
        event = {"event": "on_chain_start", "name": "some_internal_node"}

        await service._handle_graph_event("wf-123", event)

        service._emit.assert_not_called()
