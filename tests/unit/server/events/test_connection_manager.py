# tests/unit/server/events/test_connection_manager.py
"""Tests for WebSocket connection manager."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect

from amelia.server.events.connection_manager import ConnectionManager
from amelia.server.models.events import (
    EventDomain,
    EventLevel,
    EventType,
    WorkflowEvent,
)


@pytest.fixture
def manager():
    """Create ConnectionManager instance."""
    return ConnectionManager()


@pytest.fixture
def mock_websocket():
    """Create mock WebSocket."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


class TestConnectionManager:
    """Tests for ConnectionManager."""

    async def test_disconnect_removes_connection(self, manager, mock_websocket) -> None:
        """disconnect() removes connection from tracking."""
        await manager.connect(mock_websocket)
        await manager.disconnect(mock_websocket)

        assert manager.active_connections == 0

    async def test_subscribe_multiple_workflows(self, manager, mock_websocket) -> None:
        """Can subscribe to multiple workflows."""
        await manager.connect(mock_websocket)
        await manager.subscribe(mock_websocket, "wf-123")
        await manager.subscribe(mock_websocket, "wf-456")

        assert "wf-123" in manager._connections[mock_websocket]
        assert "wf-456" in manager._connections[mock_websocket]

    async def test_subscribe_all_clears_subscription_set(self, manager, mock_websocket) -> None:
        """subscribe_all() clears subscription set (empty = all)."""
        await manager.connect(mock_websocket)
        await manager.subscribe(mock_websocket, "wf-123")
        await manager.subscribe_all(mock_websocket)

        assert manager._connections[mock_websocket] == set()

    @pytest.mark.parametrize(
        "subscription_workflow,event_workflow,should_send",
        [
            (None, "wf-456", True),  # subscribed to all
            ("wf-456", "wf-456", True),  # specific match
            ("wf-999", "wf-456", False),  # no match
        ],
        ids=["subscribe_all", "specific_match", "no_match"],
    )
    async def test_broadcast_filtering(
        self, manager, mock_websocket, subscription_workflow, event_workflow, should_send, make_event
    ) -> None:
        """broadcast() respects subscription filters."""
        await manager.connect(mock_websocket)
        if subscription_workflow:
            await manager.subscribe(mock_websocket, subscription_workflow)

        event = make_event(
            id="evt-123",
            workflow_id=event_workflow,
            timestamp=datetime.now(UTC),
            message="Started",
        )

        await manager.broadcast(event)

        if should_send:
            mock_websocket.send_json.assert_awaited_once()
        else:
            mock_websocket.send_json.assert_not_awaited()

    async def test_broadcast_handles_disconnected_socket(self, manager, mock_websocket, make_event) -> None:
        """broadcast() removes disconnected sockets gracefully."""
        await manager.connect(mock_websocket)
        mock_websocket.send_json.side_effect = WebSocketDisconnect()

        event = make_event(
            id="evt-123",
            workflow_id="wf-456",
            timestamp=datetime.now(UTC),
            message="Started",
        )

        await manager.broadcast(event)

        # Connection should be removed after disconnect
        assert manager.active_connections == 0

    async def test_close_all_handles_errors(self, manager, mock_websocket) -> None:
        """close_all() handles errors gracefully."""
        mock_websocket.close.side_effect = Exception("Close failed")

        await manager.connect(mock_websocket)
        await manager.close_all()

        # Should not raise, just clear connections
        assert manager.active_connections == 0

    async def test_active_connections_count(self, manager) -> None:
        """active_connections property returns correct count."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()

        assert manager.active_connections == 0

        await manager.connect(ws1)
        assert manager.active_connections == 1

        await manager.connect(ws2)
        assert manager.active_connections == 2

        await manager.disconnect(ws1)
        assert manager.active_connections == 1


class TestConnectionManagerTraceEvents:
    """Tests for trace event broadcasting."""

    @pytest.mark.asyncio
    async def test_broadcast_sends_trace_events_to_all_clients(
        self, manager, mock_websocket
    ) -> None:
        """broadcast() sends trace events to all connected clients (no filtering)."""
        # Create a second mock websocket for this test
        mock_ws2 = AsyncMock()
        mock_ws2.accept = AsyncMock()
        mock_ws2.send_json = AsyncMock()

        await manager.connect(mock_websocket)
        await manager.connect(mock_ws2)

        # Subscribe to different workflows - normally only matching events go through
        await manager.subscribe(mock_websocket, "wf-1")
        await manager.subscribe(mock_ws2, "wf-2")

        trace_event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.CLAUDE_TOOL_CALL,
            level=EventLevel.DEBUG,
            message="Tool call",
        )

        await manager.broadcast(trace_event)

        # Both clients receive trace events (no workflow filtering)
        assert mock_websocket.send_json.called
        assert mock_ws2.send_json.called


class TestBroadcastDomainRouting:
    """Tests for domain-based broadcast routing."""

    @pytest.mark.asyncio
    async def test_broadcast_workflow_event_uses_event_wrapper(
        self, manager, mock_websocket
    ):
        """Workflow domain events are sent as {type: 'event', payload: ...}."""
        await manager.connect(mock_websocket)
        await manager.subscribe_all(mock_websocket)

        event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
            domain=EventDomain.WORKFLOW,
        )

        await manager.broadcast(event)

        mock_websocket.send_json.assert_called_once()
        payload = mock_websocket.send_json.call_args[0][0]
        assert payload["type"] == "event"
        assert "payload" in payload
        assert payload["payload"]["id"] == "evt-1"

    @pytest.mark.asyncio
    async def test_broadcast_brainstorm_event_uses_brainstorm_wrapper(
        self, manager, mock_websocket
    ):
        """Brainstorm domain events are sent as {type: 'brainstorm', ...}."""
        await manager.connect(mock_websocket)
        await manager.subscribe_all(mock_websocket)

        event = WorkflowEvent(
            id="evt-2",
            workflow_id="session-1",
            sequence=0,
            timestamp=datetime.now(UTC),
            agent="brainstormer",
            event_type=EventType.BRAINSTORM_TEXT,
            message="Streaming",
            domain=EventDomain.BRAINSTORM,
            data={"session_id": "session-1", "message_id": "msg-1", "text": "Hello"},
        )

        await manager.broadcast(event)

        mock_websocket.send_json.assert_called_once()
        payload = mock_websocket.send_json.call_args[0][0]
        assert payload["type"] == "brainstorm"
        assert payload["event_type"] == "text"  # brainstorm_ prefix stripped
        assert payload["session_id"] == "session-1"
        assert payload["message_id"] == "msg-1"
        assert payload["data"]["text"] == "Hello"
        assert "timestamp" in payload
