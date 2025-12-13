# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for ConnectionManager stream event broadcasting."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect

from amelia.core.types import StreamEvent, StreamEventType
from amelia.server.events.connection_manager import ConnectionManager


class TestConnectionManagerStream:
    """Tests for ConnectionManager stream event broadcasting."""

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

    @pytest.fixture
    def sample_stream_event(self) -> StreamEvent:
        """Create sample stream event."""
        return StreamEvent(
            type=StreamEventType.CLAUDE_THINKING,
            content="Analyzing requirements",
            timestamp=datetime.now(UTC),
            agent="developer",
            workflow_id="wf-123",
        )

    async def test_broadcast_stream_sends_to_all_connections(
        self, manager, mock_websocket, sample_stream_event
    ):
        """broadcast_stream() should send to all connections regardless of subscription."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_json = AsyncMock()

        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()

        # Connect both sockets
        await manager.connect(ws1)
        await manager.connect(ws2)

        # Subscribe ws1 to specific workflow
        await manager.subscribe(ws1, "wf-999")

        # Broadcast stream event (different workflow)
        await manager.broadcast_stream(sample_stream_event)

        # Both should receive the stream event (no filtering by workflow)
        ws1.send_json.assert_awaited_once()
        ws2.send_json.assert_awaited_once()

        # Verify payload structure
        call_args = ws1.send_json.call_args[0][0]
        assert call_args["type"] == "stream"
        assert "payload" in call_args
        assert call_args["payload"]["agent"] == "developer"
        assert call_args["payload"]["workflow_id"] == "wf-123"

    async def test_broadcast_stream_payload_structure(
        self, manager, mock_websocket, sample_stream_event
    ):
        """broadcast_stream() should send correct payload structure with subtype."""
        await manager.connect(mock_websocket)

        await manager.broadcast_stream(sample_stream_event)

        mock_websocket.send_json.assert_awaited_once()
        payload = mock_websocket.send_json.call_args[0][0]

        # Verify top-level structure
        assert payload["type"] == "stream"
        assert "payload" in payload

        # Verify StreamEventPayload uses subtype (not type)
        stream_payload = payload["payload"]
        assert "type" not in stream_payload, "Should use 'subtype' not 'type'"
        assert stream_payload["subtype"] == "claude_thinking"
        assert stream_payload["content"] == "Analyzing requirements"
        assert stream_payload["agent"] == "developer"
        assert stream_payload["workflow_id"] == "wf-123"
        assert isinstance(stream_payload["timestamp"], str)  # JSON serialization

    async def test_broadcast_stream_handles_disconnected_socket(
        self, manager, mock_websocket, sample_stream_event
    ):
        """broadcast_stream() should remove disconnected sockets gracefully."""
        await manager.connect(mock_websocket)
        mock_websocket.send_json.side_effect = WebSocketDisconnect()

        await manager.broadcast_stream(sample_stream_event)

        # Connection should be removed after disconnect
        assert manager.active_connections == 0

    async def test_broadcast_stream_timeout_handling(
        self, manager, mock_websocket, sample_stream_event
    ):
        """broadcast_stream() should timeout slow clients and remove them."""
        await manager.connect(mock_websocket)

        # Simulate slow client that times out
        async def slow_send(*args, **kwargs):
            import asyncio

            await asyncio.sleep(10)  # Longer than 5s timeout

        mock_websocket.send_json = slow_send

        await manager.broadcast_stream(sample_stream_event)

        # Connection should be removed after timeout
        assert manager.active_connections == 0

    async def test_broadcast_stream_with_no_connections(self, manager, sample_stream_event):
        """broadcast_stream() should handle no connections gracefully."""
        assert manager.active_connections == 0

        # Should not raise
        await manager.broadcast_stream(sample_stream_event)

    async def test_broadcast_stream_concurrent_sends(
        self, manager, sample_stream_event
    ):
        """broadcast_stream() should send to multiple clients concurrently."""
        # Create multiple websockets
        websockets = []
        for _ in range(5):
            ws = AsyncMock()
            ws.accept = AsyncMock()
            ws.send_json = AsyncMock()
            websockets.append(ws)
            await manager.connect(ws)

        # Broadcast stream event
        await manager.broadcast_stream(sample_stream_event)

        # All should have been called
        for ws in websockets:
            ws.send_json.assert_awaited_once()

    async def test_broadcast_stream_serializes_datetime(
        self, manager, mock_websocket
    ):
        """broadcast_stream() should serialize datetime to ISO string."""
        timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        event = StreamEvent(
            type=StreamEventType.CLAUDE_TOOL_CALL,
            content="calling tool",
            timestamp=timestamp,
            agent="reviewer",
            workflow_id="wf-456",
            tool_name="read_file",
            tool_input={"path": "/foo/bar.py"},
        )

        await manager.connect(mock_websocket)
        await manager.broadcast_stream(event)

        payload = mock_websocket.send_json.call_args[0][0]
        stream_payload = payload["payload"]

        # Timestamp should be serialized as string
        assert isinstance(stream_payload["timestamp"], str)
        assert "2025-01-15T10:30:00" in stream_payload["timestamp"]

    async def test_broadcast_stream_with_tool_data(
        self, manager, mock_websocket
    ):
        """broadcast_stream() should include tool data when present."""
        event = StreamEvent(
            type=StreamEventType.CLAUDE_TOOL_RESULT,
            content="file contents",
            timestamp=datetime.now(UTC),
            agent="architect",
            workflow_id="wf-789",
            tool_name="execute_shell",
            tool_input={"command": "ls -la", "timeout": 30},
        )

        await manager.connect(mock_websocket)
        await manager.broadcast_stream(event)

        payload = mock_websocket.send_json.call_args[0][0]
        stream_payload = payload["payload"]

        # Verify subtype is used (not type)
        assert stream_payload["subtype"] == "claude_tool_result"
        assert stream_payload["tool_name"] == "execute_shell"
        assert stream_payload["tool_input"] == {"command": "ls -la", "timeout": 30}

    async def test_broadcast_stream_partial_failure(self, manager, sample_stream_event):
        """broadcast_stream() should continue if some clients fail."""
        # Create three websockets
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_json = AsyncMock()

        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock(side_effect=WebSocketDisconnect())  # Fails

        ws3 = AsyncMock()
        ws3.accept = AsyncMock()
        ws3.send_json = AsyncMock()

        await manager.connect(ws1)
        await manager.connect(ws2)
        await manager.connect(ws3)

        await manager.broadcast_stream(sample_stream_event)

        # ws1 and ws3 should have received the event
        ws1.send_json.assert_awaited_once()
        ws3.send_json.assert_awaited_once()

        # ws2 should be disconnected
        assert manager.active_connections == 2
