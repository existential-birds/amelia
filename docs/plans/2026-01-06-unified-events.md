# Unified Events Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify WorkflowEvent and StreamEvent into a single model with `level` field (info/debug/trace), persist trace events, add virtualization to Activity log for performance, and group events hierarchically by stage.

**Architecture:** Add `EventLevel` enum to categorize events. Extend `WorkflowEvent` to hold trace-specific fields (`tool_name`, `tool_input`, `is_error`). Update database schema. Refactor ActivityLog with `@tanstack/react-virtual` for performance and stage-based grouping. Keep LogsPage for trace events only.

**Tech Stack:** Python/Pydantic (backend), SQLite (database), React/TypeScript (frontend), @tanstack/react-virtual (virtualization), Zustand (state)

---

## Task 1: Add EventLevel Enum

**Files:**
- Modify: `amelia/server/models/events.py:1-80`
- Test: `tests/unit/server/models/test_events.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/models/test_events.py
"""Tests for event models."""

import pytest
from amelia.server.models.events import EventLevel, EventType, get_event_level


class TestEventLevel:
    """Tests for EventLevel enum and classification."""

    def test_event_level_values(self) -> None:
        """EventLevel has info, debug, trace values."""
        assert EventLevel.INFO == "info"
        assert EventLevel.DEBUG == "debug"
        assert EventLevel.TRACE == "trace"

    @pytest.mark.parametrize(
        "event_type,expected_level",
        [
            # INFO level - workflow lifecycle
            (EventType.WORKFLOW_STARTED, EventLevel.INFO),
            (EventType.WORKFLOW_COMPLETED, EventLevel.INFO),
            (EventType.WORKFLOW_FAILED, EventLevel.INFO),
            (EventType.WORKFLOW_CANCELLED, EventLevel.INFO),
            # INFO level - stages
            (EventType.STAGE_STARTED, EventLevel.INFO),
            (EventType.STAGE_COMPLETED, EventLevel.INFO),
            # INFO level - approvals
            (EventType.APPROVAL_REQUIRED, EventLevel.INFO),
            (EventType.APPROVAL_GRANTED, EventLevel.INFO),
            (EventType.APPROVAL_REJECTED, EventLevel.INFO),
            # INFO level - review completion
            (EventType.REVIEW_COMPLETED, EventLevel.INFO),
            # DEBUG level - tasks
            (EventType.TASK_STARTED, EventLevel.DEBUG),
            (EventType.TASK_COMPLETED, EventLevel.DEBUG),
            (EventType.TASK_FAILED, EventLevel.DEBUG),
            # DEBUG level - files
            (EventType.FILE_CREATED, EventLevel.DEBUG),
            (EventType.FILE_MODIFIED, EventLevel.DEBUG),
            (EventType.FILE_DELETED, EventLevel.DEBUG),
            # DEBUG level - other
            (EventType.AGENT_MESSAGE, EventLevel.DEBUG),
            (EventType.REVISION_REQUESTED, EventLevel.DEBUG),
            (EventType.REVIEW_REQUESTED, EventLevel.DEBUG),
            (EventType.SYSTEM_ERROR, EventLevel.DEBUG),
            (EventType.SYSTEM_WARNING, EventLevel.DEBUG),
            # TRACE level - stream events
            (EventType.CLAUDE_THINKING, EventLevel.TRACE),
            (EventType.CLAUDE_TOOL_CALL, EventLevel.TRACE),
            (EventType.CLAUDE_TOOL_RESULT, EventLevel.TRACE),
            (EventType.AGENT_OUTPUT, EventLevel.TRACE),
        ],
    )
    def test_get_event_level(self, event_type: EventType, expected_level: EventLevel) -> None:
        """get_event_level returns correct level for each event type."""
        assert get_event_level(event_type) == expected_level
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_events.py -v`
Expected: FAIL with "cannot import name 'EventLevel'"

**Step 3: Write minimal implementation**

```python
# amelia/server/models/events.py - add after imports, before EventType

class EventLevel(StrEnum):
    """Event severity level for filtering and retention.

    Attributes:
        INFO: High-level workflow events (lifecycle, stages, approvals).
        DEBUG: Operational details (tasks, files, messages).
        TRACE: Verbose execution trace (thinking, tool calls).
    """

    INFO = "info"
    DEBUG = "debug"
    TRACE = "trace"
```

Then extend EventType enum to include stream event types (add after STREAM):

```python
    # Stream event types (trace level)
    CLAUDE_THINKING = "claude_thinking"
    CLAUDE_TOOL_CALL = "claude_tool_call"
    CLAUDE_TOOL_RESULT = "claude_tool_result"
    AGENT_OUTPUT = "agent_output"
```

Then add the level mapping function after EventType:

```python
# Event type to level mapping
_INFO_TYPES: frozenset[EventType] = frozenset({
    EventType.WORKFLOW_STARTED,
    EventType.WORKFLOW_COMPLETED,
    EventType.WORKFLOW_FAILED,
    EventType.WORKFLOW_CANCELLED,
    EventType.STAGE_STARTED,
    EventType.STAGE_COMPLETED,
    EventType.APPROVAL_REQUIRED,
    EventType.APPROVAL_GRANTED,
    EventType.APPROVAL_REJECTED,
    EventType.REVIEW_COMPLETED,
})

_TRACE_TYPES: frozenset[EventType] = frozenset({
    EventType.CLAUDE_THINKING,
    EventType.CLAUDE_TOOL_CALL,
    EventType.CLAUDE_TOOL_RESULT,
    EventType.AGENT_OUTPUT,
})


def get_event_level(event_type: EventType) -> EventLevel:
    """Get the level for an event type.

    Args:
        event_type: The event type to classify.

    Returns:
        EventLevel for the given event type.
    """
    if event_type in _INFO_TYPES:
        return EventLevel.INFO
    if event_type in _TRACE_TYPES:
        return EventLevel.TRACE
    return EventLevel.DEBUG
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_events.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/models/events.py tests/unit/server/models/test_events.py
git commit -m "feat(events): add EventLevel enum and get_event_level function"
```

---

## Task 2: Extend WorkflowEvent Model

**Files:**
- Modify: `amelia/server/models/events.py:82-132`
- Test: `tests/unit/server/models/test_events.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/server/models/test_events.py

from datetime import datetime, UTC


class TestWorkflowEvent:
    """Tests for WorkflowEvent model."""

    def test_workflow_event_has_level_field(self) -> None:
        """WorkflowEvent includes level field with default."""
        event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="architect",
            event_type=EventType.STAGE_STARTED,
            message="Test",
        )
        assert event.level == EventLevel.INFO

    def test_workflow_event_trace_fields(self) -> None:
        """WorkflowEvent includes trace-specific fields."""
        event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.CLAUDE_TOOL_CALL,
            level=EventLevel.TRACE,
            message="Tool call: Edit",
            tool_name="Edit",
            tool_input={"file": "test.py"},
            is_error=False,
        )
        assert event.level == EventLevel.TRACE
        assert event.tool_name == "Edit"
        assert event.tool_input == {"file": "test.py"}
        assert event.is_error is False

    def test_workflow_event_level_defaults_from_event_type(self) -> None:
        """Level defaults based on event_type when not provided."""
        # INFO event
        info_event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )
        assert info_event.level == EventLevel.INFO

        # DEBUG event
        debug_event = WorkflowEvent(
            id="evt-2",
            workflow_id="wf-1",
            sequence=2,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.FILE_MODIFIED,
            message="Modified file",
        )
        assert debug_event.level == EventLevel.DEBUG

        # TRACE event
        trace_event = WorkflowEvent(
            id="evt-3",
            workflow_id="wf-1",
            sequence=3,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.CLAUDE_THINKING,
            message="Thinking...",
        )
        assert trace_event.level == EventLevel.TRACE
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_events.py::TestWorkflowEvent -v`
Expected: FAIL with validation error (level field missing or wrong type)

**Step 3: Write minimal implementation**

Update WorkflowEvent class in `amelia/server/models/events.py`:

```python
class WorkflowEvent(BaseModel):
    """Event for activity log and real-time updates.

    Events are immutable and append-only. They form the authoritative
    history of workflow execution.

    Attributes:
        id: Unique event identifier (UUID).
        workflow_id: Links to ExecutionState.
        sequence: Monotonic counter per workflow (ensures ordering).
        timestamp: When event occurred.
        agent: Source of event ("architect", "developer", "reviewer", "system").
        event_type: Typed event category.
        level: Event severity level (info, debug, trace).
        message: Human-readable summary.
        data: Optional structured payload (file paths, error details, etc.).
        correlation_id: Links related events (e.g., approval request -> granted).
        tool_name: Tool name for trace events (optional).
        tool_input: Tool input parameters for trace events (optional).
        is_error: Whether trace event represents an error (default False).
    """

    id: str = Field(..., description="Unique event identifier")
    workflow_id: str = Field(..., description="Workflow this event belongs to")
    sequence: int = Field(..., ge=1, description="Monotonic sequence number")
    timestamp: datetime = Field(..., description="When event occurred")
    agent: str = Field(..., description="Event source agent")
    event_type: EventType = Field(..., description="Event type category")
    level: EventLevel = Field(default=None, description="Event severity level")
    message: str = Field(..., description="Human-readable message")
    data: dict[str, Any] | None = Field(
        default=None,
        description="Optional structured payload",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Links related events for tracing",
    )
    # Trace-specific fields
    tool_name: str | None = Field(
        default=None,
        description="Tool name for trace events",
    )
    tool_input: dict[str, Any] | None = Field(
        default=None,
        description="Tool input parameters for trace events",
    )
    is_error: bool = Field(
        default=False,
        description="Whether trace event represents an error",
    )

    def model_post_init(self, __context: Any) -> None:
        """Set level from event_type if not provided."""
        if self.level is None:
            object.__setattr__(self, "level", get_event_level(self.event_type))

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "evt-123",
                    "workflow_id": "wf-456",
                    "sequence": 1,
                    "timestamp": "2025-01-01T12:00:00Z",
                    "agent": "architect",
                    "event_type": "stage_started",
                    "level": "info",
                    "message": "Creating task plan",
                    "data": {"stage": "planning"},
                }
            ]
        }
    }
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_events.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/models/events.py tests/unit/server/models/test_events.py
git commit -m "feat(events): extend WorkflowEvent with level and trace fields"
```

