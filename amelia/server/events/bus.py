"""Event bus implementation for pub/sub workflow events."""
import asyncio
import contextlib
from collections import deque
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from loguru import logger

from amelia.server.models import WorkflowEvent


if TYPE_CHECKING:
    from amelia.server.events.connection_manager import ConnectionManager


class EventBus:
    """Simple synchronous pub/sub event bus for workflow events.

    Allows components to subscribe to and emit workflow events.
    Exceptions in subscribers are logged but don't prevent other
    subscribers from receiving events.

    Keeps a bounded in-memory ring buffer of the most recent events
    for WebSocket reconnect backfill (see events_after()).

    Warning:
        All subscribers MUST be non-blocking. Since emit() runs
        synchronously in the caller's context, blocking operations
        in subscribers will halt the orchestrator.

    """

    def __init__(self, buffer_size: int = 10_000) -> None:
        self._subscribers: list[Callable[[WorkflowEvent], None]] = []
        self._connection_manager: ConnectionManager | None = None
        self._broadcast_tasks: set[asyncio.Task[None]] = set()
        self._buffer: deque[WorkflowEvent] = deque(maxlen=buffer_size)

    def subscribe(self, callback: Callable[[WorkflowEvent], None]) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[WorkflowEvent], None]) -> None:
        with contextlib.suppress(ValueError):
            self._subscribers.remove(callback)

    def set_connection_manager(self, manager: "ConnectionManager") -> None:
        self._connection_manager = manager

    def _handle_broadcast_done(self, task: asyncio.Task[None]) -> None:
        """Handle completion of WebSocket broadcast task.

        Removes completed task from tracking set and logs any exceptions
        that occurred during broadcast.

        Args:
            task: The completed asyncio broadcast task.
        """
        self._broadcast_tasks.discard(task)
        if not task.cancelled():
            exc = task.exception()
            if exc is not None:
                logger.error(
                    "WebSocket broadcast failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

    def emit(self, event: WorkflowEvent) -> None:
        """Emit event to subscribers and broadcast to WebSocket clients.

        All events are sent to both subscribers (for persistence filtering)
        and WebSocket clients (for real-time UI updates).

        Args:
            event: The workflow event to broadcast.
        """
        self._buffer.append(event)

        for callback in self._subscribers:
            try:
                callback(event)
            except Exception as exc:
                callback_name = getattr(callback, "__name__", repr(callback))
                logger.exception(
                    "Subscriber raised exception",
                    callback=callback_name,
                    event_type=event.event_type,
                    error=str(exc),
                )

        if self._connection_manager:
            task = asyncio.create_task(self._connection_manager.broadcast(event))
            self._broadcast_tasks.add(task)
            task.add_done_callback(self._handle_broadcast_done)

    def events_after(self, event_id: UUID) -> list[WorkflowEvent] | None:
        """Return buffered events emitted after the given event id.

        Used for WebSocket reconnect backfill.

        Args:
            event_id: The id of the last event the client received.

        Returns:
            Events emitted after event_id, oldest first, when the anchor
            is found in the buffer (may be an empty list if nothing follows).
            Returns None when the anchor id is not present — either because
            it was evicted by the ring buffer or was never emitted — signalling
            that the client must refetch full state via GET rather than assume
            it is up-to-date.
        """
        events = list(self._buffer)
        for index, event in enumerate(events):
            if event.id == event_id:
                return events[index + 1:]
        return None

    async def wait_for_broadcasts(self) -> None:
        """Wait for all pending broadcast tasks to complete.

        Useful in tests to ensure broadcasts are delivered before assertions.
        Unlike cleanup(), this does not clear the task set.
        """
        if self._broadcast_tasks:
            await asyncio.gather(*self._broadcast_tasks, return_exceptions=True)

    async def cleanup(self) -> None:
        """Wait for all pending broadcast tasks to complete and clear tracking.

        Should be called during graceful shutdown to ensure all events
        are delivered before the server stops.
        """
        await self.wait_for_broadcasts()
        self._broadcast_tasks.clear()
