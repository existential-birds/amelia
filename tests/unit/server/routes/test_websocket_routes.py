"""Tests for WebSocket endpoint."""
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocket


@pytest.mark.asyncio
class TestWebSocketEndpoint:
    """Tests for /ws/events endpoint."""

    @pytest.fixture
    def mock_connection_manager(self):
        """Mock ConnectionManager."""
        from amelia.server.events.connection_manager import ConnectionManager

        manager = AsyncMock(spec=ConnectionManager)
        manager.connect = AsyncMock()
        manager.disconnect = AsyncMock()
        manager.subscribe = AsyncMock()
        manager.unsubscribe = AsyncMock()
        manager.subscribe_all = AsyncMock()
        manager.broadcast = AsyncMock()
        return manager

    @pytest.fixture
    def mock_repository(self):
        """Mock WorkflowRepository."""
        repo = AsyncMock()
        repo.event_exists = AsyncMock(return_value=True)
        repo.get_events_after = AsyncMock(return_value=[])
        return repo

    @pytest.fixture
    def mock_websocket(self):
        """Mock WebSocket."""
        ws = AsyncMock(spec=WebSocket)
        ws.accept = AsyncMock()
        ws.receive_json = AsyncMock()
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()
        return ws

    async def test_websocket_accepts_connection(self, mock_connection_manager, mock_repository, mock_websocket):
        """WebSocket endpoint accepts connection."""
        from amelia.server.routes.websocket import websocket_endpoint

        # Setup websocket to disconnect immediately
        mock_websocket.receive_json.side_effect = Exception("disconnect")

        with patch("amelia.server.routes.websocket.connection_manager", mock_connection_manager):
            with patch("amelia.server.routes.websocket.get_repository", return_value=mock_repository):
                await websocket_endpoint(mock_websocket, None)

        mock_connection_manager.connect.assert_awaited_once_with(mock_websocket)

    async def test_websocket_handles_subscribe_message(self, mock_connection_manager, mock_repository, mock_websocket):
        """WebSocket handles subscribe message."""
        from amelia.server.routes.websocket import websocket_endpoint

        # Return subscribe message then disconnect
        mock_websocket.receive_json.side_effect = [
            {"type": "subscribe", "workflow_id": "wf-123"},
            Exception("disconnect"),
        ]

        with patch("amelia.server.routes.websocket.connection_manager", mock_connection_manager):
            with patch("amelia.server.routes.websocket.get_repository", return_value=mock_repository):
                await websocket_endpoint(mock_websocket, None)

        mock_connection_manager.subscribe.assert_awaited_once_with(mock_websocket, "wf-123")

    async def test_websocket_handles_unsubscribe_message(self, mock_connection_manager, mock_repository, mock_websocket):
        """WebSocket handles unsubscribe message."""
        from amelia.server.routes.websocket import websocket_endpoint

        mock_websocket.receive_json.side_effect = [
            {"type": "unsubscribe", "workflow_id": "wf-456"},
            Exception("disconnect"),
        ]

        with patch("amelia.server.routes.websocket.connection_manager", mock_connection_manager):
            with patch("amelia.server.routes.websocket.get_repository", return_value=mock_repository):
                await websocket_endpoint(mock_websocket, None)

        mock_connection_manager.unsubscribe.assert_awaited_once_with(mock_websocket, "wf-456")

    async def test_websocket_handles_subscribe_all_message(self, mock_connection_manager, mock_repository, mock_websocket):
        """WebSocket handles subscribe_all message."""
        from amelia.server.routes.websocket import websocket_endpoint

        mock_websocket.receive_json.side_effect = [
            {"type": "subscribe_all"},
            Exception("disconnect"),
        ]

        with patch("amelia.server.routes.websocket.connection_manager", mock_connection_manager):
            with patch("amelia.server.routes.websocket.get_repository", return_value=mock_repository):
                await websocket_endpoint(mock_websocket, None)

        mock_connection_manager.subscribe_all.assert_awaited_once_with(mock_websocket)

    async def test_websocket_backfill_when_since_provided(self, mock_connection_manager, mock_repository, mock_websocket):
        """WebSocket performs backfill when ?since= parameter provided."""
        from datetime import UTC

        from amelia.server.models.events import EventType, WorkflowEvent
        from amelia.server.routes.websocket import websocket_endpoint

        # Mock backfill events
        backfill_events = [
            WorkflowEvent(
                id="evt-2",
                workflow_id="wf-123",
                sequence=2,
                timestamp=datetime.now(UTC),
                agent="system",
                event_type=EventType.STAGE_STARTED,
                message="Event 2",
            ),
            WorkflowEvent(
                id="evt-3",
                workflow_id="wf-123",
                sequence=3,
                timestamp=datetime.now(UTC),
                agent="system",
                event_type=EventType.STAGE_COMPLETED,
                message="Event 3",
            ),
        ]

        mock_repository.event_exists.return_value = True
        mock_repository.get_events_after.return_value = backfill_events

        mock_websocket.receive_json.side_effect = Exception("disconnect")

        with patch("amelia.server.routes.websocket.connection_manager", mock_connection_manager):
            with patch("amelia.server.routes.websocket.get_repository", return_value=mock_repository):
                await websocket_endpoint(mock_websocket, since="evt-1")

        # Should check if event exists
        mock_repository.event_exists.assert_awaited_once_with("evt-1")

        # Should get events after evt-1
        mock_repository.get_events_after.assert_awaited_once_with("evt-1")

        # Should send backfilled events
        assert mock_websocket.send_json.call_count >= 2

        # Should send backfill_complete
        backfill_complete_sent = any(
            call[0][0].get("type") == "backfill_complete"
            for call in mock_websocket.send_json.call_args_list
        )
        assert backfill_complete_sent

    async def test_websocket_sends_backfill_expired_when_event_missing(self, mock_connection_manager, mock_repository, mock_websocket):
        """WebSocket sends backfill_expired when requested event doesn't exist."""
        from amelia.server.routes.websocket import websocket_endpoint

        mock_repository.event_exists.return_value = False
        mock_websocket.receive_json.side_effect = Exception("disconnect")

        with patch("amelia.server.routes.websocket.connection_manager", mock_connection_manager):
            with patch("amelia.server.routes.websocket.get_repository", return_value=mock_repository):
                await websocket_endpoint(mock_websocket, since="evt-nonexistent")

        # Should send backfill_expired message
        backfill_expired_sent = any(
            call[0][0].get("type") == "backfill_expired"
            for call in mock_websocket.send_json.call_args_list
        )
        assert backfill_expired_sent

    async def test_websocket_disconnects_cleanly(self, mock_connection_manager, mock_repository, mock_websocket):
        """WebSocket disconnects cleanly when client closes."""
        from fastapi import WebSocketDisconnect

        from amelia.server.routes.websocket import websocket_endpoint

        mock_websocket.receive_json.side_effect = WebSocketDisconnect()

        with patch("amelia.server.routes.websocket.connection_manager", mock_connection_manager):
            with patch("amelia.server.routes.websocket.get_repository", return_value=mock_repository):
                await websocket_endpoint(mock_websocket, None)

        mock_connection_manager.disconnect.assert_awaited_once_with(mock_websocket)
