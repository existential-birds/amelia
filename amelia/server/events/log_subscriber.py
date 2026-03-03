"""EventBus subscriber that logs workflow events to the server console."""

from __future__ import annotations

from loguru import logger

from amelia.server.models.events import EventLevel, WorkflowEvent


def log_event_to_console(event: WorkflowEvent) -> None:
    """Log a workflow event to the server console via loguru.

    Must be non-blocking — called synchronously by EventBus.emit().
    Uses the event's natural EventLevel so that AMELIA_LOG_LEVEL controls
    which events are visible on the console.
    """
    level = (event.level or EventLevel.INFO).value.upper()
    agent = event.agent or "system"
    logger.log(
        level,
        "[{agent}] {message}",
        agent=agent,
        message=event.message,
        workflow_id=str(event.workflow_id)[:8],
        event_type=event.event_type.value,
    )
