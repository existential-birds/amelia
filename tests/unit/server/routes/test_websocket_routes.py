"""Tests for WebSocket endpoint."""
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import WebSocket, WebSocketDisconnect

from amelia.server.events.bus import EventBus
from amelia.server.events.connection_manager import ConnectionManager
from amelia.server.routes.websocket import websocket_endpoint


class TestWebSocketEndpoint:
    """Tests for /ws/events endpoint."""

    @pytest.fixture
    def mock_connection_manager(self, event_bus):
        """Mock ConnectionManager wired to a real EventBus."""
        manager = AsyncMock(spec=ConnectionManager)
        manager.get_event_bus.return_value = event_bus
        return manager

    @pytest.fixture
    def mock_websocket(self):
        """Mock WebSocket."""
        return AsyncMock(spec=WebSocket)

    @pytest.mark.parametrize(
        "message,expected_method,expected_arg",
        [
            ({"type": "subscribe", "workflow_id": "wf-123"}, "subscribe", "wf-123"),
            ({"type": "unsubscribe", "workflow_id": "wf-456"}, "unsubscribe", "wf-456"),
            ({"type": "subscribe_all"}, "subscribe_all", None),
        ],
        ids=["subscribe", "unsubscribe", "subscribe_all"],
    )
    async def test_websocket_handles_client_messages(
        self, mock_connection_manager, mock_websocket, message, expected_method, expected_arg
    ) -> None:
        """WebSocket routes client messages to connection manager."""
        mock_websocket.receive_json.side_effect = [message, WebSocketDisconnect()]

        with patch("amelia.server.routes.websocket.connection_manager", mock_connection_manager):
            await websocket_endpoint(mock_websocket, None)

        method = getattr(mock_connection_manager, expected_method)
        if expected_arg:
            method.assert_awaited_once_with(mock_websocket, expected_arg)
        else:
            method.assert_awaited_once_with(mock_websocket)

    async def test_websocket_backfill_when_since_provided(
        self, mock_connection_manager, event_bus: EventBus, mock_websocket, event_factory
    ) -> None:
        """WebSocket replays buffered events after ?since= on reconnect."""
        e1 = event_factory(id=uuid4(), sequence=1, message="Event 1")
        e2 = event_factory(id=uuid4(), sequence=2, message="Event 2")
        e3 = event_factory(id=uuid4(), sequence=3, message="Event 3")
        for event in (e1, e2, e3):
            event_bus.emit(event)

        mock_websocket.receive_json.side_effect = Exception("disconnect")

        with patch("amelia.server.routes.websocket.connection_manager", mock_connection_manager):
            await websocket_endpoint(mock_websocket, since=str(e1.id))

        sent = [call.args[0] for call in mock_websocket.send_json.call_args_list]
        event_payloads = [msg["payload"] for msg in sent if msg.get("type") == "event"]
        assert [p["id"] for p in event_payloads] == [str(e2.id), str(e3.id)]
        assert {"type": "backfill_complete", "count": 2} in sent

    async def test_websocket_backfill_empty_when_id_not_in_buffer(
        self, mock_connection_manager, event_bus: EventBus, mock_websocket, event_factory
    ) -> None:
        """Unknown/evicted since id yields an empty backfill (client refetches via GET)."""
        event_bus.emit(event_factory(id=uuid4(), sequence=1))
        mock_websocket.receive_json.side_effect = Exception("disconnect")

        with patch("amelia.server.routes.websocket.connection_manager", mock_connection_manager):
            await websocket_endpoint(mock_websocket, since=str(uuid4()))

        sent = [call.args[0] for call in mock_websocket.send_json.call_args_list]
        assert not any(msg.get("type") == "event" for msg in sent)
        assert {"type": "backfill_complete", "count": 0} in sent

    async def test_websocket_sends_backfill_expired_on_malformed_since(
        self, mock_connection_manager, mock_websocket
    ) -> None:
        """WebSocket sends backfill_expired when ?since= is not a valid UUID."""
        mock_websocket.receive_json.side_effect = Exception("disconnect")

        with patch("amelia.server.routes.websocket.connection_manager", mock_connection_manager):
            await websocket_endpoint(mock_websocket, since="not-a-uuid")

        backfill_expired_sent = any(
            call.args[0].get("type") == "backfill_expired"
            for call in mock_websocket.send_json.call_args_list
        )
        assert backfill_expired_sent
