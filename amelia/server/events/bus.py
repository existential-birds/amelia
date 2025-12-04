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
        """Emit event to all subscribers.

        Exceptions in individual subscribers are logged but don't
        prevent other subscribers from receiving the event.

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
