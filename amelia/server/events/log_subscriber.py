"""EventBus subscriber that logs workflow events to the server console."""

from __future__ import annotations

from loguru import logger

from amelia.server.models.events import EventLevel, EventType, WorkflowEvent


# Events worth showing in server console. Excludes trace-level noise
# (claude_thinking, claude_tool_call, claude_tool_result, stream, etc.)
# which would flood the console — those belong in the dashboard only.
_CONSOLE_EVENT_TYPES: frozenset[EventType] = frozenset(
    {
        # Workflow lifecycle
        EventType.WORKFLOW_STARTED,
        EventType.WORKFLOW_COMPLETED,
        EventType.WORKFLOW_FAILED,
        EventType.WORKFLOW_CANCELLED,
        # Stage transitions
        EventType.STAGE_STARTED,
        EventType.STAGE_COMPLETED,
        # Agent output
        EventType.AGENT_MESSAGE,
        # Task progress
        EventType.TASK_STARTED,
        EventType.TASK_COMPLETED,
        EventType.TASK_FAILED,
        # Approval flow
        EventType.APPROVAL_REQUIRED,
        EventType.APPROVAL_GRANTED,
        EventType.APPROVAL_REJECTED,
        # Review
        EventType.REVIEW_COMPLETED,
        # Errors
        EventType.SYSTEM_ERROR,
        EventType.SYSTEM_WARNING,
    }
)


def log_event_to_console(event: WorkflowEvent) -> None:
    """Log a workflow event to the server console via loguru.

    Must be non-blocking — called synchronously by EventBus.emit().
    Only logs console-worthy event types; trace-level events are skipped.
    Promotes AGENT_MESSAGE from DEBUG to INFO for visibility.
    """
    if event.event_type not in _CONSOLE_EVENT_TYPES:
        return

    level = (event.level or EventLevel.INFO).value.upper()

    # Promote AGENT_MESSAGE to INFO when it would otherwise be DEBUG,
    # so agent output is always visible on the console.
    if event.event_type == EventType.AGENT_MESSAGE and level == "DEBUG":
        level = "INFO"

    agent = event.agent or "system"
    logger.log(
        level,
        "[{agent}] {message}",
        agent=agent,
        message=event.message,
        workflow_id=str(event.workflow_id)[:8],
        event_type=event.event_type.value,
    )
