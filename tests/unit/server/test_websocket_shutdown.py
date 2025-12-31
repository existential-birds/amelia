"""Tests for WebSocket graceful shutdown in lifespan."""
from unittest.mock import AsyncMock

from amelia.server.events.connection_manager import ConnectionManager


class TestWebSocketShutdown:
    """Tests for WebSocket shutdown during server lifecycle."""

    async def test_lifespan_closes_websocket_connections_on_shutdown(self):
        """Lifespan shutdown closes all WebSocket connections."""
        # Create a connection manager instance for testing
        connection_manager = ConnectionManager()

        # Add mock connections
        mock_ws1 = AsyncMock()
        mock_ws1.accept = AsyncMock()
        mock_ws1.close = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws2.accept = AsyncMock()
        mock_ws2.close = AsyncMock()

        await connection_manager.connect(mock_ws1)
        await connection_manager.connect(mock_ws2)

        assert connection_manager.active_connections == 2

        # Simulate shutdown
        await connection_manager.close_all(code=1001, reason="Server shutting down")

        mock_ws1.close.assert_awaited_once_with(code=1001, reason="Server shutting down")
        mock_ws2.close.assert_awaited_once_with(code=1001, reason="Server shutting down")
        assert connection_manager.active_connections == 0
