# tests/unit/server/events/test_connection_manager.py
"""Tests for WebSocket connection manager."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect

from amelia.server.events.connection_manager import ConnectionManager


class TestConnectionManager:
    """Tests for ConnectionManager."""

    @pytest.fixture
    def manager(self):
        """Create ConnectionManager instance."""
        return ConnectionManager()

    @pytest.fixture
    def mock_websocket(self):
        """Create mock WebSocket."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()
        return ws

    async def test_disconnect_removes_connection(self, manager, mock_websocket):
        """disconnect() removes connection from tracking."""
        await manager.connect(mock_websocket)
        await manager.disconnect(mock_websocket)

        assert manager.active_connections == 0

    async def test_subscribe_multiple_workflows(self, manager, mock_websocket):
        """Can subscribe to multiple workflows."""
        await manager.connect(mock_websocket)
        await manager.subscribe(mock_websocket, "wf-123")
        await manager.subscribe(mock_websocket, "wf-456")

        assert "wf-123" in manager._connections[mock_websocket]
        assert "wf-456" in manager._connections[mock_websocket]

    async def test_subscribe_all_clears_subscription_set(self, manager, mock_websocket):
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
    ):
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

    async def test_broadcast_handles_disconnected_socket(self, manager, mock_websocket, make_event):
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

    async def test_close_all_handles_errors(self, manager, mock_websocket):
        """close_all() handles errors gracefully."""
        mock_websocket.close.side_effect = Exception("Close failed")

        await manager.connect(mock_websocket)
        await manager.close_all()

        # Should not raise, just clear connections
        assert manager.active_connections == 0

    async def test_active_connections_count(self, manager):
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
