# Server Console Event Logging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bridge EventBus workflow events to the server console via loguru so agent execution is visible without the dashboard.

**Architecture:** A single subscriber function registered on the EventBus logs every event at its natural `EventLevel`. Loguru's existing level filter (`AMELIA_LOG_LEVEL`) controls visibility. Redundant direct `logger.info()` calls in the orchestrator are removed.

**Tech Stack:** Python, loguru, pytest, Pydantic

---

### Task 1: Create log subscriber with tests (TDD)

**Files:**
- Create: `tests/unit/server/events/test_log_subscriber.py`
- Create: `amelia/server/events/log_subscriber.py`

**Step 1: Write the failing tests**

Create `tests/unit/server/events/test_log_subscriber.py`:

```python
"""Tests for EventBus -> console log subscriber."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

from amelia.server.events.log_subscriber import log_event_to_console
from amelia.server.models.events import EventLevel, EventType, WorkflowEvent


def _make_event(
    event_type: EventType,
    message: str = "test message",
    agent: str = "architect",
    level: EventLevel | None = None,
) -> WorkflowEvent:
    return WorkflowEvent(
        id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        sequence=1,
        timestamp=datetime.now(UTC),
        agent=agent,
        event_type=event_type,
        message=message,
        level=level,
    )


class TestLogEventToConsole:
    """Tests for log_event_to_console subscriber."""

    @patch("amelia.server.events.log_subscriber.logger")
    def test_logs_info_event_at_info_level(self, mock_logger: object) -> None:
        event = _make_event(EventType.STAGE_STARTED, "Starting architect")
        log_event_to_console(event)
        mock_logger.log.assert_called_once()  # type: ignore[union-attr]
        assert mock_logger.log.call_args[0][0] == "INFO"  # type: ignore[union-attr]

    @patch("amelia.server.events.log_subscriber.logger")
    def test_logs_error_event_at_error_level(self, mock_logger: object) -> None:
        event = _make_event(EventType.WORKFLOW_FAILED, "Workflow failed: timeout")
        log_event_to_console(event)
        assert mock_logger.log.call_args[0][0] == "ERROR"  # type: ignore[union-attr]

    @patch("amelia.server.events.log_subscriber.logger")
    def test_logs_debug_event_at_debug_level(self, mock_logger: object) -> None:
        event = _make_event(EventType.CLAUDE_TOOL_CALL, "Calling EditFile")
        log_event_to_console(event)
        assert mock_logger.log.call_args[0][0] == "DEBUG"  # type: ignore[union-attr]

    @patch("amelia.server.events.log_subscriber.logger")
    def test_logs_warning_event_at_warning_level(self, mock_logger: object) -> None:
        event = _make_event(EventType.SYSTEM_WARNING, "Rate limit approaching")
        log_event_to_console(event)
        assert mock_logger.log.call_args[0][0] == "WARNING"  # type: ignore[union-attr]

    @patch("amelia.server.events.log_subscriber.logger")
    def test_includes_structured_fields(self, mock_logger: object) -> None:
        event = _make_event(EventType.STAGE_COMPLETED, "Completed architect")
        log_event_to_console(event)
        call_kwargs = mock_logger.log.call_args[1]  # type: ignore[union-attr]
        assert "workflow_id" in call_kwargs
        assert "event_type" in call_kwargs
        assert call_kwargs["event_type"] == "stage_completed"

    @patch("amelia.server.events.log_subscriber.logger")
    def test_defaults_agent_to_system(self, mock_logger: object) -> None:
        event = _make_event(EventType.WORKFLOW_STARTED, "Started", agent="")
        log_event_to_console(event)
        call_kwargs = mock_logger.log.call_args[1]  # type: ignore[union-attr]
        assert call_kwargs["agent"] == "system"

    @patch("amelia.server.events.log_subscriber.logger")
    def test_defaults_level_to_info_when_none(self, mock_logger: object) -> None:
        event = _make_event(EventType.STAGE_STARTED, "test", level=None)
        # model_post_init sets level from event type, so override after creation
        object.__setattr__(event, "level", None)
        log_event_to_console(event)
        assert mock_logger.log.call_args[0][0] == "INFO"  # type: ignore[union-attr]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/events/test_log_subscriber.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'amelia.server.events.log_subscriber'`

**Step 3: Write the implementation**

Create `amelia/server/events/log_subscriber.py`:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/events/test_log_subscriber.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add amelia/server/events/log_subscriber.py tests/unit/server/events/test_log_subscriber.py
git commit -m "feat(events): add console log subscriber for EventBus (#488)"
```

---

### Task 2: Register subscriber in lifespan

**Files:**
- Modify: `amelia/server/main.py:177-178`

**Step 1: Add import and registration**

In `amelia/server/main.py`, after line 177 (`connection_manager.set_repository(repository)`), add:

```python
    # Bridge events to server console via loguru
    from amelia.server.events.log_subscriber import log_event_to_console  # noqa: PLC0415

    event_bus.subscribe(log_event_to_console)
```

This goes before the `# Create and register orchestrator` comment block (line 179).

**Step 2: Verify no import errors**

Run: `uv run python -c "from amelia.server.main import create_app; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add amelia/server/main.py
git commit -m "feat(server): register console log subscriber in lifespan (#488)"
```

---

### Task 3: Remove redundant logger.info() calls from orchestrator

**Files:**
- Modify: `amelia/server/orchestrator/service.py`

Remove these 9 `logger.info()` call blocks. Each is a standalone statement that can be deleted along with the blank line after it:

1. **Lines 567-572**: `logger.info("Starting workflow", ...)`
2. **Lines 864-868**: `logger.info("Workflow cancelled", ...)`
3. **Line 943**: `logger.info("Resuming workflow", ...)`
4. **Lines 1192-1196**: `logger.info("Workflow paused for human approval", ...)`
5. **Line 1522**: `logger.info("Workflow approved", ...)`
6. **Lines 1698-1702**: `logger.info("Workflow rejected", ...)`
7. **Lines 2375-2379**: `logger.info("Workflow queued with plan", ...)`
8. **Lines 2484-2489**: `logger.info("Workflow queued, spawning planning task", ...)`
9. **Lines 2560-2565**: `logger.info("Starting pending workflow", ...)`

**Do NOT remove** any `logger.debug()`, `logger.warning()`, or `logger.exception()` calls — those serve diagnostic purposes not covered by events.

**Step 1: Remove the 9 logger.info() blocks**

Delete each block listed above. Preserve surrounding blank lines for readability (don't leave double blank lines).

**Step 2: Run existing tests**

Run: `uv run pytest tests/unit/server/ -v --timeout=30`
Expected: All existing tests PASS. Some tests may mock `logger.info` — if any fail, update those tests to remove expectations for the deleted log calls.

**Step 3: Run type checker**

Run: `uv run mypy amelia/server/orchestrator/service.py`
Expected: No new errors. If `logger` import becomes unused after removals, remove it (unlikely — other logger calls remain).

**Step 4: Commit**

```bash
git add amelia/server/orchestrator/service.py
git commit -m "refactor(orchestrator): remove redundant logger.info calls (#488)

These events are now logged via the EventBus console subscriber."
```

---

### Task 4: Final verification

**Step 1: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All tests PASS

**Step 2: Run linters and type checker**

Run: `uv run ruff check amelia tests && uv run mypy amelia`
Expected: No errors

**Step 3: Run dashboard build**

Run: `cd dashboard && pnpm build && cd ..`
Expected: Build succeeds (no changes to dashboard, but pre-push hook checks it)
