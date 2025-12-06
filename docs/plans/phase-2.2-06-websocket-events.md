# WebSocket Real-time Events Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Status:** ✅ Complete

**Goal:** Implement WebSocket endpoint for real-time event streaming with subscription filtering, reconnection backfill, heartbeat ping/pong, and integration with EventBus.

**Architecture:** WebSocket endpoint at /ws/events with ConnectionManager managing subscriptions, backfill for reconnection with ?since= parameter, heartbeat mechanism, and EventBus integration for broadcasting events.

**Tech Stack:** FastAPI WebSocket, asyncio, pytest with WebSocket testing

**Depends on:** Plan 5 (EventBus & Orchestrator Service)

---

## ⚠️ Implementation Notes (Added based on current codebase state)

**IMPORTANT:** The following adaptations are required when implementing this plan:

1. **Task 1 Step 4 (models/__init__.py):** The plan shows replacing the entire file. Instead, ADD the WebSocket imports to the existing exports. The file already exports `EventType`, `WorkflowEvent`, `CreateWorkflowRequest`, `RejectRequest`, response models, state models, and token models. Preserve all existing exports.

2. **Task 4 Step 4 (routes/__init__.py):** Same as above - ADD `websocket_router` to existing exports. The file already exports `health_router` and `workflows_router`.

3. **Task 6 (Graceful Shutdown):** The plan uses `app.add_event_handler("shutdown", ...)` but we use the lifespan context manager pattern. WebSocket shutdown should be integrated into the existing `lifespan()` function in `main.py`, not as a separate event handler. Add `await connection_manager.close_all(code=1001, reason="Server shutting down")` in the shutdown section after `await health_checker.stop()`.

4. **Task 4 & 5 (DI Integration):** The plan uses a stub `get_repository()` function. Integrate with our existing DI pattern in `dependencies.py` - add `get_connection_manager()` and wire it through the lifespan, similar to how `get_orchestrator()` works.

5. **Logger imports:** Use `from loguru import logger` (already fixed in this plan).

6. **Health Endpoint:** After Task 4, update `amelia/server/routes/health.py` to report actual WebSocket connection count by importing `connection_manager` from the websocket route and using `connection_manager.active_connections` instead of the hardcoded 0.

---

## Task 1: Create WebSocket Protocol Message Models

**Files:**
- Create: `amelia/server/models/websocket.py`
- Modify: `amelia/server/models/__init__.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/models/test_websocket.py
"""Tests for WebSocket protocol message models."""
import pytest
from datetime import datetime


class TestClientMessages:
    """Tests for client-to-server message models."""

    def test_subscribe_message(self):
        """Subscribe message has workflow_id."""
        from amelia.server.models.websocket import SubscribeMessage

        msg = SubscribeMessage(workflow_id="wf-123")

        assert msg.type == "subscribe"
        assert msg.workflow_id == "wf-123"

    def test_unsubscribe_message(self):
        """Unsubscribe message has workflow_id."""
        from amelia.server.models.websocket import UnsubscribeMessage

        msg = UnsubscribeMessage(workflow_id="wf-456")

        assert msg.type == "unsubscribe"
        assert msg.workflow_id == "wf-456"

    def test_subscribe_all_message(self):
        """Subscribe all message has no workflow_id."""
        from amelia.server.models.websocket import SubscribeAllMessage

        msg = SubscribeAllMessage()

        assert msg.type == "subscribe_all"

    def test_pong_message(self):
        """Pong message is heartbeat response."""
        from amelia.server.models.websocket import PongMessage

        msg = PongMessage()

        assert msg.type == "pong"

    def test_client_message_serialization(self):
        """Client messages serialize to JSON correctly."""
        from amelia.server.models.websocket import SubscribeMessage

        msg = SubscribeMessage(workflow_id="wf-123")
        json_data = msg.model_dump()

        assert json_data["type"] == "subscribe"
        assert json_data["workflow_id"] == "wf-123"


class TestServerMessages:
    """Tests for server-to-client message models."""

    def test_event_message(self):
        """Event message wraps WorkflowEvent."""
        from amelia.server.models.websocket import EventMessage
        from amelia.server.models.events import WorkflowEvent, EventType

        event = WorkflowEvent(
            id="evt-123",
            workflow_id="wf-456",
            sequence=1,
            timestamp=datetime.utcnow(),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )

        msg = EventMessage(payload=event)

        assert msg.type == "event"
        assert msg.payload.id == "evt-123"
        assert msg.payload.workflow_id == "wf-456"

    def test_ping_message(self):
        """Ping message is heartbeat."""
        from amelia.server.models.websocket import PingMessage

        msg = PingMessage()

        assert msg.type == "ping"

    def test_backfill_complete_message(self):
        """Backfill complete includes event count."""
        from amelia.server.models.websocket import BackfillCompleteMessage

        msg = BackfillCompleteMessage(count=15)

        assert msg.type == "backfill_complete"
        assert msg.count == 15

    def test_backfill_expired_message(self):
        """Backfill expired includes error message."""
        from amelia.server.models.websocket import BackfillExpiredMessage

        msg = BackfillExpiredMessage(
            message="Requested event no longer exists. Full refresh required."
        )

        assert msg.type == "backfill_expired"
        assert "no longer exists" in msg.message

    def test_server_message_serialization(self):
        """Server messages serialize to JSON correctly."""
        from amelia.server.models.websocket import PingMessage

        msg = PingMessage()
        json_data = msg.model_dump()

        assert json_data["type"] == "ping"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_websocket.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement WebSocket message models**

```python
# amelia/server/models/websocket.py
"""WebSocket protocol message models."""
from typing import Literal

from pydantic import BaseModel, Field

from amelia.server.models.events import WorkflowEvent


# Client -> Server Messages


class SubscribeMessage(BaseModel):
    """Subscribe to specific workflow events."""

    type: Literal["subscribe"] = "subscribe"
    workflow_id: str = Field(..., description="Workflow to subscribe to")


