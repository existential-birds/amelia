# amelia/server/events/connection_manager.py
"""WebSocket connection manager with subscription filtering."""
from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from amelia.server.models.events import EventDomain, EventLevel, WorkflowEvent


if TYPE_CHECKING:
    from amelia.server.database.repository import WorkflowRepository


class ConnectionManager:
    """Manages WebSocket connections with subscription-based filtering.

    Each connection tracks which workflows it's subscribed to:
    - Empty set = subscribed to all workflows
    - Non-empty set = subscribed to specific workflows only

    Thread-safe via asyncio.Lock.

    Attributes:
        _connections: Dict mapping WebSocket to set of subscribed workflow IDs.
        _lock: Async lock for thread-safe connection management.
        _repository: Optional workflow repository for event backfill.
    """

    def __init__(self) -> None:
        """Initialize connection manager."""
        self._connections: dict[WebSocket, set[str]] = {}
        self._lock = asyncio.Lock()
        self._repository: WorkflowRepository | None = None

    def set_repository(self, repository: WorkflowRepository) -> None:
        """Set the workflow repository for event backfill.

        Args:
            repository: WorkflowRepository instance.
        """
        self._repository = repository

    def get_repository(self) -> WorkflowRepository | None:
        """Get the workflow repository.

        Returns:
            The WorkflowRepository instance if set via set_repository(),
            or None if not yet initialized. In normal server operation,
            this is set during lifespan startup.
        """
        return self._repository

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection.

        Args:
            websocket: The WebSocket to connect.
        """
        await websocket.accept()
        async with self._lock:
            # Empty set = subscribed to all workflows
            self._connections[websocket] = set()

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection.

        Args:
            websocket: The WebSocket to disconnect.
        """
        async with self._lock:
            self._connections.pop(websocket, None)

    async def subscribe(self, websocket: WebSocket, workflow_id: str) -> None:
        """Subscribe connection to specific workflow events.

        Args:
            websocket: The WebSocket connection.
            workflow_id: The workflow to subscribe to.
        """
        async with self._lock:
            if websocket in self._connections:
                self._connections[websocket].add(workflow_id)

    async def unsubscribe(self, websocket: WebSocket, workflow_id: str) -> None:
        """Unsubscribe connection from specific workflow events.

        Args:
            websocket: The WebSocket connection.
            workflow_id: The workflow to unsubscribe from.
        """
        async with self._lock:
            if websocket in self._connections:
                self._connections[websocket].discard(workflow_id)

    async def subscribe_all(self, websocket: WebSocket) -> None:
        """Subscribe connection to all workflow events.

        Args:
            websocket: The WebSocket connection.
        """
        async with self._lock:
            if websocket in self._connections:
                # Empty set = subscribed to all
                self._connections[websocket] = set()


    async def _send_to_client(
        self, ws: WebSocket, payload: dict[str, Any], timeout: float = 5.0
    ) -> tuple[WebSocket, bool]:
        """Send payload to a single client with timeout.

        Args:
            ws: The WebSocket connection to send to.
            payload: The JSON-serializable payload to send.
            timeout: Maximum seconds to wait for send (default 5.0).

        Returns:
            Tuple of (websocket, success) where success is True if sent,
            False on disconnect/timeout errors.
        """
        try:
            await asyncio.wait_for(ws.send_json(payload), timeout=timeout)
            return (ws, True)
        except (WebSocketDisconnect, TimeoutError, ConnectionResetError, ConnectionError):
            return (ws, False)

    async def broadcast(self, event: WorkflowEvent) -> None:
        """Broadcast event to connected WebSocket clients.

        For trace-level events: broadcasts to ALL clients (no workflow filtering)
        For other events: broadcasts only to clients subscribed to the workflow

        Sends to all target clients concurrently with a timeout. Slow or hung
        clients are disconnected after timeout to prevent blocking other subscribers.

        Args:
            event: The workflow event to broadcast.
        """
        is_trace = event.level == EventLevel.TRACE

        targets: list[WebSocket] = []
        async with self._lock:
            if is_trace:
                # Trace events go to ALL clients
                targets = list(self._connections.keys())
            else:
                # Regular events filtered by workflow subscription
                for ws, subscribed_ids in self._connections.items():
                    # Empty set = subscribed to all workflows
                    if not subscribed_ids or event.workflow_id in subscribed_ids:
                        targets.append(ws)

        logger.debug(
            "broadcast_targets",
            event_type=event.event_type.value,
            level=event.level.value if event.level else None,
            workflow_id=event.workflow_id,
            target_count=len(targets),
            total_connections=len(self._connections),
        )

        if not targets:
            return

        if event.domain == EventDomain.BRAINSTORM:
            # Brainstorm events use flat format for direct frontend handling
            event_type_str = event.event_type.value
            if event_type_str.startswith("brainstorm_"):
                event_type_str = event_type_str[len("brainstorm_"):]

            payload = {
                "type": "brainstorm",
                "event_type": event_type_str,
                "session_id": event.workflow_id,  # Brainstorm events use workflow_id as session_id
                "message_id": event.data.get("message_id") if event.data else None,
                "data": event.data or {},
                "timestamp": event.timestamp.isoformat(),
            }
        else:
            # Workflow events use wrapped format
            payload = {
                "type": "event",
                "payload": event.model_dump(mode="json"),
            }

        results = await asyncio.gather(
            *(self._send_to_client(ws, payload) for ws in targets)
        )

        # Remove failed connections
        failed = [ws for ws, success in results if not success]
        succeeded = len(targets) - len(failed)
        logger.debug(
            "broadcast_complete",
            event_type=event.event_type.value,
            succeeded=succeeded,
            failed=len(failed),
        )
        if failed:
            async with self._lock:
                for ws in failed:
                    self._connections.pop(ws, None)

    async def close_all(self, code: int = 1000, reason: str = "") -> None:
        """Close all connections gracefully.

        Args:
            code: WebSocket close code (default 1000 = normal closure).
            reason: Human-readable close reason.
        """
        async with self._lock:
            for ws in list(self._connections.keys()):
                with suppress(Exception):
                    # Ignore errors during shutdown
                    await ws.close(code=code, reason=reason)
            self._connections.clear()

    @property
    def active_connections(self) -> int:
        """Get count of active connections.

        Returns:
            Number of active WebSocket connections.
        """
        return len(self._connections)
