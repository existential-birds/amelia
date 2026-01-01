"""Tests for ConnectionManager stream event broadcasting."""

from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect

from amelia.core.types import StreamEvent, StreamEventType
from amelia.server.events.connection_manager import ConnectionManager


class TestConnectionManagerStream:
    """Tests for ConnectionManager stream event broadcasting."""

    @pytest.fixture
    def manager(self) -> ConnectionManager:
        """Create ConnectionManager instance."""
        return ConnectionManager()

    @pytest.fixture
    def websocket_factory(self) -> Callable[[], AsyncMock]:
        """Factory for creating mock WebSocket instances."""
        def _create() -> AsyncMock:
            ws = AsyncMock()
            ws.accept = AsyncMock()
            ws.send_json = AsyncMock()
            ws.close = AsyncMock()
            return ws
        return _create

    async def test_broadcast_stream_sends_to_all_connections(
        self, manager, websocket_factory, sample_stream_event
    ) -> None:
        """broadcast_stream() should send to all connections regardless of subscription."""
        ws1 = websocket_factory()
        ws2 = websocket_factory()

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
        self, manager, websocket_factory, sample_stream_event
    ) -> None:
        """broadcast_stream() should send correct payload structure with subtype."""
        mock_websocket = websocket_factory()
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
        assert stream_payload["subtype"] == StreamEventType.CLAUDE_THINKING.value
        assert stream_payload["content"] == "Analyzing requirements"
        assert stream_payload["agent"] == "developer"
        assert stream_payload["workflow_id"] == "wf-123"
        assert isinstance(stream_payload["timestamp"], str)  # JSON serialization

    async def test_broadcast_stream_handles_disconnected_socket(
        self, manager, websocket_factory, sample_stream_event
    ) -> None:
        """broadcast_stream() should remove disconnected sockets gracefully."""
        mock_websocket = websocket_factory()
        await manager.connect(mock_websocket)
        mock_websocket.send_json.side_effect = WebSocketDisconnect()

        await manager.broadcast_stream(sample_stream_event)

        # Connection should be removed after disconnect
        assert manager.active_connections == 0

    async def test_broadcast_stream_timeout_handling(
        self, manager, websocket_factory, sample_stream_event
    ) -> None:
        """broadcast_stream() should timeout slow clients and remove them."""
        mock_websocket = websocket_factory()
        await manager.connect(mock_websocket)

        # Simulate timeout by raising TimeoutError immediately
        # This is what asyncio.wait_for raises when timeout expires
        async def timeout_send(*args, **kwargs):
            raise TimeoutError("Simulated send timeout")

        mock_websocket.send_json = timeout_send

        await manager.broadcast_stream(sample_stream_event)

        # Connection should be removed after timeout
        assert manager.active_connections == 0

    async def test_broadcast_stream_with_no_connections(self, manager, sample_stream_event) -> None:
        """broadcast_stream() should handle no connections gracefully."""
        assert manager.active_connections == 0

        # Should not raise
        await manager.broadcast_stream(sample_stream_event)

    async def test_broadcast_stream_concurrent_sends(
        self, manager, websocket_factory, sample_stream_event
    ) -> None:
        """broadcast_stream() should send to multiple clients concurrently."""
        # Create multiple websockets
        websockets = [websocket_factory() for _ in range(5)]
        for ws in websockets:
            await manager.connect(ws)

        # Broadcast stream event
        await manager.broadcast_stream(sample_stream_event)

        # All should have been called
        for ws in websockets:
            ws.send_json.assert_awaited_once()

    async def test_broadcast_stream_serializes_datetime(
        self, manager, websocket_factory
    ) -> None:
        """broadcast_stream() should serialize datetime to ISO string."""
        mock_websocket = websocket_factory()
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
        self, manager, websocket_factory
    ) -> None:
        """broadcast_stream() should include tool data when present."""
        mock_websocket = websocket_factory()
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
        assert stream_payload["subtype"] == StreamEventType.CLAUDE_TOOL_RESULT.value
        assert stream_payload["tool_name"] == "execute_shell"
        assert stream_payload["tool_input"] == {"command": "ls -la", "timeout": 30}

    async def test_broadcast_stream_partial_failure(
        self, manager, websocket_factory, sample_stream_event
    ) -> None:
        """broadcast_stream() should continue if some clients fail."""
        # Create three websockets
        ws1 = websocket_factory()
        ws2 = websocket_factory()
        ws2.send_json = AsyncMock(side_effect=WebSocketDisconnect())  # Fails
        ws3 = websocket_factory()

        await manager.connect(ws1)
        await manager.connect(ws2)
        await manager.connect(ws3)

        await manager.broadcast_stream(sample_stream_event)

        # ws1 and ws3 should have received the event
        ws1.send_json.assert_awaited_once()
        ws3.send_json.assert_awaited_once()

        # ws2 should be disconnected
        assert manager.active_connections == 2
