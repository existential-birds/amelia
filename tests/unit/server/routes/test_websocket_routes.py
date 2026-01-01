"""Tests for WebSocket endpoint."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocket, WebSocketDisconnect

from amelia.server.events.connection_manager import ConnectionManager
from amelia.server.models.events import EventType, WorkflowEvent
from amelia.server.routes.websocket import websocket_endpoint


class TestWebSocketEndpoint:
    """Tests for /ws/events endpoint."""

    @pytest.fixture
    def mock_repository(self):
        """Mock WorkflowRepository."""
        repo = AsyncMock()
        repo.get_events_after.return_value = []
        return repo

    @pytest.fixture
    def mock_connection_manager(self, mock_repository):
        """Mock ConnectionManager with repository."""
        manager = AsyncMock(spec=ConnectionManager)
        manager.get_repository.return_value = mock_repository
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
        self, mock_connection_manager, mock_repository, mock_websocket, message, expected_method, expected_arg
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

    async def test_websocket_backfill_when_since_provided(self, mock_connection_manager, mock_repository, mock_websocket) -> None:
        """WebSocket performs backfill when ?since= parameter provided."""
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

        mock_repository.get_events_after.return_value = backfill_events

        mock_websocket.receive_json.side_effect = Exception("disconnect")

        with patch("amelia.server.routes.websocket.connection_manager", mock_connection_manager):
            await websocket_endpoint(mock_websocket, since="evt-1")

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

    async def test_websocket_sends_backfill_expired_when_event_missing(self, mock_connection_manager, mock_repository, mock_websocket) -> None:
        """WebSocket sends backfill_expired when requested event doesn't exist."""
        # Simulate event not found - get_events_after raises ValueError
        mock_repository.get_events_after.side_effect = ValueError("Event evt-nonexistent not found")
        mock_websocket.receive_json.side_effect = Exception("disconnect")

        with patch("amelia.server.routes.websocket.connection_manager", mock_connection_manager):
            await websocket_endpoint(mock_websocket, since="evt-nonexistent")

        # Should send backfill_expired message
        backfill_expired_sent = any(
            call[0][0].get("type") == "backfill_expired"
            for call in mock_websocket.send_json.call_args_list
        )
        assert backfill_expired_sent