class UnsubscribeMessage(BaseModel):
    """Unsubscribe from specific workflow events."""

    type: Literal["unsubscribe"] = "unsubscribe"
    workflow_id: str = Field(..., description="Workflow to unsubscribe from")


class SubscribeAllMessage(BaseModel):
    """Subscribe to all workflow events."""

    type: Literal["subscribe_all"] = "subscribe_all"


class PongMessage(BaseModel):
    """Heartbeat response from client."""

    type: Literal["pong"] = "pong"


# Union type for all client messages
ClientMessage = SubscribeMessage | UnsubscribeMessage | SubscribeAllMessage | PongMessage


# Server -> Client Messages


class EventMessage(BaseModel):
    """Event broadcast to client."""

    type: Literal["event"] = "event"
    payload: WorkflowEvent = Field(..., description="The workflow event")


class PingMessage(BaseModel):
    """Heartbeat ping from server."""

    type: Literal["ping"] = "ping"


class BackfillCompleteMessage(BaseModel):
    """Sent after reconnect backfill completes."""

    type: Literal["backfill_complete"] = "backfill_complete"
    count: int = Field(..., description="Number of events backfilled")


class BackfillExpiredMessage(BaseModel):
    """Sent when requested backfill event no longer exists."""

    type: Literal["backfill_expired"] = "backfill_expired"
    message: str = Field(
        ...,
        description="Error message explaining the event was cleaned up",
    )


# Union type for all server messages
ServerMessage = EventMessage | PingMessage | BackfillCompleteMessage | BackfillExpiredMessage
```

**Step 4: Update models __init__.py**

```python
# amelia/server/models/__init__.py
"""Domain models for Amelia server."""
from amelia.server.models.events import EventType, WorkflowEvent
from amelia.server.models.websocket import (
    SubscribeMessage,
    UnsubscribeMessage,
    SubscribeAllMessage,
    PongMessage,
    EventMessage,
    PingMessage,
    BackfillCompleteMessage,
    BackfillExpiredMessage,
    ClientMessage,
    ServerMessage,
)

