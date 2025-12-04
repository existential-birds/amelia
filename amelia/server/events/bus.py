"""Event bus implementation for pub/sub workflow events."""
import contextlib
from collections.abc import Callable

from loguru import logger

from amelia.server.models import WorkflowEvent


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
    """

    def __init__(self) -> None:
        """Initialize event bus with no subscribers."""
        self._subscribers: list[Callable[[WorkflowEvent], None]] = []

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
                logger.exception(
                    "Subscriber raised exception",
                    callback=callback.__name__,
                    event_type=event.event_type,
                    error=str(exc),
                )
