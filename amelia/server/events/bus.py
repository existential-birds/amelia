# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Event bus implementation for pub/sub workflow events."""
import asyncio
import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from amelia.core.types import StreamEvent
from amelia.server.models import WorkflowEvent


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
    """

    def __init__(self) -> None:
        """Initialize event bus with no subscribers."""
        self._subscribers: list[Callable[[WorkflowEvent], None]] = []
        self._connection_manager: ConnectionManager | None = None
        self._broadcast_tasks: set[asyncio.Task[None]] = set()

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
        """Emit event to all subscribers synchronously.

        Subscribers are called in registration order. Exceptions in individual
        subscribers are logged but don't prevent other subscribers from
        receiving the event.

        Warning:
            Subscribers MUST be non-blocking. Since emit() runs synchronously
            in the caller's context, any blocking operation in a subscriber
            will halt the orchestrator. If you need to perform I/O or slow
            operations, dispatch them as background tasks within your callback.

        Args:
            event: The workflow event to broadcast.
        """
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

        # Broadcast to WebSocket clients
        if self._connection_manager:
            task = asyncio.create_task(self._connection_manager.broadcast(event))
            self._broadcast_tasks.add(task)
            task.add_done_callback(self._handle_broadcast_done)

    def emit_stream(self, event: StreamEvent) -> None:
        """Emit a stream event to WebSocket clients without persistence.

        Stream events are ephemeral - they're broadcast in real-time but
        not stored in the database. Unlike emit(), this does NOT call
        regular WorkflowEvent subscribers.

        Args:
            event: The stream event to broadcast.
        """
        if self._connection_manager:
            task = asyncio.create_task(self._connection_manager.broadcast_stream(event))
            self._broadcast_tasks.add(task)
            task.add_done_callback(self._handle_broadcast_done)

    async def cleanup(self) -> None:
        """Wait for all pending broadcast tasks to complete.

        Should be called during graceful shutdown to ensure all events
        are delivered before the server stops.
        """
        if self._broadcast_tasks:
            await asyncio.gather(*self._broadcast_tasks, return_exceptions=True)
            self._broadcast_tasks.clear()