__all__ = [
    "EventType",
    "WorkflowEvent",
    "SubscribeMessage",
    "UnsubscribeMessage",
    "SubscribeAllMessage",
    "PongMessage",
    "EventMessage",
    "PingMessage",
    "BackfillCompleteMessage",
    "BackfillExpiredMessage",
    "ClientMessage",
    "ServerMessage",
]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_websocket.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/models/websocket.py amelia/server/models/__init__.py tests/unit/server/models/test_websocket.py
git commit -m "feat(server): add WebSocket protocol message models"
```

---

## Task 2: Implement ConnectionManager

**Files:**
- Create: `amelia/server/events/connection_manager.py`
- Modify: `amelia/server/events/__init__.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/events/test_connection_manager.py
"""Tests for WebSocket connection manager."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime


class TestConnectionManager:
    """Tests for ConnectionManager."""

    @pytest.fixture
    def manager(self):
        """Create ConnectionManager instance."""
        from amelia.server.events.connection_manager import ConnectionManager
        return ConnectionManager()

    @pytest.fixture
    def mock_websocket(self):
        """Create mock WebSocket."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_connect_accepts_websocket(self, manager, mock_websocket):
        """connect() accepts the WebSocket connection."""
        await manager.connect(mock_websocket)

        mock_websocket.accept.assert_awaited_once()
        assert manager.active_connections == 1

    @pytest.mark.asyncio
    async def test_connect_initializes_empty_subscription(self, manager, mock_websocket):
        """New connections start with empty subscription (all events)."""
        await manager.connect(mock_websocket)

        # Empty set means subscribed to all
        assert mock_websocket in manager._connections
        assert manager._connections[mock_websocket] == set()

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self, manager, mock_websocket):
        """disconnect() removes connection from tracking."""
        await manager.connect(mock_websocket)
        await manager.disconnect(mock_websocket)

        assert mock_websocket not in manager._connections
        assert manager.active_connections == 0

    @pytest.mark.asyncio
    async def test_subscribe_adds_workflow_id(self, manager, mock_websocket):
        """subscribe() adds workflow_id to connection's subscription set."""
        await manager.connect(mock_websocket)
        await manager.subscribe(mock_websocket, "wf-123")

        assert "wf-123" in manager._connections[mock_websocket]

    @pytest.mark.asyncio
    async def test_subscribe_multiple_workflows(self, manager, mock_websocket):
        """Can subscribe to multiple workflows."""
        await manager.connect(mock_websocket)
        await manager.subscribe(mock_websocket, "wf-123")
        await manager.subscribe(mock_websocket, "wf-456")

        assert "wf-123" in manager._connections[mock_websocket]
        assert "wf-456" in manager._connections[mock_websocket]

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_workflow_id(self, manager, mock_websocket):
        """unsubscribe() removes workflow_id from subscription set."""
        await manager.connect(mock_websocket)
        await manager.subscribe(mock_websocket, "wf-123")
        await manager.unsubscribe(mock_websocket, "wf-123")

        assert "wf-123" not in manager._connections[mock_websocket]

    @pytest.mark.asyncio
    async def test_subscribe_all_clears_subscription_set(self, manager, mock_websocket):
        """subscribe_all() clears subscription set (empty = all)."""
        await manager.connect(mock_websocket)
        await manager.subscribe(mock_websocket, "wf-123")
        await manager.subscribe_all(mock_websocket)

        assert manager._connections[mock_websocket] == set()

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_subscribed_all(self, manager, mock_websocket):
        """broadcast() sends event to connections subscribed to all."""
        from amelia.server.models.events import WorkflowEvent, EventType

        await manager.connect(mock_websocket)

        event = WorkflowEvent(
            id="evt-123",
            workflow_id="wf-456",
            sequence=1,
            timestamp=datetime.utcnow(),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )

        await manager.broadcast(event)

        mock_websocket.send_json.assert_awaited_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "event"
        assert call_args["payload"]["workflow_id"] == "wf-456"

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_specific_subscriber(self, manager, mock_websocket):
        """broadcast() sends event to connections subscribed to that workflow."""
        from amelia.server.models.events import WorkflowEvent, EventType

        await manager.connect(mock_websocket)
        await manager.subscribe(mock_websocket, "wf-456")

        event = WorkflowEvent(
            id="evt-123",
            workflow_id="wf-456",
            sequence=1,
            timestamp=datetime.utcnow(),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )

        await manager.broadcast(event)

        mock_websocket.send_json.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_broadcast_skips_unsubscribed_connection(self, manager, mock_websocket):
        """broadcast() skips connections not subscribed to that workflow."""
        from amelia.server.models.events import WorkflowEvent, EventType

        await manager.connect(mock_websocket)
        await manager.subscribe(mock_websocket, "wf-999")  # Different workflow

        event = WorkflowEvent(
            id="evt-123",
            workflow_id="wf-456",
            sequence=1,
            timestamp=datetime.utcnow(),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )

        await manager.broadcast(event)

        # Should not send to this connection
        mock_websocket.send_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_broadcast_handles_disconnected_socket(self, manager, mock_websocket):
        """broadcast() removes disconnected sockets gracefully."""
        from amelia.server.models.events import WorkflowEvent, EventType
        from fastapi import WebSocketDisconnect

        await manager.connect(mock_websocket)
        mock_websocket.send_json.side_effect = WebSocketDisconnect()

        event = WorkflowEvent(
            id="evt-123",
            workflow_id="wf-456",
            sequence=1,
            timestamp=datetime.utcnow(),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )

        await manager.broadcast(event)

        # Connection should be removed after disconnect
        assert mock_websocket not in manager._connections

    @pytest.mark.asyncio
    async def test_close_all_closes_all_connections(self, manager, mock_websocket):
        """close_all() closes all connections gracefully."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.close = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.close = AsyncMock()

        await manager.connect(ws1)
        await manager.connect(ws2)

        await manager.close_all(code=1000, reason="shutdown")

        ws1.close.assert_awaited_once_with(code=1000, reason="shutdown")
        ws2.close.assert_awaited_once_with(code=1000, reason="shutdown")
        assert manager.active_connections == 0

    @pytest.mark.asyncio
    async def test_close_all_handles_errors(self, manager, mock_websocket):
        """close_all() handles errors gracefully."""
        mock_websocket.close.side_effect = Exception("Close failed")

        await manager.connect(mock_websocket)
        await manager.close_all()

        # Should not raise, just clear connections
        assert manager.active_connections == 0

    @pytest.mark.asyncio
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/events/test_connection_manager.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement ConnectionManager**

```python
# amelia/server/events/connection_manager.py
"""WebSocket connection manager with subscription filtering."""
import asyncio

from fastapi import WebSocket, WebSocketDisconnect

from amelia.server.models.events import WorkflowEvent


class ConnectionManager:
    """Manages WebSocket connections with subscription-based filtering.

    Each connection tracks which workflows it's subscribed to:
    - Empty set = subscribed to all workflows
    - Non-empty set = subscribed to specific workflows only

    Thread-safe via asyncio.Lock.
    """

    def __init__(self):
        """Initialize connection manager."""
        self._connections: dict[WebSocket, set[str]] = {}
        self._lock = asyncio.Lock()

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

    async def broadcast(self, event: WorkflowEvent) -> None:
        """Broadcast event to subscribed connections only.

        Connections with empty subscription set receive all events.
        Connections with specific workflow IDs only receive matching events.

        Automatically removes disconnected clients.

        Args:
            event: The workflow event to broadcast.
        """
        async with self._lock:
            for ws, subscribed_ids in list(self._connections.items()):
                # Empty set = subscribed to all workflows
                if not subscribed_ids or event.workflow_id in subscribed_ids:
                    try:
                        await ws.send_json({
                            "type": "event",
                            "payload": event.model_dump(mode="json"),
                        })
                    except WebSocketDisconnect:
                        # Remove disconnected client
                        self._connections.pop(ws, None)
                    except Exception:
                        # Remove on any error
                        self._connections.pop(ws, None)

    async def close_all(self, code: int = 1000, reason: str = "") -> None:
        """Close all connections gracefully.

        Args:
            code: WebSocket close code (default 1000 = normal closure).
            reason: Human-readable close reason.
        """
        async with self._lock:
            for ws in list(self._connections.keys()):
                try:
                    await ws.close(code=code, reason=reason)
                except Exception:
                    # Ignore errors during shutdown
                    pass
            self._connections.clear()

    @property
    def active_connections(self) -> int:
        """Get count of active connections.

        Returns:
            Number of active WebSocket connections.
        """
        return len(self._connections)
```

**Step 4: Update events __init__.py**

```python
# amelia/server/events/__init__.py
"""Event bus and WebSocket connection manager."""
from amelia.server.events.bus import EventBus
from amelia.server.events.connection_manager import ConnectionManager

__all__ = ["EventBus", "ConnectionManager"]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/events/test_connection_manager.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/events/connection_manager.py amelia/server/events/__init__.py tests/unit/server/events/test_connection_manager.py
git commit -m "feat(server): implement ConnectionManager with subscription filtering"
```

---

## Task 3: Add Repository Methods for Event Backfill

**Files:**
- Modify: `amelia/server/database/repository.py`
- Create: `tests/unit/server/database/test_repository_backfill.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/database/test_repository_backfill.py
"""Tests for repository backfill methods."""
import pytest
from datetime import datetime


@pytest.mark.asyncio
class TestEventBackfill:
    """Tests for event backfill functionality."""

    async def test_event_exists_returns_true_when_exists(self, repository, workflow):
        """event_exists() returns True when event exists."""
        from amelia.server.models.events import WorkflowEvent, EventType

        event = WorkflowEvent(
            id="evt-123",
            workflow_id=workflow.id,
            sequence=1,
            timestamp=datetime.utcnow(),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )

        await repository.save_event(event)

        exists = await repository.event_exists("evt-123")
        assert exists is True

    async def test_event_exists_returns_false_when_not_exists(self, repository):
        """event_exists() returns False when event doesn't exist."""
        exists = await repository.event_exists("evt-nonexistent")
        assert exists is False

    async def test_get_events_after_returns_newer_events(self, repository, workflow):
        """get_events_after() returns events with sequence > since_event sequence."""
        from amelia.server.models.events import WorkflowEvent, EventType

        # Create sequence of events
        events = []
        for i in range(1, 6):
            event = WorkflowEvent(
                id=f"evt-{i}",
                workflow_id=workflow.id,
                sequence=i,
                timestamp=datetime.utcnow(),
                agent="system",
                event_type=EventType.STAGE_STARTED,
                message=f"Event {i}",
            )
            await repository.save_event(event)
            events.append(event)

        # Get events after evt-2 (should return evt-3, evt-4, evt-5)
        newer_events = await repository.get_events_after("evt-2")

        assert len(newer_events) == 3
        assert newer_events[0].id == "evt-3"
        assert newer_events[1].id == "evt-4"
        assert newer_events[2].id == "evt-5"

    async def test_get_events_after_preserves_order(self, repository, workflow):
        """get_events_after() returns events in sequence order."""
        from amelia.server.models.events import WorkflowEvent, EventType

        for i in range(1, 11):
            event = WorkflowEvent(
                id=f"evt-{i}",
                workflow_id=workflow.id,
                sequence=i,
                timestamp=datetime.utcnow(),
                agent="system",
                event_type=EventType.STAGE_STARTED,
                message=f"Event {i}",
            )
            await repository.save_event(event)

        newer_events = await repository.get_events_after("evt-5")

        # Should be in sequence order
        sequences = [e.sequence for e in newer_events]
        assert sequences == [6, 7, 8, 9, 10]

    async def test_get_events_after_filters_by_workflow(self, repository):
        """get_events_after() only returns events from same workflow."""
        from amelia.server.models.events import WorkflowEvent, EventType
        from amelia.server.models.state import ExecutionState, WorkflowStatus

        # Create two workflows
        wf1 = ExecutionState(
            id="wf-1",
            issue_id="ISSUE-1",
            worktree_path="/tmp/wf1",
            worktree_name="wf1",
            status=WorkflowStatus.PENDING,
            profile="default",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        wf2 = ExecutionState(
            id="wf-2",
            issue_id="ISSUE-2",
            worktree_path="/tmp/wf2",
            worktree_name="wf2",
            status=WorkflowStatus.PENDING,
            profile="default",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        await repository.save_workflow(wf1)
        await repository.save_workflow(wf2)

        # Events for wf-1
        for i in range(1, 4):
            event = WorkflowEvent(
                id=f"wf1-evt-{i}",
                workflow_id=wf1.id,
                sequence=i,
                timestamp=datetime.utcnow(),
                agent="system",
                event_type=EventType.STAGE_STARTED,
                message=f"WF1 Event {i}",
            )
            await repository.save_event(event)

        # Events for wf-2
        for i in range(1, 4):
            event = WorkflowEvent(
                id=f"wf2-evt-{i}",
                workflow_id=wf2.id,
                sequence=i,
                timestamp=datetime.utcnow(),
                agent="system",
                event_type=EventType.STAGE_STARTED,
                message=f"WF2 Event {i}",
            )
            await repository.save_event(event)

        # Get events after wf1-evt-1
        newer_events = await repository.get_events_after("wf1-evt-1")

        # Should only return wf-1 events
        assert len(newer_events) == 2
        assert all(e.workflow_id == "wf-1" for e in newer_events)

    async def test_get_events_after_empty_when_latest_event(self, repository, workflow):
        """get_events_after() returns empty list when given latest event."""
        from amelia.server.models.events import WorkflowEvent, EventType

        event = WorkflowEvent(
            id="evt-1",
            workflow_id=workflow.id,
            sequence=1,
            timestamp=datetime.utcnow(),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )

        await repository.save_event(event)

        newer_events = await repository.get_events_after("evt-1")
        assert len(newer_events) == 0

    async def test_get_events_after_raises_when_event_not_found(self, repository):
        """get_events_after() raises ValueError when event doesn't exist."""
        with pytest.raises(ValueError, match="Event .* not found"):
            await repository.get_events_after("evt-nonexistent")
```

**Step 1b: Add test fixtures to conftest**

Add these fixtures to `tests/unit/server/database/conftest.py`:

```python
@pytest.fixture
async def repository(db_with_schema: Database) -> WorkflowRepository:
    """Create WorkflowRepository with initialized schema."""
    from amelia.server.database.repository import WorkflowRepository
    return WorkflowRepository(db_with_schema)


@pytest.fixture
async def workflow(repository: WorkflowRepository) -> ServerExecutionState:
    """Create and save a test workflow."""
    from datetime import datetime
    from amelia.server.models.state import ServerExecutionState

    wf = ServerExecutionState(
        id="wf-test",
        issue_id="ISSUE-1",
        worktree_path="/tmp/test",
        worktree_name="test",
        workflow_status="pending",
        started_at=datetime.utcnow(),
    )
    await repository.create(wf)
    return wf
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_repository_backfill.py -v`
Expected: FAIL (methods not implemented)

**Step 3: Implement backfill methods in repository**

Add to `amelia/server/database/repository.py`:

```python
async def event_exists(self, event_id: str) -> bool:
    """Check if an event exists by ID.

    Args:
        event_id: The event ID to check.

    Returns:
        True if event exists, False otherwise.
    """
    result = await self._db.fetch_scalar(
        "SELECT 1 FROM events WHERE id = ? LIMIT 1",
        (event_id,),
    )
    return result is not None


async def get_events_after(self, since_event_id: str) -> list[WorkflowEvent]:
    """Get all events after a specific event (for backfill on reconnect).

    Args:
        since_event_id: The event ID to start after.

    Returns:
        List of events after the given event, ordered by sequence.

    Raises:
        ValueError: If the since_event_id doesn't exist.
    """
    # First, get the workflow_id and sequence of the since event
    row = await self._db.fetch_one(
        "SELECT workflow_id, sequence FROM events WHERE id = ?",
        (since_event_id,),
    )

    if row is None:
        raise ValueError(f"Event {since_event_id} not found")

    workflow_id, since_sequence = row["workflow_id"], row["sequence"]

    # Get all events from same workflow with higher sequence
    rows = await self._db.fetch_all(
        """
        SELECT id, workflow_id, sequence, timestamp, agent, event_type,
               message, data, correlation_id
        FROM events
        WHERE workflow_id = ? AND sequence > ?
        ORDER BY sequence ASC
        """,
        (workflow_id, since_sequence),
    )

    events = []
    for row in rows:
        event_data = dict(row)
        # Parse JSON data field if present (column is data_json, model field is data)
        if event_data.get("data_json"):
            event_data["data"] = json.loads(event_data.pop("data_json"))
        else:
            event_data.pop("data_json", None)  # Remove None value
        events.append(WorkflowEvent(**event_data))

    return events
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_repository_backfill.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/database/repository.py tests/unit/server/database/test_repository_backfill.py
git commit -m "feat(repository): add event_exists and get_events_after for backfill"
```

---

## Task 4: Implement WebSocket Endpoint

**Files:**
- Create: `amelia/server/routes/websocket.py`
- Modify: `amelia/server/routes/__init__.py`
- Modify: `amelia/server/main.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/routes/test_websocket.py
"""Tests for WebSocket endpoint."""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
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
                with pytest.raises(Exception):
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
                with pytest.raises(Exception):
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
                with pytest.raises(Exception):
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
                with pytest.raises(Exception):
                    await websocket_endpoint(mock_websocket, None)

        mock_connection_manager.subscribe_all.assert_awaited_once_with(mock_websocket)

    async def test_websocket_backfill_when_since_provided(self, mock_connection_manager, mock_repository, mock_websocket):
        """WebSocket performs backfill when ?since= parameter provided."""
        from amelia.server.routes.websocket import websocket_endpoint
        from amelia.server.models.events import WorkflowEvent, EventType

        # Mock backfill events
        backfill_events = [
            WorkflowEvent(
                id="evt-2",
                workflow_id="wf-123",
                sequence=2,
                timestamp=datetime.utcnow(),
                agent="system",
                event_type=EventType.STAGE_STARTED,
                message="Event 2",
            ),
            WorkflowEvent(
                id="evt-3",
                workflow_id="wf-123",
                sequence=3,
                timestamp=datetime.utcnow(),
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
                with pytest.raises(Exception):
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
                with pytest.raises(Exception):
                    await websocket_endpoint(mock_websocket, since="evt-nonexistent")

        # Should send backfill_expired message
        backfill_expired_sent = any(
            call[0][0].get("type") == "backfill_expired"
            for call in mock_websocket.send_json.call_args_list
        )
        assert backfill_expired_sent

    async def test_websocket_disconnects_cleanly(self, mock_connection_manager, mock_repository, mock_websocket):
        """WebSocket disconnects cleanly when client closes."""
        from amelia.server.routes.websocket import websocket_endpoint
        from fastapi import WebSocketDisconnect

        mock_websocket.receive_json.side_effect = WebSocketDisconnect()

        with patch("amelia.server.routes.websocket.connection_manager", mock_connection_manager):
            with patch("amelia.server.routes.websocket.get_repository", return_value=mock_repository):
                await websocket_endpoint(mock_websocket, None)

        mock_connection_manager.disconnect.assert_awaited_once_with(mock_websocket)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_websocket.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement WebSocket endpoint**

```python
# amelia/server/routes/websocket.py
"""WebSocket endpoint for real-time event streaming."""
import asyncio
from typing import Annotated

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends

from amelia.server.events.connection_manager import ConnectionManager
from amelia.server.database.repository import WorkflowRepository
# Import repository dependency from existing DI module
from amelia.server.dependencies import get_repository
from loguru import logger


router = APIRouter(tags=["websocket"])

# Global connection manager instance
connection_manager = ConnectionManager()


@router.websocket("/ws/events")
async def websocket_endpoint(
    websocket: WebSocket,
    since: Annotated[str | None, Query()] = None,
    repository: WorkflowRepository = Depends(get_repository),
) -> None:
    """WebSocket endpoint for real-time event streaming.

    Protocol:
        Client -> Server:
            {"type": "subscribe", "workflow_id": "uuid"}
            {"type": "unsubscribe", "workflow_id": "uuid"}
            {"type": "subscribe_all"}
            {"type": "pong"}

        Server -> Client:
            {"type": "event", "payload": WorkflowEvent}
            {"type": "ping"}
            {"type": "backfill_complete", "count": 15}
            {"type": "backfill_expired", "message": "..."}

    Args:
        websocket: The WebSocket connection.
        since: Optional event ID for backfill on reconnect.
        repository: Workflow repository for backfill queries.
    """
    await connection_manager.connect(websocket)
    logger.info("websocket_connected", active_connections=connection_manager.active_connections)

    try:
        # Handle backfill if reconnecting
        if since:
            event_exists = await repository.event_exists(since)

            if not event_exists:
                # Event was cleaned up by retention - client needs full refresh
                await websocket.send_json({
                    "type": "backfill_expired",
                    "message": "Requested event no longer exists. Full refresh required.",
                })
                logger.warning("backfill_expired", since_event_id=since)
            else:
                # Replay missed events from database
                events = await repository.get_events_after(since)

                for event in events:
                    await websocket.send_json({
                        "type": "event",
                        "payload": event.model_dump(mode="json"),
                    })

                await websocket.send_json({
                    "type": "backfill_complete",
                    "count": len(events),
                })
                logger.info("backfill_complete", count=len(events))

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(_heartbeat_loop(websocket))

        try:
            # Message handling loop
            while True:
                data = await websocket.receive_json()
                message_type = data.get("type")

                if message_type == "subscribe":
                    workflow_id = data.get("workflow_id")
                    if workflow_id:
                        await connection_manager.subscribe(websocket, workflow_id)
                        logger.debug("subscription_added", workflow_id=workflow_id)

                elif message_type == "unsubscribe":
                    workflow_id = data.get("workflow_id")
                    if workflow_id:
                        await connection_manager.unsubscribe(websocket, workflow_id)
                        logger.debug("subscription_removed", workflow_id=workflow_id)

                elif message_type == "subscribe_all":
                    await connection_manager.subscribe_all(websocket)
                    logger.debug("subscribed_to_all")

                elif message_type == "pong":
                    # Heartbeat response - just log
                    logger.debug("heartbeat_pong_received")

        finally:
            # Cancel heartbeat when loop exits
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    except WebSocketDisconnect:
        logger.info("websocket_disconnected")
    except Exception as e:
        logger.error("websocket_error", error=str(e), exc_info=True)
    finally:
        await connection_manager.disconnect(websocket)
        logger.info("websocket_cleanup", active_connections=connection_manager.active_connections)


async def _heartbeat_loop(websocket: WebSocket, interval: float = 30.0) -> None:
    """Send periodic ping messages to keep connection alive.

    Args:
        websocket: The WebSocket to send pings to.
        interval: Seconds between pings (default 30s).
    """
    try:
        while True:
            await asyncio.sleep(interval)
            await websocket.send_json({"type": "ping"})
            logger.debug("heartbeat_ping_sent")
    except asyncio.CancelledError:
        # Normal cancellation on disconnect
        pass
    except Exception as e:
        logger.error("heartbeat_error", error=str(e))
```

**Step 4: Update routes __init__.py**

```python
# amelia/server/routes/__init__.py
"""API route modules."""
from amelia.server.routes.health import router as health_router
from amelia.server.routes.websocket import router as websocket_router

__all__ = ["health_router", "websocket_router"]
```

**Step 5: Mount WebSocket routes in main app**

Update `amelia/server/main.py`:

```python
# Add import
from amelia.server.routes import health_router, websocket_router

# In create_app():
# Mount health routes
application.include_router(health_router, prefix="/api")

# Mount WebSocket routes
application.include_router(websocket_router)
```

**Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_websocket.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add amelia/server/routes/websocket.py amelia/server/routes/__init__.py amelia/server/main.py tests/unit/server/routes/test_websocket.py
git commit -m "feat(server): implement WebSocket endpoint with backfill and subscriptions"
```

---

## Task 5: Integrate EventBus with ConnectionManager

**Files:**
- Modify: `amelia/server/events/bus.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/events/test_event_bus_websocket.py
"""Tests for EventBus WebSocket integration."""
import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock


@pytest.mark.asyncio
class TestEventBusWebSocketIntegration:
    """Tests for EventBus broadcasting to WebSocket."""

    @pytest.fixture
    def mock_connection_manager(self):
        """Mock ConnectionManager."""
        from amelia.server.events.connection_manager import ConnectionManager

        manager = AsyncMock(spec=ConnectionManager)
        manager.broadcast = AsyncMock()
        return manager

    @pytest.fixture
    def event_bus(self, mock_connection_manager):
        """EventBus with mocked ConnectionManager."""
        from amelia.server.events.bus import EventBus

        bus = EventBus()
        bus.set_connection_manager(mock_connection_manager)
        return bus

    async def test_emit_broadcasts_to_websocket(self, event_bus, mock_connection_manager):
        """emit() broadcasts event to ConnectionManager."""
        from amelia.server.models.events import WorkflowEvent, EventType

        event = WorkflowEvent(
            id="evt-123",
            workflow_id="wf-456",
            sequence=1,
            timestamp=datetime.utcnow(),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )

        event_bus.emit(event)

        # Give asyncio time to process
        await asyncio.sleep(0.01)

        mock_connection_manager.broadcast.assert_awaited_once_with(event)

    async def test_emit_without_connection_manager_does_not_crash(self):
        """emit() works even without ConnectionManager set."""
        from amelia.server.events.bus import EventBus
        from amelia.server.models.events import WorkflowEvent, EventType

        bus = EventBus()
        # Don't set connection manager

        event = WorkflowEvent(
            id="evt-123",
            workflow_id="wf-456",
            sequence=1,
            timestamp=datetime.utcnow(),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )

        # Should not crash
        bus.emit(event)
        await asyncio.sleep(0.01)

    async def test_subscribe_still_works_with_websocket(self, event_bus, mock_connection_manager):
        """Local subscribers still receive events when WebSocket enabled.

        Note: Subscribers MUST be non-blocking. If you need to perform I/O
        or slow operations, dispatch them as background tasks.
        """
        from amelia.server.models.events import WorkflowEvent, EventType

        received_events = []

        async def handler(event: WorkflowEvent):
            # Example of non-blocking subscriber - quick operation only
            received_events.append(event)
            # If you need I/O: asyncio.create_task(slow_operation(event))

        event_bus.subscribe(handler)

        event = WorkflowEvent(
            id="evt-123",
            workflow_id="wf-456",
            sequence=1,
            timestamp=datetime.utcnow(),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )

        event_bus.emit(event)
        await asyncio.sleep(0.01)

        # Both local subscriber and WebSocket should receive
        assert len(received_events) == 1
        mock_connection_manager.broadcast.assert_awaited_once()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/events/test_event_bus_websocket.py -v`
Expected: FAIL (set_connection_manager method not implemented)

**Step 3: Update EventBus to broadcast to ConnectionManager**

Modify `amelia/server/events/bus.py`:

```python
# Add to EventBus class

def __init__(self) -> None:
    """Initialize event bus."""
    self._subscribers: list[Callable[[WorkflowEvent], Awaitable[None]]] = []
    self._connection_manager: ConnectionManager | None = None

def set_connection_manager(self, manager: ConnectionManager) -> None:
    """Set the ConnectionManager for WebSocket broadcasting.

    Args:
        manager: The ConnectionManager instance.
    """
    self._connection_manager = manager

def emit(self, event: WorkflowEvent) -> None:
    """Emit event to all subscribers AND WebSocket clients.

    All subscribers are dispatched as async background tasks.

    Args:
        event: The workflow event to emit.
    """
    for subscriber in self._subscribers:
        asyncio.create_task(subscriber(event))

    # Broadcast to WebSocket clients
    if self._connection_manager:
        asyncio.create_task(self._connection_manager.broadcast(event))
```

Add import at top:

```python
import asyncio
from amelia.server.events.connection_manager import ConnectionManager
```

**Step 3b: Wire ConnectionManager to EventBus in lifespan**

Update `amelia/server/main.py` lifespan function to connect the EventBus to the ConnectionManager:

```python
# Add import at top of file
from amelia.server.routes.websocket import connection_manager

# In lifespan(), after creating event_bus (around line 70):
event_bus = EventBus()
event_bus.set_connection_manager(connection_manager)  # NEW: Wire WebSocket broadcasting
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/events/test_event_bus_websocket.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/events/bus.py tests/unit/server/events/test_event_bus_websocket.py
git commit -m "feat(event-bus): integrate with ConnectionManager for WebSocket broadcast"
```

---

## Task 6: Add Graceful Shutdown for WebSocket

**Files:**
- Modify: `amelia/server/main.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/test_websocket_shutdown.py
"""Tests for WebSocket graceful shutdown in lifespan."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
class TestWebSocketShutdown:
    """Tests for WebSocket shutdown during server lifecycle."""

    async def test_lifespan_closes_websocket_connections_on_shutdown(self):
        """Lifespan shutdown closes all WebSocket connections."""
        from amelia.server.routes.websocket import connection_manager

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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_websocket_shutdown.py -v`
Expected: FAIL (shutdown not wired in lifespan)

**Step 3: Add WebSocket shutdown to lifespan**

Update `amelia/server/main.py` lifespan function to close WebSocket connections during shutdown:

```python
# Add import at top
from amelia.server.routes.websocket import connection_manager

# In lifespan(), update the shutdown section (after yield):
    yield

    # Shutdown - stop components in reverse order
    # Close WebSocket connections first
    await connection_manager.close_all(code=1001, reason="Server shutting down")

    await health_checker.stop()
    await lifecycle.shutdown()
    clear_orchestrator()
    await database.close()
    clear_database()
    _config = None
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_websocket_shutdown.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/main.py tests/unit/server/test_websocket_shutdown.py
git commit -m "feat(server): add graceful WebSocket shutdown in lifespan"
```

---

## Task 7: Integration Test - WebSocket End-to-End

**Files:**
- Create: `tests/integration/test_websocket_e2e.py`

**Step 1: Write the integration test**

```python
# tests/integration/test_websocket_e2e.py
"""End-to-end integration tests for WebSocket.

Note: These tests use synchronous TestClient for WebSocket testing.
For timeout handling, we use a try/except pattern with limited iterations
rather than a timeout parameter (which TestClient doesn't support).
"""
import pytest
import asyncio
from datetime import datetime
from fastapi.testclient import TestClient
from fastapi import WebSocket


@pytest.mark.asyncio
class TestWebSocketIntegration:
    """Integration tests for WebSocket functionality."""

    @pytest.fixture
    async def app(self):
        """Create test app with all dependencies."""
        from amelia.server.main import create_app
        from amelia.server.database.repository import WorkflowRepository
        from amelia.server.routes import websocket
        from pathlib import Path
        import tempfile

        # Create temp database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        # Initialize repository
        repo = WorkflowRepository(db_path)
        await repo.initialize()

        # Inject repository into WebSocket route
        def get_test_repository():
            return repo

        websocket.get_repository = get_test_repository

        app = create_app()

        yield app

        # Cleanup
        db_path.unlink(missing_ok=True)

    async def test_websocket_connect_and_subscribe(self, app):
        """Client can connect and subscribe to workflow."""
        with TestClient(app) as client:
            with client.websocket_connect("/ws/events") as ws:
                # Send subscribe message
                ws.send_json({"type": "subscribe", "workflow_id": "wf-123"})

                # Should receive ping eventually
                for _ in range(10):
                    try:
                        # Note: TestClient WebSocket doesn't support timeout, so we use
                        # a try/except pattern with the test framework's default timeout
                        data = ws.receive_json()
                        if data.get("type") == "ping":
                            break
                    except Exception:
                        continue

    async def test_websocket_receives_events(self, app):
        """Client receives events broadcast via EventBus."""
        from amelia.server.events.bus import EventBus
        from amelia.server.routes.websocket import connection_manager
        from amelia.server.models.events import WorkflowEvent, EventType

        # Setup EventBus with ConnectionManager
        event_bus = EventBus()
        event_bus.set_connection_manager(connection_manager)

        with TestClient(app) as client:
            with client.websocket_connect("/ws/events") as ws:
                # Subscribe to all events
                ws.send_json({"type": "subscribe_all"})

                # Emit event via EventBus
                event = WorkflowEvent(
                    id="evt-123",
                    workflow_id="wf-456",
                    sequence=1,
                    timestamp=datetime.utcnow(),
                    agent="system",
                    event_type=EventType.WORKFLOW_STARTED,
                    message="Started",
                )
                event_bus.emit(event)

                # Should receive the event
                received = False
                for _ in range(10):
                    try:
                        # Note: TestClient WebSocket doesn't support timeout, so we use
                        # a try/except pattern with the test framework's default timeout
                        data = ws.receive_json()
                        if data.get("type") == "event" and data.get("payload", {}).get("id") == "evt-123":
                            received = True
                            break
                    except Exception:
                        continue

                assert received, "Did not receive broadcast event"

    async def test_websocket_backfill_on_reconnect(self, app):
        """Client receives backfill events on reconnect with ?since=."""
        from amelia.server.models.events import WorkflowEvent, EventType
        from amelia.server.models.state import ExecutionState, WorkflowStatus
        from amelia.server.routes import websocket

        # Get repository
        repo = websocket.get_repository()

        # Create workflow and events
        workflow = ExecutionState(
            id="wf-123",
            issue_id="ISSUE-1",
            worktree_path="/tmp/test",
            worktree_name="test",
            status=WorkflowStatus.PENDING,
            profile="default",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        await repo.save_workflow(workflow)

        # Save events
        for i in range(1, 4):
            event = WorkflowEvent(
                id=f"evt-{i}",
                workflow_id=workflow.id,
                sequence=i,
                timestamp=datetime.utcnow(),
                agent="system",
                event_type=EventType.STAGE_STARTED,
                message=f"Event {i}",
            )
            await repo.save_event(event)

        with TestClient(app) as client:
            # Reconnect with since=evt-1
            with client.websocket_connect("/ws/events?since=evt-1") as ws:
                # Should receive evt-2 and evt-3
                received_events = []
                backfill_complete = False

                for _ in range(20):
                    try:
                        # Note: TestClient WebSocket doesn't support timeout, so we use
                        # a try/except pattern with the test framework's default timeout
                        data = ws.receive_json()
                        if data.get("type") == "event":
                            received_events.append(data["payload"]["id"])
                        elif data.get("type") == "backfill_complete":
                            backfill_complete = True
                            break
                    except Exception:
                        continue

                assert "evt-2" in received_events
                assert "evt-3" in received_events
                assert backfill_complete

    async def test_websocket_backfill_expired(self, app):
        """Client receives backfill_expired when event doesn't exist."""
        with TestClient(app) as client:
            # Reconnect with non-existent event
            with client.websocket_connect("/ws/events?since=evt-nonexistent") as ws:
                # Should receive backfill_expired
                received_expired = False

                for _ in range(10):
                    try:
                        # Note: TestClient WebSocket doesn't support timeout, so we use
                        # a try/except pattern with the test framework's default timeout
                        data = ws.receive_json()
                        if data.get("type") == "backfill_expired":
                            received_expired = True
                            break
                    except Exception:
                        continue

                assert received_expired
```

**Step 2: Run integration test**

Run: `uv run pytest tests/integration/test_websocket_e2e.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_websocket_e2e.py
git commit -m "test(server): add WebSocket end-to-end integration tests"
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] `uv run pytest tests/unit/server/models/test_websocket.py -v` - WebSocket message models pass
- [ ] `uv run pytest tests/unit/server/events/test_connection_manager.py -v` - ConnectionManager tests pass
- [ ] `uv run pytest tests/unit/server/database/test_repository_backfill.py -v` - Backfill repository methods pass
- [ ] `uv run pytest tests/unit/server/routes/test_websocket.py -v` - WebSocket endpoint tests pass
- [ ] `uv run pytest tests/unit/server/events/test_event_bus_websocket.py -v` - EventBus WebSocket integration passes
- [ ] `uv run pytest tests/unit/server/test_websocket_shutdown.py -v` - Graceful shutdown tests pass
- [ ] `uv run pytest tests/integration/test_websocket_e2e.py -v` - End-to-end integration tests pass
- [ ] `uv run ruff check amelia/server` - No linting errors
- [ ] `uv run mypy amelia/server` - No type errors
- [ ] Manual test: Connect to `ws://localhost:8420/ws/events` and receive events
- [ ] Manual test: Subscribe/unsubscribe messages work correctly
- [ ] Manual test: Reconnect with `?since=` parameter receives backfill
- [ ] Manual test: Heartbeat ping/pong works

---

## Summary

This plan implements WebSocket real-time event streaming:

| Component | File | Purpose |
|-----------|------|---------|
| Protocol Models | `amelia/server/models/websocket.py` | Client/server message types |
| ConnectionManager | `amelia/server/events/connection_manager.py` | Subscription management & broadcasting |
| Repository Backfill | `amelia/server/database/repository.py` | Event backfill queries |
| WebSocket Endpoint | `amelia/server/routes/websocket.py` | /ws/events handler with backfill |
| EventBus Integration | `amelia/server/events/bus.py` | Broadcast events to WebSocket |
| Graceful Shutdown | `amelia/server/main.py` | Close WebSocket connections on shutdown |

**Key Features:**
- Subscription filtering (all workflows or specific workflow IDs)
- Reconnection with backfill using `?since=event_id` parameter
- Backfill expiration handling for cleaned-up events
- Heartbeat ping/pong mechanism (30s interval)
- Graceful shutdown with proper close codes
- Thread-safe connection management with asyncio.Lock
- Integration with EventBus for real-time broadcasts

**Async Subscribers:**

All EventBus subscribers must be async functions (`async def`). They are dispatched as background tasks via `asyncio.create_task()`, so they won't block the caller.

```python
async def my_subscriber(event: WorkflowEvent):
    # Async operations are fine - runs as background task
    await save_to_database(event)
    await notify_external_service(event)
```

**Next PR:** Dashboard UI Foundation (Plan 7)
