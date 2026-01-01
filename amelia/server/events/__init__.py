"""Event bus and WebSocket connection manager.

Provide pub/sub infrastructure for real-time event streaming. The event bus
broadcasts workflow events to subscribers, while the connection manager
handles WebSocket lifecycle and message routing.

Exports:
    EventBus: Pub/sub event bus for workflow events.
    ConnectionManager: WebSocket connection lifecycle manager.
"""

from amelia.server.events.bus import EventBus
from amelia.server.events.connection_manager import ConnectionManager


__all__ = ["EventBus", "ConnectionManager"]