---

## Task 3: Update Database Schema

**Files:**
- Modify: `amelia/server/database/connection.py`
- Test: `tests/unit/server/database/test_connection.py` (if exists, else create)

**Step 1: Write the failing test**

```python
# tests/unit/server/database/test_schema.py
"""Tests for database schema."""

import pytest
from amelia.server.database.connection import Database


@pytest.fixture
async def db(tmp_path):
    """Create a test database."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    yield db
    await db.close()


class TestEventsSchema:
    """Tests for events table schema."""

    @pytest.mark.asyncio
    async def test_events_table_has_level_column(self, db: Database) -> None:
        """Events table has level column."""
        result = await db.fetch_one("PRAGMA table_info(events)")
        columns = await db.fetch_all("PRAGMA table_info(events)")
        column_names = [col["name"] for col in columns]
        assert "level" in column_names

    @pytest.mark.asyncio
    async def test_events_table_has_trace_columns(self, db: Database) -> None:
        """Events table has trace-specific columns."""
        columns = await db.fetch_all("PRAGMA table_info(events)")
        column_names = [col["name"] for col in columns]
        assert "tool_name" in column_names
        assert "tool_input_json" in column_names
        assert "is_error" in column_names

    @pytest.mark.asyncio
    async def test_events_level_index_exists(self, db: Database) -> None:
        """Events table has index on level column."""
        indexes = await db.fetch_all("PRAGMA index_list(events)")
        index_names = [idx["name"] for idx in indexes]
        assert "idx_events_level" in index_names
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_schema.py -v`
Expected: FAIL with "level not in column_names"

**Step 3: Write minimal implementation**

Update the events table schema in `amelia/server/database/connection.py`. Find the CREATE TABLE events statement and update it:

```python
# In ensure_schema() method, update the events table creation:
await self.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
        sequence INTEGER NOT NULL,
        timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        agent TEXT NOT NULL,
        event_type TEXT NOT NULL,
        level TEXT NOT NULL DEFAULT 'debug',
        message TEXT NOT NULL,
        data_json TEXT,
        correlation_id TEXT,
        tool_name TEXT,
        tool_input_json TEXT,
        is_error INTEGER NOT NULL DEFAULT 0
    )
""")

# Add index for level-based queries (after other event indexes):
await self.execute(
    "CREATE INDEX IF NOT EXISTS idx_events_level ON events(level)"
)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_schema.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/database/connection.py tests/unit/server/database/test_schema.py
git commit -m "feat(db): add level and trace columns to events table"
```

---

## Task 4: Update Repository save_event and _row_to_event

**Files:**
- Modify: `amelia/server/database/repository.py`
- Test: `tests/unit/server/database/test_repository.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/server/database/test_repository.py (or create if needed)

from datetime import datetime, UTC
from amelia.server.models.events import EventType, EventLevel, WorkflowEvent


class TestRepositoryEvents:
    """Tests for event persistence."""

    @pytest.mark.asyncio
    async def test_save_event_with_level(self, repository, sample_workflow) -> None:
        """save_event persists level field."""
        event = WorkflowEvent(
            id="evt-level-test",
            workflow_id=sample_workflow.id,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            level=EventLevel.INFO,
            message="Started",
        )
        await repository.save_event(event)

        row = await repository._db.fetch_one(
            "SELECT level FROM events WHERE id = ?", (event.id,)
        )
        assert row["level"] == "info"

    @pytest.mark.asyncio
    async def test_save_event_with_trace_fields(self, repository, sample_workflow) -> None:
        """save_event persists trace-specific fields."""
        event = WorkflowEvent(
            id="evt-trace-test",
            workflow_id=sample_workflow.id,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.CLAUDE_TOOL_CALL,
            level=EventLevel.TRACE,
            message="Tool call: Edit",
            tool_name="Edit",
            tool_input={"file": "test.py", "content": "hello"},
            is_error=False,
        )
        await repository.save_event(event)

        row = await repository._db.fetch_one(
            "SELECT tool_name, tool_input_json, is_error FROM events WHERE id = ?",
            (event.id,),
        )
        assert row["tool_name"] == "Edit"
        assert row["is_error"] == 0
        import json
        assert json.loads(row["tool_input_json"]) == {"file": "test.py", "content": "hello"}

    @pytest.mark.asyncio
    async def test_row_to_event_restores_level(self, repository, sample_workflow) -> None:
        """_row_to_event restores level and trace fields."""
        event = WorkflowEvent(
            id="evt-restore-test",
            workflow_id=sample_workflow.id,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.CLAUDE_TOOL_CALL,
            level=EventLevel.TRACE,
            message="Tool call",
            tool_name="Read",
            tool_input={"path": "/test"},
            is_error=True,
        )
        await repository.save_event(event)

        events = await repository.get_recent_events(sample_workflow.id, limit=1)
        restored = events[0]

        assert restored.level == EventLevel.TRACE
        assert restored.tool_name == "Read"
        assert restored.tool_input == {"path": "/test"}
        assert restored.is_error is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_repository.py::TestRepositoryEvents -v`
