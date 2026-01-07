"""Event bus implementation for pub/sub workflow events."""
import asyncio
import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from amelia.server.models import WorkflowEvent
from amelia.server.models.events import EventLevel


if TYPE_CHECKING:
    from amelia.server.events.connection_manager import ConnectionManager


class EventBus:
    """Simple synchronous pub/sub event bus for workflow events.

    Allows components to subscribe to and emit workflow events.
    Exceptions in subscribers are logged but don't prevent other
    subscribers from receiving events.

    Warning:
        All subscribers MUST be non-blocking. Since emit() runs
        synchronously in the caller's context, blocking operations
        in subscribers will halt the orchestrator.

    Attributes:
        _subscribers: List of callback functions to notify on emit.
        _broadcast_tasks: Set of active broadcast tasks for cleanup tracking.
        _trace_retention_days: Days to retain trace events (0 = no persistence).
    """

    def __init__(self) -> None:
        """Initialize event bus with no subscribers."""
        self._subscribers: list[Callable[[WorkflowEvent], None]] = []
        self._connection_manager: ConnectionManager | None = None
        self._broadcast_tasks: set[asyncio.Task[None]] = set()
        self._trace_retention_days: int = 7

    def subscribe(self, callback: Callable[[WorkflowEvent], None]) -> None:
        """Subscribe to workflow events.

        Args:
            callback: Function to call when events are emitted.
        """
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[WorkflowEvent], None]) -> None:
        """Unsubscribe from workflow events.

        Args:
            callback: Previously subscribed callback to remove.
        """
        with contextlib.suppress(ValueError):
            self._subscribers.remove(callback)

    def set_connection_manager(self, manager: "ConnectionManager") -> None:
        """Set the ConnectionManager for WebSocket broadcasting.

        Args:
            manager: The ConnectionManager instance.
        """
        self._connection_manager = manager

    def configure(self, trace_retention_days: int | None = None) -> None:
        """Configure event bus settings.

        Args:
            trace_retention_days: Days to retain trace events. Set to 0 to disable
                persistence of trace events (WebSocket broadcast only).
        """
        if trace_retention_days is not None:
            self._trace_retention_days = trace_retention_days

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

        For trace-level events:
        - Skips persistence (subscriber notification) if trace_retention_days=0
        - Always broadcasts to WebSocket for real-time UI

        Warning:
            Subscribers MUST be non-blocking. Since emit() runs synchronously
            in the caller's context, any blocking operation in a subscriber
            will halt the orchestrator. If you need to perform I/O or slow
            operations, dispatch them as background tasks within your callback.

        Args:
            event: The workflow event to broadcast.
        """
        # Determine if this is a trace event
        is_trace = event.level == EventLevel.TRACE

        # Handle persistence (subscriber notification)
        should_persist = not is_trace or self._trace_retention_days > 0
        if should_persist:
            for callback in self._subscribers:
                try:
                    callback(event)
                except Exception as exc:
                    # Use getattr to safely get callback name - functools.partial,
                    # callable instances, etc. may not have __name__
                    callback_name = getattr(callback, "__name__", repr(callback))
                    logger.exception(
                        "Subscriber raised exception",
                        callback=callback_name,
                        event_type=event.event_type,
                        error=str(exc),
                    )

        # Always broadcast to WebSocket
        if self._connection_manager:
            task = asyncio.create_task(self._connection_manager.broadcast(event))
            self._broadcast_tasks.add(task)
            task.add_done_callback(self._handle_broadcast_done)

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
