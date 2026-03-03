# Server Console Event Logging

**Issue**: #488 — Server console missing agent execution logs
**Date**: 2026-03-03
**Branch**: `488-server-console-event-logging`

## Problem

When running `amelia server` or `amelia dev`, workflow events (stage transitions, agent messages, tool calls, task progress) only appear in the WebSocket-connected dashboard. The server console shows nothing between workflow start and completion, making headless/CI/API-only usage a black box.

## Design

### Subscriber function

A single `log_event_to_console()` function in `amelia/server/events/log_subscriber.py`, registered as an EventBus subscriber. It logs every event at its natural `EventLevel` with no filtering — loguru's level filter (controlled by `AMELIA_LOG_LEVEL`) handles visibility.

```python
def log_event_to_console(event: WorkflowEvent) -> None:
    level = (event.level or EventLevel.INFO).value.upper()
    agent = event.agent or "system"
    logger.log(level, "[{agent}] {message}", agent=agent, message=event.message,
               workflow_id=str(event.workflow_id)[:8], event_type=event.event_type.value)
```

### Registration

In `lifespan()` (main.py), after `connection_manager.set_repository(repository)`:

```python
from amelia.server.events.log_subscriber import log_event_to_console
event_bus.subscribe(log_event_to_console)
```

### Visibility by log level

- `AMELIA_LOG_LEVEL=INFO` (default): lifecycle, stages, approvals, reviews, errors, warnings
- `AMELIA_LOG_LEVEL=DEBUG`: all of the above + tool calls, agent messages, task progress, thinking, tool results

### Consolidation

Remove 9 redundant `logger.info()` calls from `orchestrator/service.py` that duplicate EventBus events:

1. "Starting workflow" (~line 567)
2. "Workflow cancelled" (~line 864)
3. "Resuming workflow" (~line 943)
4. "Workflow paused for human approval" (~line 1192)
5. "Workflow approved" (~line 1522)
6. "Workflow rejected" (~line 1698)
7. "Workflow queued with plan" (~line 2375)
8. "Workflow queued, spawning planning task" (~line 2484)
9. "Starting pending workflow" (~line 2560)

Keep all `logger.debug()`, `logger.warning()`, and `logger.exception()` calls — these serve diagnostic purposes not covered by events.

### No new env vars

The existing `AMELIA_LOG_LEVEL` controls verbosity. No new configuration needed.

### Driver support

All three drivers (Claude CLI, Codex CLI, DeepAgents API) already emit `CLAUDE_TOOL_CALL` with `tool_name` and `tool_input` via `AgenticMessage.to_workflow_event()`. No driver changes needed.

## Files changed

- **New**: `amelia/server/events/log_subscriber.py` (~15 lines)
- **Edit**: `amelia/server/main.py` (2 lines in lifespan)
- **Edit**: `amelia/server/orchestrator/service.py` (remove 9 logger.info calls)
- **New**: `tests/unit/server/events/test_log_subscriber.py`

## Testing

Unit tests covering:
- Events logged at their natural EventLevel
- Structured fields (workflow_id, event_type) passed through
- All event types handled without error