Expected: FAIL (level column doesn't exist or not being saved)

**Step 3: Write minimal implementation**

Update `save_event` in `amelia/server/database/repository.py`:

```python
async def save_event(self, event: WorkflowEvent) -> None:
    """Persist workflow event to database.

    Args:
        event: Event to persist.
    """
    serialized = event.model_dump(mode="json")
    data_json = json.dumps(serialized["data"]) if serialized["data"] else None
    tool_input_json = (
        json.dumps(serialized["tool_input"]) if serialized["tool_input"] else None
    )

    await self._db.execute(
        """
        INSERT INTO events (
            id, workflow_id, sequence, timestamp, agent,
            event_type, level, message, data_json, correlation_id,
            tool_name, tool_input_json, is_error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.id,
            event.workflow_id,
            event.sequence,
            event.timestamp.isoformat(),
            event.agent,
            event.event_type.value,
            event.level.value,
            event.message,
            data_json,
            event.correlation_id,
            event.tool_name,
            tool_input_json,
            1 if event.is_error else 0,
        ),
    )
```

Update `_row_to_event` in `amelia/server/database/repository.py`:

```python
def _row_to_event(self, row: dict[str, Any]) -> WorkflowEvent:
    """Convert database row to WorkflowEvent."""
    data = json.loads(row["data_json"]) if row["data_json"] else None
    tool_input = (
        json.loads(row["tool_input_json"]) if row.get("tool_input_json") else None
    )

    return WorkflowEvent(
        id=row["id"],
        workflow_id=row["workflow_id"],
        sequence=row["sequence"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        agent=row["agent"],
        event_type=EventType(row["event_type"]),
        level=EventLevel(row["level"]),
        message=row["message"],
        data=data,
        correlation_id=row.get("correlation_id"),
        tool_name=row.get("tool_name"),
        tool_input=tool_input,
        is_error=bool(row.get("is_error", 0)),
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_repository.py::TestRepositoryEvents -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/database/repository.py tests/unit/server/database/test_repository.py
git commit -m "feat(db): update repository to persist level and trace fields"
```

---

## Task 5: Add trace_retention_days Config

**Files:**
- Modify: `amelia/server/config.py`
- Modify: `CLAUDE.md`
- Test: `tests/unit/server/test_config.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/test_config.py (add to existing or create)

import os
from amelia.server.config import ServerConfig


class TestServerConfig:
    """Tests for ServerConfig."""

    def test_trace_retention_days_default(self) -> None:
        """trace_retention_days defaults to 7."""
        config = ServerConfig()
        assert config.trace_retention_days == 7

    def test_trace_retention_days_from_env(self, monkeypatch) -> None:
        """trace_retention_days can be set via environment."""
        monkeypatch.setenv("AMELIA_TRACE_RETENTION_DAYS", "3")
        config = ServerConfig()
        assert config.trace_retention_days == 3

    def test_trace_retention_days_zero_disables_persistence(self) -> None:
        """trace_retention_days=0 is valid (disables persistence)."""
        config = ServerConfig(trace_retention_days=0)
        assert config.trace_retention_days == 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_config.py::TestServerConfig -v`
Expected: FAIL with "no attribute 'trace_retention_days'"

**Step 3: Write minimal implementation**

Add to `amelia/server/config.py` in ServerConfig class:

```python
trace_retention_days: int = Field(
    default=7,
    ge=0,
    description=(
        "Days to retain trace-level events (claude_thinking, tool_call, etc.). "
        "Trace events are high-volume. Set to 0 to disable trace persistence."
    ),
)
```

Update `CLAUDE.md` server config table:

```markdown
| `AMELIA_TRACE_RETENTION_DAYS` | `7` | Days to retain trace-level events. `0` = don't persist traces |
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_config.py::TestServerConfig -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/config.py CLAUDE.md tests/unit/server/test_config.py
git commit -m "feat(config): add trace_retention_days setting"
```

---

## Task 6: Update Retention Service for Trace Events

**Files:**
- Modify: `amelia/server/lifecycle/retention.py`
- Test: `tests/unit/server/lifecycle/test_retention.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/server/lifecycle/test_retention.py

class TestTraceRetention:
    """Tests for trace event retention."""

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_trace_events(
        self, retention_service, db, sample_workflow
    ) -> None:
        """cleanup_on_shutdown deletes trace events older than retention."""
        from datetime import timedelta
        old_timestamp = datetime.now(UTC) - timedelta(days=10)

        # Insert old trace event
        await db.execute(
            """
            INSERT INTO events (id, workflow_id, sequence, timestamp, agent, event_type, level, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("old-trace", sample_workflow.id, 1, old_timestamp.isoformat(),
             "developer", "claude_tool_call", "trace", "Old tool call"),
        )

        # Insert recent trace event
        await db.execute(
            """
            INSERT INTO events (id, workflow_id, sequence, timestamp, agent, event_type, level, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("new-trace", sample_workflow.id, 2, datetime.now(UTC).isoformat(),
             "developer", "claude_tool_call", "trace", "New tool call"),
        )

        result = await retention_service.cleanup_on_shutdown()

        # Old trace should be deleted, new trace should remain
        rows = await db.fetch_all("SELECT id FROM events WHERE level = 'trace'")
        event_ids = [r["id"] for r in rows]
        assert "old-trace" not in event_ids
        assert "new-trace" in event_ids
        assert result.trace_events_deleted >= 1

    @pytest.mark.asyncio
    async def test_cleanup_respects_trace_retention_days(
        self, db, sample_workflow
    ) -> None:
        """Trace retention uses trace_retention_days, not log_retention_days."""
        from amelia.server.lifecycle.retention import LogRetentionService
        from unittest.mock import MagicMock

        # Config with different retention periods
        config = MagicMock()
        config.log_retention_days = 30
        config.trace_retention_days = 3
        config.checkpoint_retention_days = -1

        service = LogRetentionService(db=db, config=config)

        # Insert trace event 5 days old (older than trace retention, newer than log retention)
        old_timestamp = datetime.now(UTC) - timedelta(days=5)
        await db.execute(
            """
            INSERT INTO events (id, workflow_id, sequence, timestamp, agent, event_type, level, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("medium-age-trace", sample_workflow.id, 1, old_timestamp.isoformat(),
             "developer", "claude_tool_call", "trace", "Medium age"),
        )

        await service.cleanup_on_shutdown()

        # Should be deleted (older than 3 days trace retention)
        row = await db.fetch_one("SELECT id FROM events WHERE id = ?", ("medium-age-trace",))
        assert row is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/lifecycle/test_retention.py::TestTraceRetention -v`
Expected: FAIL (no trace cleanup or result.trace_events_deleted doesn't exist)

**Step 3: Write minimal implementation**

Update `CleanupResult` in `amelia/server/lifecycle/retention.py`:

```python
class CleanupResult(BaseModel):
    """Result of retention cleanup operation."""
    events_deleted: int = 0
    workflows_deleted: int = 0
    checkpoints_deleted: int = 0
    trace_events_deleted: int = 0  # NEW
```

Update `ConfigProtocol` to include trace_retention_days:

```python
class ConfigProtocol(Protocol):
    """Protocol for retention configuration."""
    log_retention_days: int
    log_retention_max_events: int
    checkpoint_retention_days: int
    trace_retention_days: int  # NEW
```

Add trace cleanup to `cleanup_on_shutdown`:

```python
async def cleanup_on_shutdown(self) -> CleanupResult:
    """Run all retention cleanups on graceful shutdown."""
    # ... existing event and workflow cleanup ...

    # Cleanup trace events with separate retention
    trace_events_deleted = await self._cleanup_trace_events()

    # ... existing checkpoint cleanup ...

    return CleanupResult(
        events_deleted=events_deleted,
        workflows_deleted=workflows_deleted,
        checkpoints_deleted=checkpoints_deleted,
        trace_events_deleted=trace_events_deleted,
    )

async def _cleanup_trace_events(self) -> int:
    """Delete trace events older than trace_retention_days."""
    trace_retention_days = self._config.trace_retention_days
    if trace_retention_days < 0:
        return 0  # Disabled

    cutoff = datetime.now(UTC) - timedelta(days=trace_retention_days)

    result = await self._db.execute(
        """
        DELETE FROM events
        WHERE level = 'trace'
        AND timestamp < ?
        """,
        (cutoff.isoformat(),),
    )

    deleted = result if isinstance(result, int) else 0
    logger.info(
        "Trace cleanup complete",
        trace_events_deleted=deleted,
        trace_retention_days=trace_retention_days,
    )
    return deleted
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/lifecycle/test_retention.py::TestTraceRetention -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/lifecycle/retention.py tests/unit/server/lifecycle/test_retention.py
git commit -m "feat(retention): add trace event cleanup with separate retention period"
```

---

## Task 7: Update EventBus to Persist Trace Events

**Files:**
- Modify: `amelia/server/events/bus.py`
- Test: `tests/unit/server/events/test_bus.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/events/test_bus.py

from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock
import pytest
from amelia.core.types import StreamEvent, StreamEventType
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventType, EventLevel


class TestEventBusTraceEmit:
    """Tests for trace event emission."""

    @pytest.mark.asyncio
    async def test_emit_stream_converts_to_workflow_event(self) -> None:
        """emit_stream converts StreamEvent to WorkflowEvent for persistence."""
        bus = EventBus()
        captured_events = []

        def capture(event):
            captured_events.append(event)

        bus.subscribe(capture)

        stream_event = StreamEvent(
            type=StreamEventType.CLAUDE_TOOL_CALL,
            timestamp=datetime.now(UTC),
            agent="developer",
            workflow_id="wf-123",
            tool_name="Edit",
            tool_input={"file": "test.py"},
        )

        bus.emit_stream(stream_event)

        assert len(captured_events) == 1
        workflow_event = captured_events[0]
        assert workflow_event.event_type == EventType.CLAUDE_TOOL_CALL
        assert workflow_event.level == EventLevel.TRACE
        assert workflow_event.tool_name == "Edit"
        assert workflow_event.tool_input == {"file": "test.py"}
        assert workflow_event.workflow_id == "wf-123"

    @pytest.mark.asyncio
    async def test_emit_stream_respects_trace_retention_zero(self) -> None:
        """emit_stream skips persistence when trace_retention_days=0."""
        bus = EventBus()
        captured_events = []
        bus.subscribe(lambda e: captured_events.append(e))

        # Configure trace_retention_days=0
        bus.configure(trace_retention_days=0)

        stream_event = StreamEvent(
            type=StreamEventType.CLAUDE_THINKING,
            timestamp=datetime.now(UTC),
            agent="developer",
            workflow_id="wf-123",
            content="Thinking...",
        )

        bus.emit_stream(stream_event)

        # Should not call subscribers (no persistence)
        assert len(captured_events) == 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/events/test_bus.py::TestEventBusTraceEmit -v`
Expected: FAIL (emit_stream doesn't convert or call subscribers)

**Step 3: Write minimal implementation**

Update `EventBus` in `amelia/server/events/bus.py`:

```python
from amelia.server.models.events import WorkflowEvent, EventType, EventLevel, get_event_level


class EventBus:
    """Synchronous event bus for workflow events."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[WorkflowEvent], None]] = []
        self._connection_manager: ConnectionManager | None = None
        self._broadcast_tasks: set[asyncio.Task] = set()
        self._trace_retention_days: int = 7  # Default

    def configure(self, trace_retention_days: int | None = None) -> None:
        """Configure event bus settings."""
        if trace_retention_days is not None:
            self._trace_retention_days = trace_retention_days

    def emit_stream(self, event: StreamEvent) -> None:
        """Emit a stream event, optionally persisting as trace WorkflowEvent.

        Args:
            event: The stream event to emit.
        """
        # Filter tool results unless enabled (existing logic)
        if event.type == StreamEventType.CLAUDE_TOOL_RESULT:
            if not getattr(self, '_stream_tool_results', False):
                return

        # Skip persistence if trace retention disabled
        persist = self._trace_retention_days > 0

        if persist:
            # Convert to WorkflowEvent for persistence
            workflow_event = WorkflowEvent(
                id=event.id,
                workflow_id=event.workflow_id,
                sequence=0,  # Will be assigned by service layer
                timestamp=event.timestamp,
                agent=event.agent,
                event_type=EventType(event.type.value),
                level=EventLevel.TRACE,
                message=self._build_trace_message(event),
                tool_name=event.tool_name,
                tool_input=event.tool_input,
                is_error=event.is_error,
            )

            # Notify subscribers (for persistence)
            for callback in self._subscribers:
                try:
                    callback(workflow_event)
                except Exception as exc:
                    logger.exception("Subscriber raised exception", error=str(exc))

        # Always broadcast to WebSocket (for real-time UI)
        if self._connection_manager:
            task = asyncio.create_task(
                self._connection_manager.broadcast_stream(event)
            )
            self._broadcast_tasks.add(task)
            task.add_done_callback(self._handle_broadcast_done)

    def _build_trace_message(self, event: StreamEvent) -> str:
        """Build human-readable message for trace event."""
        if event.type == StreamEventType.CLAUDE_THINKING:
            preview = (event.content or "")[:80]
            return f"Thinking: {preview}..." if len(event.content or "") > 80 else f"Thinking: {preview}"
        elif event.type == StreamEventType.CLAUDE_TOOL_CALL:
            return f"Tool call: {event.tool_name}"
        elif event.type == StreamEventType.CLAUDE_TOOL_RESULT:
            status = "error" if event.is_error else "success"
            return f"Tool result ({status}): {event.tool_name}"
        elif event.type == StreamEventType.AGENT_OUTPUT:
            preview = (event.content or "")[:80]
            return f"Output: {preview}"
        return f"Stream: {event.type.value}"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/events/test_bus.py::TestEventBusTraceEmit -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/events/bus.py tests/unit/server/events/test_bus.py
git commit -m "feat(events): emit_stream converts to WorkflowEvent for persistence"
```

---

## Task 8: Update Frontend Types

**Files:**
- Modify: `dashboard/src/types/index.ts`
- Test: `dashboard/src/types/__tests__/index.test.ts` (create if needed)

**Step 1: Write the failing test**

```typescript
// dashboard/src/types/__tests__/index.test.ts
import { describe, it, expect } from 'vitest';
import type { EventLevel, WorkflowEvent } from '../index';

describe('WorkflowEvent types', () => {
  it('supports level field', () => {
    const event: WorkflowEvent = {
      id: 'evt-1',
      workflow_id: 'wf-1',
      sequence: 1,
      timestamp: '2025-01-01T00:00:00Z',
      agent: 'developer',
      event_type: 'claude_tool_call',
      level: 'trace',
      message: 'Tool call',
      tool_name: 'Edit',
      tool_input: { file: 'test.py' },
      is_error: false,
    };

    expect(event.level).toBe('trace');
    expect(event.tool_name).toBe('Edit');
  });

  it('level can be info, debug, or trace', () => {
    const levels: EventLevel[] = ['info', 'debug', 'trace'];
    expect(levels).toHaveLength(3);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/types/__tests__/index.test.ts`
Expected: FAIL (EventLevel type doesn't exist)

**Step 3: Write minimal implementation**

Update `dashboard/src/types/index.ts`:

```typescript
/**
 * Event severity level for filtering and display.
 */
export type EventLevel = 'info' | 'debug' | 'trace';

/**
 * Type of event that occurred.
 */
export type EventType =
  // Lifecycle
  | 'workflow_started'
  | 'workflow_completed'
  | 'workflow_failed'
  | 'workflow_cancelled'
  // Stages
  | 'stage_started'
  | 'stage_completed'
  // Approval
  | 'approval_required'
  | 'approval_granted'
  | 'approval_rejected'
  // Artifacts
  | 'file_created'
  | 'file_modified'
  | 'file_deleted'
  // Review cycle
  | 'review_requested'
  | 'review_completed'
  | 'revision_requested'
  // Agent messages
  | 'agent_message'
  | 'task_started'
  | 'task_completed'
  | 'task_failed'
  // System
  | 'system_error'
  | 'system_warning'
  // Trace (stream events)
  | 'claude_thinking'
  | 'claude_tool_call'
  | 'claude_tool_result'
  | 'agent_output';

/**
 * Workflow event from the server.
 */
export interface WorkflowEvent {
  /** Unique identifier for this event. */
  id: string;
  /** ID of the workflow this event belongs to. */
  workflow_id: string;
  /** Sequential event number within the workflow. */
  sequence: number;
  /** ISO 8601 timestamp when the event was emitted. */
  timestamp: string;
  /** Name of the agent that emitted this event. */
  agent: string;
  /** Type of event that occurred. */
  event_type: EventType;
  /** Event severity level. */
  level: EventLevel;
  /** Human-readable message describing the event. */
  message: string;
  /** Optional additional structured data. */
  data?: Record<string, unknown>;
  /** Optional correlation ID for grouping related events. */
  correlation_id?: string;
  /** Tool name for trace events. */
  tool_name?: string;
  /** Tool input parameters for trace events. */
  tool_input?: Record<string, unknown>;
  /** Whether trace event represents an error. */
  is_error?: boolean;
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/types/__tests__/index.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/types/index.ts dashboard/src/types/__tests__/index.test.ts
git commit -m "feat(dashboard): add EventLevel type and extend WorkflowEvent"
```

---

## Task 9: Add Virtualization Library

**Files:**
- Modify: `dashboard/package.json`

**Step 1: Add the dependency**

Run: `cd dashboard && pnpm add @tanstack/react-virtual`

**Step 2: Verify installation**

Run: `cd dashboard && pnpm list @tanstack/react-virtual`
Expected: Shows @tanstack/react-virtual in dependencies

**Step 3: Commit**

```bash
git add dashboard/package.json dashboard/pnpm-lock.yaml
git commit -m "chore(dashboard): add @tanstack/react-virtual for virtualization"
```

---

## Task 10: Create Activity Log Types

**Files:**
- Create: `dashboard/src/components/activity/types.ts`
- Test: `dashboard/src/components/activity/__tests__/types.test.ts`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/activity/__tests__/types.test.ts
import { describe, it, expect } from 'vitest';
import type { StageGroup, VirtualRow, AgentStage } from '../types';

describe('Activity log types', () => {
  it('StageGroup has required fields', () => {
    const group: StageGroup = {
      stage: 'architect',
      label: 'Planning (Architect)',
      events: [],
      isActive: false,
      isCompleted: true,
      startedAt: '2025-01-01T00:00:00Z',
      endedAt: '2025-01-01T00:05:00Z',
    };

    expect(group.stage).toBe('architect');
    expect(group.events).toEqual([]);
  });

  it('VirtualRow can be header or event', () => {
    const headerRow: VirtualRow = {
      type: 'header',
      group: {
        stage: 'developer',
        label: 'Implementation',
        events: [],
        isActive: true,
        isCompleted: false,
        startedAt: null,
        endedAt: null,
      },
    };

    const eventRow: VirtualRow = {
      type: 'event',
      event: {
        id: 'evt-1',
        workflow_id: 'wf-1',
        sequence: 1,
        timestamp: '2025-01-01T00:00:00Z',
        agent: 'developer',
        event_type: 'task_started',
        level: 'debug',
        message: 'Started task',
      },
      stageIndex: 1,
    };

    expect(headerRow.type).toBe('header');
    expect(eventRow.type).toBe('event');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/components/activity/__tests__/types.test.ts`
Expected: FAIL (types don't exist)

**Step 3: Write minimal implementation**

```typescript
// dashboard/src/components/activity/types.ts
import type { WorkflowEvent } from '@/types';

/**
 * Agent stages in workflow execution order.
 */
export type AgentStage = 'architect' | 'developer' | 'reviewer';

/**
 * Stage labels for display.
 */
export const STAGE_LABELS: Record<AgentStage, string> = {
  architect: 'Planning (Architect)',
  developer: 'Implementation (Developer)',
  reviewer: 'Review (Reviewer)',
};

/**
 * Stage order for sorting.
 */
export const STAGE_ORDER: AgentStage[] = ['architect', 'developer', 'reviewer'];

/**
 * Grouped events by stage for hierarchical display.
 */
export interface StageGroup {
  /** Stage identifier. */
  stage: AgentStage;
  /** Display label for the stage. */
  label: string;
  /** Events belonging to this stage. */
  events: WorkflowEvent[];
  /** Whether this stage is currently active. */
  isActive: boolean;
  /** Whether this stage is completed. */
  isCompleted: boolean;
  /** Timestamp of first event (null if no events). */
  startedAt: string | null;
  /** Timestamp of last event (null if no events). */
  endedAt: string | null;
}

/**
 * Row types for virtualized list.
 */
export type VirtualRow =
  | { type: 'header'; group: StageGroup }
  | { type: 'event'; event: WorkflowEvent; stageIndex: number };
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/components/activity/__tests__/types.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/activity/types.ts dashboard/src/components/activity/__tests__/types.test.ts
git commit -m "feat(dashboard): add activity log types for hierarchical display"
```

---

## Task 11: Create useActivityLogGroups Hook

**Files:**
- Create: `dashboard/src/components/activity/useActivityLogGroups.ts`
- Test: `dashboard/src/components/activity/__tests__/useActivityLogGroups.test.ts`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/activity/__tests__/useActivityLogGroups.test.ts
import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useActivityLogGroups } from '../useActivityLogGroups';
import type { WorkflowEvent } from '@/types';

const makeEvent = (overrides: Partial<WorkflowEvent>): WorkflowEvent => ({
  id: 'evt-1',
  workflow_id: 'wf-1',
  sequence: 1,
  timestamp: '2025-01-01T00:00:00Z',
  agent: 'developer',
  event_type: 'task_started',
  level: 'debug',
  message: 'Test event',
  ...overrides,
});

describe('useActivityLogGroups', () => {
  it('groups events by agent/stage', () => {
    const events: WorkflowEvent[] = [
      makeEvent({ id: '1', agent: 'architect', sequence: 1, event_type: 'stage_started' }),
      makeEvent({ id: '2', agent: 'architect', sequence: 2, event_type: 'stage_completed' }),
      makeEvent({ id: '3', agent: 'developer', sequence: 3, event_type: 'task_started' }),
    ];

    const { result } = renderHook(() =>
      useActivityLogGroups(events, new Set())
    );

    expect(result.current.groups).toHaveLength(2);
    expect(result.current.groups[0].stage).toBe('architect');
    expect(result.current.groups[0].events).toHaveLength(2);
    expect(result.current.groups[1].stage).toBe('developer');
    expect(result.current.groups[1].events).toHaveLength(1);
  });

  it('filters out trace level events', () => {
    const events: WorkflowEvent[] = [
      makeEvent({ id: '1', level: 'info', event_type: 'stage_started' }),
      makeEvent({ id: '2', level: 'debug', event_type: 'task_started' }),
      makeEvent({ id: '3', level: 'trace', event_type: 'claude_tool_call' }),
    ];

    const { result } = renderHook(() =>
      useActivityLogGroups(events, new Set())
    );

    const allEvents = result.current.groups.flatMap((g) => g.events);
    expect(allEvents).toHaveLength(2);
    expect(allEvents.find((e) => e.level === 'trace')).toBeUndefined();
  });

  it('collapses stages in collapsedStages set', () => {
    const events: WorkflowEvent[] = [
      makeEvent({ id: '1', agent: 'architect', sequence: 1 }),
      makeEvent({ id: '2', agent: 'developer', sequence: 2 }),
    ];

    const { result } = renderHook(() =>
      useActivityLogGroups(events, new Set(['architect']))
    );

    // Headers always present, but collapsed stage events excluded from rows
    const rows = result.current.rows;
    const architectEvents = rows.filter(
      (r) => r.type === 'event' && r.event.agent === 'architect'
    );
    expect(architectEvents).toHaveLength(0);
  });

  it('orders stages as architect -> developer -> reviewer', () => {
    const events: WorkflowEvent[] = [
      makeEvent({ id: '1', agent: 'reviewer', sequence: 1 }),
      makeEvent({ id: '2', agent: 'architect', sequence: 2 }),
      makeEvent({ id: '3', agent: 'developer', sequence: 3 }),
    ];

    const { result } = renderHook(() =>
      useActivityLogGroups(events, new Set())
    );

    const stageOrder = result.current.groups.map((g) => g.stage);
    expect(stageOrder).toEqual(['architect', 'developer', 'reviewer']);
  });

  it('marks stage active if has stage_started but not stage_completed', () => {
    const events: WorkflowEvent[] = [
      makeEvent({ id: '1', agent: 'architect', event_type: 'stage_started' }),
    ];

    const { result } = renderHook(() =>
      useActivityLogGroups(events, new Set())
    );

    expect(result.current.groups[0].isActive).toBe(true);
    expect(result.current.groups[0].isCompleted).toBe(false);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/components/activity/__tests__/useActivityLogGroups.test.ts`
Expected: FAIL (hook doesn't exist)

**Step 3: Write minimal implementation**

```typescript
// dashboard/src/components/activity/useActivityLogGroups.ts
import { useMemo } from 'react';
import type { WorkflowEvent } from '@/types';
import type { StageGroup, VirtualRow, AgentStage } from './types';
import { STAGE_ORDER, STAGE_LABELS } from './types';

/**
 * Hook to group workflow events by stage for hierarchical display.
 *
 * @param events - All workflow events (will filter to info+debug only)
 * @param collapsedStages - Set of stage names that are collapsed
 * @returns Groups and flattened rows for virtualization
 */
export function useActivityLogGroups(
  events: WorkflowEvent[],
  collapsedStages: Set<string>
): { groups: StageGroup[]; rows: VirtualRow[] } {
  return useMemo(() => {
    // Filter to info+debug only (exclude trace)
    const filteredEvents = events.filter((e) => e.level !== 'trace');

    // Group events by agent
    const byAgent = new Map<string, WorkflowEvent[]>();
    for (const event of filteredEvents) {
      const agent = event.agent.toLowerCase();
      // Map unknown agents to developer
      const targetStage = STAGE_ORDER.includes(agent as AgentStage)
        ? agent
        : 'developer';
      const existing = byAgent.get(targetStage) || [];
      existing.push(event);
      byAgent.set(targetStage, existing);
    }

    // Build stage groups in order
    const groups: StageGroup[] = STAGE_ORDER.filter((stage) =>
      byAgent.has(stage)
    ).map((stage) => {
      const stageEvents = byAgent.get(stage) || [];
      const sorted = [...stageEvents].sort(
        (a, b) =>
          new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      );

      const hasStarted = sorted.some((e) => e.event_type === 'stage_started');
      const hasCompleted = sorted.some(
        (e) => e.event_type === 'stage_completed'
      );

      return {
        stage: stage as AgentStage,
        label: STAGE_LABELS[stage as AgentStage],
        events: sorted,
        isActive: hasStarted && !hasCompleted,
        isCompleted: hasCompleted,
        startedAt: sorted[0]?.timestamp ?? null,
        endedAt: sorted[sorted.length - 1]?.timestamp ?? null,
      };
    });

    // Flatten for virtualization
    const rows: VirtualRow[] = [];
    groups.forEach((group, idx) => {
      rows.push({ type: 'header', group });
      if (!collapsedStages.has(group.stage)) {
        group.events.forEach((event) => {
          rows.push({ type: 'event', event, stageIndex: idx });
        });
      }
    });

    return { groups, rows };
  }, [events, collapsedStages]);
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/components/activity/__tests__/useActivityLogGroups.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/activity/useActivityLogGroups.ts dashboard/src/components/activity/__tests__/useActivityLogGroups.test.ts
git commit -m "feat(dashboard): add useActivityLogGroups hook for hierarchical display"
```

---

## Task 12: Create ActivityLogHeader Component

**Files:**
- Create: `dashboard/src/components/activity/ActivityLogHeader.tsx`
- Test: `dashboard/src/components/activity/__tests__/ActivityLogHeader.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/activity/__tests__/ActivityLogHeader.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ActivityLogHeader } from '../ActivityLogHeader';
import type { StageGroup } from '../types';

const makeGroup = (overrides: Partial<StageGroup> = {}): StageGroup => ({
  stage: 'architect',
  label: 'Planning (Architect)',
  events: [],
  isActive: false,
  isCompleted: false,
  startedAt: null,
  endedAt: null,
  ...overrides,
});

describe('ActivityLogHeader', () => {
  it('renders stage label', () => {
    render(
      <ActivityLogHeader
        group={makeGroup({ label: 'Planning (Architect)' })}
        isCollapsed={false}
        onToggle={() => {}}
      />
    );

    expect(screen.getByText('Planning (Architect)')).toBeInTheDocument();
  });

  it('shows event count', () => {
    render(
      <ActivityLogHeader
        group={makeGroup({ events: [{} as any, {} as any, {} as any] })}
        isCollapsed={false}
        onToggle={() => {}}
      />
    );

    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('calls onToggle when clicked', () => {
    const onToggle = vi.fn();
    render(
      <ActivityLogHeader
        group={makeGroup()}
        isCollapsed={false}
        onToggle={onToggle}
      />
    );

    fireEvent.click(screen.getByRole('button'));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('shows completed indicator when isCompleted', () => {
    render(
      <ActivityLogHeader
        group={makeGroup({ isCompleted: true })}
        isCollapsed={false}
        onToggle={() => {}}
      />
    );

    expect(screen.getByTestId('stage-completed')).toBeInTheDocument();
  });

  it('shows active indicator when isActive', () => {
    render(
      <ActivityLogHeader
        group={makeGroup({ isActive: true })}
        isCollapsed={false}
        onToggle={() => {}}
      />
    );

    expect(screen.getByTestId('stage-active')).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/components/activity/__tests__/ActivityLogHeader.test.tsx`
Expected: FAIL (component doesn't exist)

**Step 3: Write minimal implementation**

```typescript
// dashboard/src/components/activity/ActivityLogHeader.tsx
import { ChevronRight, ChevronDown, Check, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { StageGroup } from './types';

const AGENT_COLORS: Record<string, string> = {
  architect: 'text-blue-400',
  developer: 'text-green-400',
  reviewer: 'text-yellow-400',
};

interface ActivityLogHeaderProps {
  group: StageGroup;
  isCollapsed: boolean;
  onToggle: () => void;
}

export function ActivityLogHeader({
  group,
  isCollapsed,
  onToggle,
}: ActivityLogHeaderProps) {
  const color = AGENT_COLORS[group.stage] || 'text-muted-foreground';

  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        'w-full flex items-center gap-2 px-3 py-2',
        'bg-muted/50 hover:bg-muted/70 transition-colors',
        'border-b border-border/30 font-mono text-sm'
      )}
      aria-expanded={!isCollapsed}
    >
      {isCollapsed ? (
        <ChevronRight className="w-4 h-4 text-muted-foreground" />
      ) : (
        <ChevronDown className="w-4 h-4 text-muted-foreground" />
      )}

      <span className={cn('font-semibold', color)}>{group.label}</span>

      <span className="ml-auto flex items-center gap-2">
        <span className="text-muted-foreground tabular-nums">
          {group.events.length}
        </span>

        {group.isCompleted && (
          <Check
            className="w-4 h-4 text-green-500"
            data-testid="stage-completed"
          />
        )}

        {group.isActive && !group.isCompleted && (
          <Loader2
            className="w-4 h-4 text-primary animate-spin"
            data-testid="stage-active"
          />
        )}
      </span>
    </button>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/components/activity/__tests__/ActivityLogHeader.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/activity/ActivityLogHeader.tsx dashboard/src/components/activity/__tests__/ActivityLogHeader.test.tsx
git commit -m "feat(dashboard): add ActivityLogHeader component"
```

---

## Task 13: Move ActivityLogItem to ActivityLogEvent

**Files:**
- Create: `dashboard/src/components/activity/ActivityLogEvent.tsx` (copy from ActivityLogItem)
- Test: `dashboard/src/components/activity/__tests__/ActivityLogEvent.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/activity/__tests__/ActivityLogEvent.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ActivityLogEvent } from '../ActivityLogEvent';
import type { WorkflowEvent } from '@/types';

const makeEvent = (overrides: Partial<WorkflowEvent> = {}): WorkflowEvent => ({
  id: 'evt-1',
  workflow_id: 'wf-1',
  sequence: 1,
  timestamp: '2025-01-01T12:30:45Z',
  agent: 'developer',
  event_type: 'task_started',
  level: 'debug',
  message: 'Started implementation task',
  ...overrides,
});

describe('ActivityLogEvent', () => {
  it('renders event message', () => {
    render(<ActivityLogEvent event={makeEvent()} />);
    expect(screen.getByText('Started implementation task')).toBeInTheDocument();
  });

  it('renders formatted timestamp', () => {
    render(<ActivityLogEvent event={makeEvent()} />);
    // Should show time portion
    expect(screen.getByText(/12:30:45/)).toBeInTheDocument();
  });

  it('renders agent name', () => {
    render(<ActivityLogEvent event={makeEvent({ agent: 'architect' })} />);
    expect(screen.getByText('[ARCHITECT]')).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/components/activity/__tests__/ActivityLogEvent.test.tsx`
Expected: FAIL (component doesn't exist)

**Step 3: Write minimal implementation**

```typescript
// dashboard/src/components/activity/ActivityLogEvent.tsx
import { cn } from '@/lib/utils';
import type { WorkflowEvent } from '@/types';

const AGENT_STYLES: Record<string, { text: string; bg: string }> = {
  ARCHITECT: { text: 'text-blue-400', bg: '' },
  DEVELOPER: { text: 'text-green-400', bg: '' },
  REVIEWER: { text: 'text-yellow-400', bg: '' },
  SYSTEM: { text: 'text-muted-foreground', bg: '' },
};

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

interface ActivityLogEventProps {
  event: WorkflowEvent;
}

export function ActivityLogEvent({ event }: ActivityLogEventProps) {
  const agentKey = event.agent.toUpperCase();
  const style = AGENT_STYLES[agentKey] ?? AGENT_STYLES.SYSTEM;

  return (
    <div
      data-slot="activity-log-event"
      className={cn(
        'grid grid-cols-[100px_120px_1fr] gap-3 py-1.5 px-3',
        'border-b border-border/30 font-mono text-sm',
        style.bg
      )}
    >
      <span className="text-muted-foreground tabular-nums">
        {formatTime(event.timestamp)}
      </span>
      <span className={cn('font-semibold', style.text)}>
        [{agentKey}]
      </span>
      <span className="text-foreground/80 break-words">{event.message}</span>
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/components/activity/__tests__/ActivityLogEvent.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/activity/ActivityLogEvent.tsx dashboard/src/components/activity/__tests__/ActivityLogEvent.test.tsx
git commit -m "feat(dashboard): add ActivityLogEvent component"
```

---

## Task 14: Create Activity Index Export

**Files:**
- Create: `dashboard/src/components/activity/index.ts`

**Step 1: Create the barrel export**

```typescript
// dashboard/src/components/activity/index.ts
export { ActivityLogHeader } from './ActivityLogHeader';
export { ActivityLogEvent } from './ActivityLogEvent';
export { useActivityLogGroups } from './useActivityLogGroups';
export type { StageGroup, VirtualRow, AgentStage } from './types';
export { STAGE_ORDER, STAGE_LABELS } from './types';
```

**Step 2: Commit**

```bash
git add dashboard/src/components/activity/index.ts
git commit -m "feat(dashboard): add activity components barrel export"
```

---

## Task 15: Refactor ActivityLog with Virtualization

**Files:**
- Modify: `dashboard/src/components/ActivityLog.tsx`
- Test: `dashboard/src/components/__tests__/ActivityLog.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/components/__tests__/ActivityLog.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ActivityLog } from '../ActivityLog';
import type { WorkflowEvent } from '@/types';

// Mock the stores
vi.mock('@/store/workflowStore', () => ({
  useWorkflowStore: () => ({ eventsByWorkflow: {} }),
}));

const makeEvent = (overrides: Partial<WorkflowEvent>): WorkflowEvent => ({
  id: 'evt-1',
  workflow_id: 'wf-test',
  sequence: 1,
  timestamp: '2025-01-01T00:00:00Z',
  agent: 'developer',
  event_type: 'task_started',
  level: 'debug',
  message: 'Test event',
  ...overrides,
});

describe('ActivityLog', () => {
  it('renders stage headers', () => {
    const events = [
      makeEvent({ id: '1', agent: 'architect', event_type: 'stage_started', level: 'info' }),
    ];

    render(<ActivityLog workflowId="wf-test" initialEvents={events} />);

    expect(screen.getByText('Planning (Architect)')).toBeInTheDocument();
  });

  it('does not render trace events', () => {
    const events = [
      makeEvent({ id: '1', level: 'info', message: 'Info event' }),
      makeEvent({ id: '2', level: 'trace', message: 'Trace event', event_type: 'claude_tool_call' }),
    ];

    render(<ActivityLog workflowId="wf-test" initialEvents={events} />);

    expect(screen.getByText('Info event')).toBeInTheDocument();
    expect(screen.queryByText('Trace event')).not.toBeInTheDocument();
  });

  it('collapses stage when header clicked', () => {
    const events = [
      makeEvent({ id: '1', agent: 'architect', event_type: 'stage_started', level: 'info' }),
      makeEvent({ id: '2', agent: 'architect', message: 'Detail event', level: 'debug' }),
    ];

    render(<ActivityLog workflowId="wf-test" initialEvents={events} />);

    // Event should be visible initially
    expect(screen.getByText('Detail event')).toBeInTheDocument();

    // Click to collapse
    fireEvent.click(screen.getByText('Planning (Architect)'));

    // Event should be hidden
    expect(screen.queryByText('Detail event')).not.toBeInTheDocument();
  });

  it('does not have Live toggle', () => {
    render(<ActivityLog workflowId="wf-test" initialEvents={[]} />);

    expect(screen.queryByText(/live/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/components/__tests__/ActivityLog.test.tsx`
Expected: FAIL (old implementation still there)

**Step 3: Write minimal implementation**

Replace `dashboard/src/components/ActivityLog.tsx`:

```typescript
// dashboard/src/components/ActivityLog.tsx
import { useRef, useState, useMemo, useEffect } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useWorkflowStore } from '@/store/workflowStore';
import {
  ActivityLogHeader,
  ActivityLogEvent,
  useActivityLogGroups,
} from './activity';
import type { WorkflowEvent } from '@/types';

interface ActivityLogProps {
  workflowId: string;
  initialEvents?: WorkflowEvent[];
}

export function ActivityLog({
  workflowId,
  initialEvents = [],
}: ActivityLogProps) {
  const parentRef = useRef<HTMLDivElement>(null);
  const [collapsedStages, setCollapsedStages] = useState<Set<string>>(
    new Set()
  );

  // Get realtime events from store
  const { eventsByWorkflow } = useWorkflowStore();

  // Merge initial events with realtime events
  const allEvents = useMemo(() => {
    const realtimeEvents = eventsByWorkflow[workflowId] || [];
    const initialIds = new Set(initialEvents.map((e) => e.id));
    const newEvents = realtimeEvents.filter((e) => !initialIds.has(e.id));
    return [...initialEvents, ...newEvents];
  }, [initialEvents, eventsByWorkflow, workflowId]);

  // Group events by stage and flatten for virtualization
  const { rows } = useActivityLogGroups(allEvents, collapsedStages);

  // Virtualizer
  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: (index) => (rows[index].type === 'header' ? 44 : 36),
    overscan: 10,
  });

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (rows.length > 0 && parentRef.current) {
      rowVirtualizer.scrollToIndex(rows.length - 1, { behavior: 'smooth' });
    }
  }, [rows.length, rowVirtualizer]);

  const toggleStage = (stage: string) => {
    setCollapsedStages((prev) => {
      const next = new Set(prev);
      if (next.has(stage)) {
        next.delete(stage);
      } else {
        next.add(stage);
      }
      return next;
    });
  };

  if (rows.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground font-mono text-sm">
        No events yet
      </div>
    );
  }

  return (
    <div
      ref={parentRef}
      className="h-full overflow-auto"
      role="log"
      aria-live="polite"
    >
      <div
        style={{
          height: `${rowVirtualizer.getTotalSize()}px`,
          width: '100%',
          position: 'relative',
        }}
      >
        {rowVirtualizer.getVirtualItems().map((virtualRow) => {
          const row = rows[virtualRow.index];
          return (
            <div
              key={virtualRow.key}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: `${virtualRow.size}px`,
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              {row.type === 'header' ? (
                <ActivityLogHeader
                  group={row.group}
                  isCollapsed={collapsedStages.has(row.group.stage)}
                  onToggle={() => toggleStage(row.group.stage)}
                />
              ) : (
                <ActivityLogEvent event={row.event} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/components/__tests__/ActivityLog.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/ActivityLog.tsx dashboard/src/components/__tests__/ActivityLog.test.tsx
git commit -m "feat(dashboard): refactor ActivityLog with virtualization and stage grouping"
```

---

## Task 16: Update LogsPage with Virtualization

**Files:**
- Modify: `dashboard/src/pages/LogsPage.tsx`
- Test: `dashboard/src/pages/__tests__/LogsPage.test.tsx`

**Step 1: Write the failing test**

```typescript
// dashboard/src/pages/__tests__/LogsPage.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LogsPage } from '../LogsPage';

// Mock the stream store
vi.mock('@/store/stream-store', () => ({
  useStreamStore: () => ({
    events: [
      {
        id: '1',
        subtype: 'claude_tool_call',
        content: null,
        timestamp: '2025-01-01T00:00:00Z',
        agent: 'developer',
        workflow_id: 'wf-1',
        tool_name: 'Edit',
        tool_input: { file: 'test.py' },
      },
    ],
    liveMode: true,
    setLiveMode: vi.fn(),
    clearEvents: vi.fn(),
  }),
}));

describe('LogsPage', () => {
  it('renders trace events header', () => {
    render(<LogsPage />);
    expect(screen.getByText(/trace/i)).toBeInTheDocument();
  });

  it('renders stream events', () => {
    render(<LogsPage />);
    expect(screen.getByText(/Edit/)).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/pages/__tests__/LogsPage.test.tsx`
Expected: May pass or fail depending on current implementation

**Step 3: Update implementation with virtualization**

Update `dashboard/src/pages/LogsPage.tsx` to add virtualization (keeping existing filter logic):

```typescript
// dashboard/src/pages/LogsPage.tsx
import { useRef, useMemo } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { Zap, Trash2 } from 'lucide-react';
import { useStreamStore } from '@/store/stream-store';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { StreamEvent } from '@/types';

// ... keep existing filter UI and StreamLogItem component ...

export function LogsPage() {
  const parentRef = useRef<HTMLDivElement>(null);
  const { events, liveMode, setLiveMode, clearEvents } = useStreamStore();

  // ... keep existing filter state and logic ...

  const filteredEvents = useMemo(() => {
    // ... existing filter logic ...
    return events; // or filtered version
  }, [events /* , filters */]);

  const rowVirtualizer = useVirtualizer({
    count: filteredEvents.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 40,
    overscan: 10,
  });

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-2">
          <Zap className="w-5 h-5 text-primary" />
          <h1 className="text-lg font-semibold">Trace Events</h1>
          <span className="text-sm text-muted-foreground">
            ({filteredEvents.length} events)
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* ... existing filter controls ... */}
          <Button variant="outline" size="sm" onClick={clearEvents}>
            <Trash2 className="w-4 h-4 mr-1" />
            Clear
          </Button>
        </div>
      </div>

      {/* Virtualized event list */}
      <div ref={parentRef} className="flex-1 overflow-auto">
        <div
          style={{
            height: `${rowVirtualizer.getTotalSize()}px`,
            width: '100%',
            position: 'relative',
          }}
        >
          {rowVirtualizer.getVirtualItems().map((virtualRow) => {
            const event = filteredEvents[virtualRow.index];
            return (
              <div
                key={virtualRow.key}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: `${virtualRow.size}px`,
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              >
                <StreamLogItem event={event} />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/pages/__tests__/LogsPage.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/pages/LogsPage.tsx dashboard/src/pages/__tests__/LogsPage.test.tsx
git commit -m "feat(dashboard): add virtualization to LogsPage"
```

---

## Task 17: Clean Up Old ActivityLogItem

**Files:**
- Delete: `dashboard/src/components/ActivityLogItem.tsx` (if not used elsewhere)
- Update any imports to use new activity/ActivityLogEvent

**Step 1: Search for usages**

Run: `cd dashboard && grep -r "ActivityLogItem" src/`

**Step 2: Update imports or delete file**

If only used in old ActivityLog, delete the file and update any remaining imports.

**Step 3: Commit**

```bash
git rm dashboard/src/components/ActivityLogItem.tsx
git commit -m "chore(dashboard): remove old ActivityLogItem component"
```

---

## Task 18: Run Full Test Suite

**Step 1: Run backend tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 2: Run frontend tests**

Run: `cd dashboard && pnpm test:run`
Expected: All tests PASS

**Step 3: Run linters**

Run: `uv run ruff check amelia tests && uv run mypy amelia`
Run: `cd dashboard && pnpm lint && pnpm type-check`
Expected: No errors

**Step 4: Final commit**

```bash
git add -A
git commit -m "test: verify all tests pass after unified events refactoring"
```

---

## Task 19: Remove Backend StreamEvent Infrastructure

**Files:**
- Modify: `amelia/core/types.py`
- Modify: `amelia/core/__init__.py`
- Modify: `amelia/server/models/events.py`

**Step 1: Remove StreamEvent types from core/types.py**

Delete the following from `amelia/core/types.py`:
- `StreamEventType` enum (lines ~133-139)
- `StreamEvent` class (lines ~142-164)
- `StreamEmitter` type alias (line ~167)

**Step 2: Remove exports from core/__init__.py**

Remove these exports from `amelia/core/__init__.py`:
```python
# Remove these lines:
StreamEmitter,
StreamEvent,
StreamEventType,
```

**Step 3: Remove StreamEventPayload from models/events.py**

Delete the `StreamEventPayload` class from `amelia/server/models/events.py` (lines ~134-161).

**Step 4: Run tests to verify imports are cleaned up**

Run: `uv run pytest tests/unit/server/models/ -v`
Expected: May have import errors that need fixing in subsequent tasks

**Step 5: Commit**

```bash
git add amelia/core/types.py amelia/core/__init__.py amelia/server/models/events.py
git commit -m "chore(events): remove StreamEvent types from core"
```

---

## Task 20: Consolidate EventBus emit Methods

**Files:**
- Modify: `amelia/server/events/bus.py`
- Test: `tests/unit/server/events/test_bus.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/server/events/test_bus.py

class TestEventBusTraceEvents:
    """Tests for trace event handling in unified emit."""

    @pytest.mark.asyncio
    async def test_emit_broadcasts_trace_events(self) -> None:
        """emit() broadcasts trace-level events to WebSocket."""
        bus = EventBus()
        mock_manager = AsyncMock()
        bus.set_connection_manager(mock_manager)

        trace_event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.CLAUDE_TOOL_CALL,
            level=EventLevel.TRACE,
            message="Tool call: Edit",
            tool_name="Edit",
        )

        bus.emit(trace_event)
        await bus.wait_for_broadcasts()

        mock_manager.broadcast.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_trace_skips_persistence_when_disabled(self) -> None:
        """emit() skips subscriber notification for trace events when retention=0."""
        bus = EventBus()
        bus.configure(trace_retention_days=0)
        captured = []
        bus.subscribe(lambda e: captured.append(e))

        trace_event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.CLAUDE_TOOL_CALL,
            level=EventLevel.TRACE,
            message="Tool call",
        )

        bus.emit(trace_event)

        assert len(captured) == 0  # Not persisted
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/events/test_bus.py::TestEventBusTraceEvents -v`
Expected: FAIL (emit doesn't handle trace events specially yet)

**Step 3: Update EventBus.emit() to handle trace events**

Update `amelia/server/events/bus.py`:

```python
def emit(self, event: WorkflowEvent) -> None:
    """Emit event to subscribers and broadcast to WebSocket clients.

    For trace-level events:
    - Skips persistence (subscriber notification) if trace_retention_days=0
    - Always broadcasts to WebSocket for real-time UI
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
                logger.exception("Subscriber raised exception", error=str(exc))

    # Always broadcast to WebSocket
    if self._connection_manager:
        task = asyncio.create_task(
            self._connection_manager.broadcast(event)
        )
        self._broadcast_tasks.add(task)
        task.add_done_callback(self._handle_broadcast_done)
```

**Step 4: Remove emit_stream() method**

Delete the `emit_stream()` method entirely from `EventBus`.

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/events/test_bus.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/events/bus.py tests/unit/server/events/test_bus.py
git commit -m "feat(events): consolidate emit_stream into emit with trace handling"
```

---

## Task 21: Consolidate ConnectionManager broadcast Methods

**Files:**
- Modify: `amelia/server/events/connection_manager.py`
- Test: `tests/unit/server/events/test_connection_manager.py`

**Step 1: Write the failing test**

```python
# Add to tests/unit/server/events/test_connection_manager.py

class TestConnectionManagerTraceEvents:
    """Tests for trace event broadcasting."""

    @pytest.mark.asyncio
    async def test_broadcast_sends_trace_events_to_all_clients(self) -> None:
        """broadcast() sends trace events to all connected clients (no filtering)."""
        manager = ConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await manager.connect(mock_ws1, workflow_id="wf-1")
        await manager.connect(mock_ws2, workflow_id="wf-2")

        trace_event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.CLAUDE_TOOL_CALL,
            level=EventLevel.TRACE,
            message="Tool call",
        )

        await manager.broadcast(trace_event)

        # Both clients receive trace events (no workflow filtering)
        assert mock_ws1.send_json.called
        assert mock_ws2.send_json.called
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/events/test_connection_manager.py::TestConnectionManagerTraceEvents -v`
Expected: FAIL (trace events are filtered by workflow)

**Step 3: Update broadcast() to handle trace events**

Update `amelia/server/events/connection_manager.py`:

```python
async def broadcast(self, event: WorkflowEvent) -> None:
    """Broadcast event to connected WebSocket clients.

    For trace-level events: broadcasts to ALL clients (no workflow filtering)
    For other events: broadcasts only to clients subscribed to the workflow
    """
    if not self._connections:
        return

    is_trace = event.level == EventLevel.TRACE
    payload = {"type": "event", "payload": event.model_dump(mode="json")}

    async def send_to_client(ws: WebSocket) -> None:
        try:
            await asyncio.wait_for(ws.send_json(payload), timeout=5.0)
        except Exception as exc:
            logger.warning("Failed to send to client", error=str(exc))

    if is_trace:
        # Trace events go to ALL clients
        await asyncio.gather(
            *(send_to_client(ws) for ws in self._connections.keys()),
            return_exceptions=True,
        )
    else:
        # Regular events filtered by workflow subscription
        for ws, subscriptions in self._connections.items():
            if event.workflow_id in subscriptions or "*" in subscriptions:
                await send_to_client(ws)
```

**Step 4: Remove broadcast_stream() method**

Delete the `broadcast_stream()` method entirely from `ConnectionManager`.

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/events/test_connection_manager.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/events/connection_manager.py tests/unit/server/events/test_connection_manager.py
git commit -m "feat(events): consolidate broadcast_stream into broadcast with trace handling"
```

---

## Task 22: Update Agent Stream Emission

**Files:**
- Modify: `amelia/drivers/base.py`
- Modify: `amelia/agents/architect.py`
- Modify: `amelia/agents/developer.py`
- Modify: `amelia/agents/reviewer.py`
- Modify: `amelia/agents/evaluator.py`
- Modify: `amelia/server/orchestrator/service.py`

**Step 1: Update AgenticMessage.to_stream_event() → to_workflow_event()**

In `amelia/drivers/base.py`, rename and update the method:

```python
def to_workflow_event(
    self,
    workflow_id: str,
    agent: str,
    sequence: int = 0,
) -> WorkflowEvent:
    """Convert agentic message to WorkflowEvent for emission.

    Args:
        workflow_id: The workflow this event belongs to.
        agent: The agent that generated this message.
        sequence: Event sequence number (0 = will be assigned later).

    Returns:
        WorkflowEvent with trace level.
    """
    from amelia.server.models.events import EventType, EventLevel, WorkflowEvent

    type_mapping = {
        AgenticMessageType.THINKING: EventType.CLAUDE_THINKING,
        AgenticMessageType.TOOL_CALL: EventType.CLAUDE_TOOL_CALL,
        AgenticMessageType.TOOL_RESULT: EventType.CLAUDE_TOOL_RESULT,
        AgenticMessageType.OUTPUT: EventType.AGENT_OUTPUT,
    }

    message = self._build_message()

    return WorkflowEvent(
        id=str(uuid4()),
        workflow_id=workflow_id,
        sequence=sequence,
        timestamp=datetime.now(UTC),
        agent=agent,
        event_type=type_mapping[self.type],
        level=EventLevel.TRACE,
        message=message,
        tool_name=self.tool_name,
        tool_input=self.tool_input,
        is_error=self.is_error,
    )
```

**Step 2: Update all agents to use to_workflow_event()**

In each agent file, replace calls like:
```python
await stream_emitter(message.to_stream_event(workflow_id, agent_name))
```

With:
```python
event_bus.emit(message.to_workflow_event(workflow_id, agent_name))
```

**Step 3: Remove _create_stream_emitter() from OrchestratorService**

In `amelia/server/orchestrator/service.py`:
- Delete the `_create_stream_emitter()` method
- Update agent config to pass `event_bus` directly instead of `stream_emitter`

**Step 4: Run tests**

Run: `uv run pytest tests/unit/agents/ -v`
Expected: Some failures that need fixing

**Step 5: Fix broken tests**

Update agent tests to expect `to_workflow_event()` calls instead of `to_stream_event()`.

**Step 6: Commit**

```bash
git add amelia/drivers/base.py amelia/agents/*.py amelia/server/orchestrator/service.py
git commit -m "feat(agents): update to emit WorkflowEvent instead of StreamEvent"
```

---

## Task 23: Delete Obsolete Backend Tests

**Files:**
- Delete: `tests/unit/core/test_stream_types.py`
- Delete: `tests/unit/server/events/test_bus_stream.py`
- Delete: `tests/unit/server/events/test_connection_manager_stream.py`
- Delete: `tests/integration/test_stream_propagation.py`
- Modify: `tests/conftest.py`

**Step 1: Delete obsolete test files**

```bash
rm tests/unit/core/test_stream_types.py
rm tests/unit/server/events/test_bus_stream.py
rm tests/unit/server/events/test_connection_manager_stream.py
rm tests/integration/test_stream_propagation.py
```

**Step 2: Remove sample_stream_event fixture from conftest.py**

In `tests/conftest.py`, delete the `sample_stream_event` fixture (lines ~180-188).

**Step 3: Run tests to verify nothing is broken**

Run: `uv run pytest tests/ -v --ignore=tests/e2e`
Expected: PASS (no import errors from deleted files)

**Step 4: Commit**

```bash
git rm tests/unit/core/test_stream_types.py
git rm tests/unit/server/events/test_bus_stream.py
git rm tests/unit/server/events/test_connection_manager_stream.py
git rm tests/integration/test_stream_propagation.py
git add tests/conftest.py
git commit -m "chore(tests): remove obsolete StreamEvent tests"
```

---

## Task 24: Remove Frontend StreamEvent Types

**Files:**
- Modify: `dashboard/src/types/index.ts`

**Step 1: Remove StreamEvent types**

In `dashboard/src/types/index.ts`:

1. Delete `StreamEventType` enum (lines ~439-447)
2. Delete `StreamEvent` interface (lines ~481-505)
3. Update `WebSocketMessage` type to remove `'stream'` variant:

```typescript
// Before:
export type WebSocketMessage =
  | { type: 'event'; payload: WorkflowEvent }
  | { type: 'stream'; payload: StreamEvent }
  | { type: 'error'; payload: { message: string } };

// After:
export type WebSocketMessage =
  | { type: 'event'; payload: WorkflowEvent }
  | { type: 'error'; payload: { message: string } };
```

**Step 2: Run type check**

Run: `cd dashboard && pnpm type-check`
Expected: Errors pointing to files that still use StreamEvent (to be fixed in next tasks)

**Step 3: Commit**

```bash
git add dashboard/src/types/index.ts
git commit -m "chore(dashboard): remove StreamEvent types"
```

---

## Task 25: Remove Stream Store

**Files:**
- Delete: `dashboard/src/store/stream-store.ts`
- Delete: `dashboard/src/store/__tests__/stream-store.test.ts`

**Step 1: Delete stream store files**

```bash
rm dashboard/src/store/stream-store.ts
rm dashboard/src/store/__tests__/stream-store.test.ts
```

**Step 2: Update any imports**

Search for imports and remove them:
```bash
cd dashboard && grep -r "stream-store" src/
```

Remove imports from:
- `useWebSocket.ts`
- Any other files referencing the stream store

**Step 3: Run type check**

Run: `cd dashboard && pnpm type-check`
Expected: More errors to fix in subsequent tasks

**Step 4: Commit**

```bash
git rm dashboard/src/store/stream-store.ts
git rm dashboard/src/store/__tests__/stream-store.test.ts
git commit -m "chore(dashboard): remove stream store"
```

---

## Task 26: Update WebSocket Hook

**Files:**
- Modify: `dashboard/src/hooks/useWebSocket.ts`
- Test: `dashboard/src/hooks/__tests__/useWebSocket.test.tsx`

**Step 1: Remove stream event handling**

In `dashboard/src/hooks/useWebSocket.ts`:

1. Remove `addStreamEvent` import from stream-store
2. Remove the `'stream'` case from the message handler:

```typescript
// Remove this case:
case 'stream':
  addStreamEvent(message.payload);
  break;
```

**Step 2: Update tests**

In `dashboard/src/hooks/__tests__/useWebSocket.test.tsx`:
- Remove tests for stream event handling (lines ~294-393)
- Remove stream store mocks

**Step 3: Run tests**

Run: `cd dashboard && pnpm test src/hooks/__tests__/useWebSocket.test.tsx`
Expected: PASS

**Step 4: Commit**

```bash
git add dashboard/src/hooks/useWebSocket.ts dashboard/src/hooks/__tests__/useWebSocket.test.tsx
git commit -m "chore(dashboard): remove stream event handling from WebSocket hook"
```

---

## Task 27: Clean Up Test Fixtures

**Files:**
- Modify: `dashboard/src/__tests__/fixtures.ts`
- Update: Various test files using `createMockStreamEvent`

**Step 1: Remove createMockStreamEvent**

In `dashboard/src/__tests__/fixtures.ts`, delete the `createMockStreamEvent()` function (lines ~170-184).

**Step 2: Search for usages and update tests**

```bash
cd dashboard && grep -r "createMockStreamEvent" src/
```

Update any test files still using this function to use `createMockEvent()` with trace-level fields instead.

**Step 3: Run all frontend tests**

Run: `cd dashboard && pnpm test:run`
Expected: PASS

**Step 4: Commit**

```bash
git add dashboard/src/__tests__/fixtures.ts
git commit -m "chore(dashboard): remove createMockStreamEvent fixture"
```

---

## Task 28: Final Verification

**Step 1: Run full backend test suite**

Run: `uv run pytest tests/ -v --ignore=tests/e2e`
Expected: All tests PASS

**Step 2: Run full frontend test suite**

Run: `cd dashboard && pnpm test:run`
Expected: All tests PASS

**Step 3: Run linters and type checks**

Run: `uv run ruff check amelia tests && uv run mypy amelia`
Run: `cd dashboard && pnpm lint && pnpm type-check`
Expected: No errors

**Step 4: Search for any remaining StreamEvent references**

```bash
grep -r "StreamEvent" amelia/ tests/ dashboard/src/ --include="*.py" --include="*.ts" --include="*.tsx"
grep -r "emit_stream" amelia/ tests/
grep -r "broadcast_stream" amelia/ tests/
grep -r "stream-store" dashboard/src/
```

Expected: No results (all cleaned up)

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: complete unified events cleanup - remove all StreamEvent remnants"
```

---

## Summary

This plan implements unified events in 28 tasks:

| Phase | Tasks | Description |
|-------|-------|-------------|
| **Foundation** | 1-7 | Add EventLevel, extend WorkflowEvent, update database, repository, config, retention |
| **Frontend Types** | 8-14 | Add frontend types, virtualization, activity components |
| **Refactor Components** | 15-17 | Refactor ActivityLog, LogsPage, clean up old components |
| **Verify** | 18 | Run full test suite |
| **Backend Cleanup** | 19-23 | Remove StreamEvent infrastructure, consolidate emit/broadcast, update agents |
| **Frontend Cleanup** | 24-27 | Remove stream types, store, WebSocket handling, fixtures |
| **Final Verification** | 28 | Complete verification and cleanup |

**Execution Options:**

**1. Subagent-Driven (this session)** - Dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?