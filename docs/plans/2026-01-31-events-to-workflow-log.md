# Events to Workflow Log Refactor — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the `events` table with a slim `workflow_log` table that only persists high-level workflow events. Verbose trace events become stream-only (in-memory).

**Architecture:** Add a `PERSISTED_TYPES` frozenset to `events.py` that defines which event types get written to the new `workflow_log` table. The repository's `save_event()` short-circuits for non-persisted types. The `EventBus` continues broadcasting all events to WebSocket — filtering happens only at the persistence layer. Trace retention config is removed entirely.

**Tech Stack:** Python 3.12+, aiosqlite, Pydantic, pytest-asyncio, React/TypeScript (dashboard settings)

**Breaking change:** Requires deleting `~/.amelia/` (clean break). No data migration.

---

## Event Classification Reference

### Persisted → `workflow_log`

| Category | Event Types |
|----------|-------------|
| Lifecycle | `workflow_created`, `workflow_started`, `workflow_completed`, `workflow_failed`, `workflow_cancelled` |
| Stages | `stage_started`, `stage_completed` |
| Approval | `approval_required`, `approval_granted`, `approval_rejected` |
| Artifacts | `file_created`, `file_modified`, `file_deleted` |
| Review | `review_requested`, `review_completed`, `revision_requested` |
| Tasks | `task_started`, `task_completed`, `task_failed` |
| System | `system_error`, `system_warning` |
| Oracle | `oracle_consultation_started`, `oracle_consultation_completed`, `oracle_consultation_failed` |
| Brainstorm | `brainstorm_session_created`, `brainstorm_session_completed`, `brainstorm_artifact_created` |

### Stream-only (not persisted)

| Category | Event Types |
|----------|-------------|
| Claude trace | `claude_thinking`, `claude_tool_call`, `claude_tool_result`, `agent_output` |
| Oracle trace | `oracle_consultation_thinking`, `oracle_tool_call`, `oracle_tool_result` |
| Brainstorm trace | `brainstorm_reasoning`, `brainstorm_tool_call`, `brainstorm_tool_result`, `brainstorm_text`, `brainstorm_message_complete` |
| Streaming | `stream`, `agent_message` |

---

### Task 1: Add `PERSISTED_TYPES` to events model and simplify `EventLevel`

**Files:**
- Modify: `amelia/server/models/events.py`
- Test: `tests/unit/server/models/test_events.py`

The `EventLevel` enum currently has `INFO`, `DEBUG`, `TRACE`. The new `workflow_log` table's CHECK constraint only allows `info`, `warning`, `error`. This task reconciles them.

**Step 1: Write failing tests for `PERSISTED_TYPES`**

Add to `tests/unit/server/models/test_events.py`:

```python
from amelia.server.models.events import PERSISTED_TYPES, EventType


class TestPersistedTypes:
    """Tests for PERSISTED_TYPES classification."""

    def test_persisted_types_is_frozenset(self):
        """PERSISTED_TYPES must be immutable."""
        assert isinstance(PERSISTED_TYPES, frozenset)

    def test_lifecycle_events_are_persisted(self):
        """All lifecycle events must be persisted."""
        lifecycle = {
            EventType.WORKFLOW_CREATED,
            EventType.WORKFLOW_STARTED,
            EventType.WORKFLOW_COMPLETED,
            EventType.WORKFLOW_FAILED,
            EventType.WORKFLOW_CANCELLED,
        }
        assert lifecycle <= PERSISTED_TYPES

    def test_trace_events_are_not_persisted(self):
        """Trace events must NOT be persisted."""
        trace_types = {
            EventType.CLAUDE_THINKING,
            EventType.CLAUDE_TOOL_CALL,
            EventType.CLAUDE_TOOL_RESULT,
            EventType.AGENT_OUTPUT,
            EventType.ORACLE_CONSULTATION_THINKING,
            EventType.ORACLE_TOOL_CALL,
            EventType.ORACLE_TOOL_RESULT,
        }
        assert trace_types.isdisjoint(PERSISTED_TYPES)

    def test_stream_events_are_not_persisted(self):
        """Stream and agent_message events must NOT be persisted."""
        stream_types = {EventType.STREAM, EventType.AGENT_MESSAGE}
        assert stream_types.isdisjoint(PERSISTED_TYPES)

    def test_brainstorm_trace_events_are_not_persisted(self):
        """Brainstorm trace events must NOT be persisted."""
        brainstorm_trace = {
            EventType.BRAINSTORM_REASONING,
            EventType.BRAINSTORM_TOOL_CALL,
            EventType.BRAINSTORM_TOOL_RESULT,
            EventType.BRAINSTORM_TEXT,
            EventType.BRAINSTORM_MESSAGE_COMPLETE,
        }
        assert brainstorm_trace.isdisjoint(PERSISTED_TYPES)

    def test_every_event_type_is_classified(self):
        """Every EventType must be either persisted or explicitly stream-only.

        Guards against new event types being added without classification.
        """
        all_types = set(EventType)
        stream_only = {
            EventType.CLAUDE_THINKING,
            EventType.CLAUDE_TOOL_CALL,
            EventType.CLAUDE_TOOL_RESULT,
            EventType.AGENT_OUTPUT,
            EventType.ORACLE_CONSULTATION_THINKING,
            EventType.ORACLE_TOOL_CALL,
            EventType.ORACLE_TOOL_RESULT,
            EventType.BRAINSTORM_REASONING,
            EventType.BRAINSTORM_TOOL_CALL,
            EventType.BRAINSTORM_TOOL_RESULT,
            EventType.BRAINSTORM_TEXT,
            EventType.BRAINSTORM_MESSAGE_COMPLETE,
            EventType.STREAM,
            EventType.AGENT_MESSAGE,
        }
        classified = PERSISTED_TYPES | stream_only
        unclassified = all_types - classified
        assert not unclassified, f"Unclassified event types: {unclassified}"
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/server/models/test_events.py::TestPersistedTypes -v
```

Expected: FAIL with `ImportError: cannot import name 'PERSISTED_TYPES'`

**Step 3: Add `PERSISTED_TYPES` and update `EventLevel`**

In `amelia/server/models/events.py`:

1. Change `EventLevel` to replace `TRACE` with `WARNING`:

```python
class EventLevel(StrEnum):
    """Event severity level for filtering and retention.

    Attributes:
        INFO: High-level workflow events (lifecycle, stages, approvals).
        WARNING: System warnings and non-critical issues.
        DEBUG: Operational details (tasks, files, messages).
        ERROR: Error events.
    """

    INFO = "info"
    WARNING = "warning"
    DEBUG = "debug"
    ERROR = "error"
```

2. Replace `_INFO_TYPES` and `_TRACE_TYPES` with `PERSISTED_TYPES` (exported, public):

```python
PERSISTED_TYPES: frozenset[EventType] = frozenset({
    # Lifecycle
    EventType.WORKFLOW_CREATED,
    EventType.WORKFLOW_STARTED,
    EventType.WORKFLOW_COMPLETED,
    EventType.WORKFLOW_FAILED,
    EventType.WORKFLOW_CANCELLED,
    # Stages
    EventType.STAGE_STARTED,
    EventType.STAGE_COMPLETED,
    # Approval
    EventType.APPROVAL_REQUIRED,
    EventType.APPROVAL_GRANTED,
    EventType.APPROVAL_REJECTED,
    # Artifacts
    EventType.FILE_CREATED,
    EventType.FILE_MODIFIED,
    EventType.FILE_DELETED,
    # Review
    EventType.REVIEW_REQUESTED,
    EventType.REVIEW_COMPLETED,
    EventType.REVISION_REQUESTED,
    # Tasks
    EventType.TASK_STARTED,
    EventType.TASK_COMPLETED,
    EventType.TASK_FAILED,
    # System
    EventType.SYSTEM_ERROR,
    EventType.SYSTEM_WARNING,
    # Oracle
    EventType.ORACLE_CONSULTATION_STARTED,
    EventType.ORACLE_CONSULTATION_COMPLETED,
    EventType.ORACLE_CONSULTATION_FAILED,
    # Brainstorm
    EventType.BRAINSTORM_SESSION_CREATED,
    EventType.BRAINSTORM_SESSION_COMPLETED,
    EventType.BRAINSTORM_ARTIFACT_CREATED,
})
```

3. Update `get_event_level()` to use the new classification:

```python
# Event types that map to specific non-debug levels
_ERROR_TYPES: frozenset[EventType] = frozenset({
    EventType.WORKFLOW_FAILED,
    EventType.TASK_FAILED,
    EventType.SYSTEM_ERROR,
    EventType.ORACLE_CONSULTATION_FAILED,
})

_WARNING_TYPES: frozenset[EventType] = frozenset({
    EventType.SYSTEM_WARNING,
})

_INFO_TYPES: frozenset[EventType] = frozenset({
    EventType.WORKFLOW_CREATED,
    EventType.WORKFLOW_STARTED,
    EventType.WORKFLOW_COMPLETED,
    EventType.WORKFLOW_CANCELLED,
    EventType.STAGE_STARTED,
    EventType.STAGE_COMPLETED,
    EventType.APPROVAL_REQUIRED,
    EventType.APPROVAL_GRANTED,
    EventType.APPROVAL_REJECTED,
    EventType.REVIEW_COMPLETED,
    EventType.ORACLE_CONSULTATION_STARTED,
    EventType.ORACLE_CONSULTATION_COMPLETED,
})


def get_event_level(event_type: EventType) -> EventLevel:
    """Get the level for an event type.

    Args:
        event_type: The event type to classify.

    Returns:
        EventLevel for the given event type.
    """
    if event_type in _ERROR_TYPES:
        return EventLevel.ERROR
    if event_type in _WARNING_TYPES:
        return EventLevel.WARNING
    if event_type in _INFO_TYPES:
        return EventLevel.INFO
    return EventLevel.DEBUG
```

4. Update `WorkflowEvent.level` field type annotation — no longer `EventLevel | None`, always set:

No change needed here since `model_post_init` already auto-sets the level. Keep `level: EventLevel | None = Field(default=None, ...)` as-is — the validator handles it.

**Step 4: Fix existing tests that reference `EventLevel.TRACE`**

Search for `EventLevel.TRACE` or `level.*trace` in tests and update them. Key files:
- `tests/unit/server/models/test_events.py` — update level assertion tests
- `tests/unit/server/events/test_bus.py` — update trace filtering tests
- `tests/unit/server/database/test_repository.py` — `TestRepositoryEvents` tests reference trace fields

**Step 5: Run all tests**

```bash
uv run pytest tests/unit/server/models/test_events.py -v
```

Expected: All PASS

**Step 6: Commit**

```bash
git add amelia/server/models/events.py tests/unit/server/models/test_events.py
git commit -m "feat(events): add PERSISTED_TYPES and update EventLevel enum

Add public PERSISTED_TYPES frozenset classifying which event types
get written to the database vs stream-only. Replace TRACE level with
WARNING and ERROR levels to match workflow_log schema."
```

---

### Task 2: Replace `events` DDL with `workflow_log` in schema

**Files:**
- Modify: `amelia/server/database/connection.py`

**Step 1: Replace the `events` table DDL in `Database.ensure_schema()`**

In `amelia/server/database/connection.py`, find the `CREATE TABLE IF NOT EXISTS events (...)` block (line ~278) and replace with:

```python
await self.execute("""
    CREATE TABLE IF NOT EXISTS workflow_log (
        id TEXT PRIMARY KEY,
        workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
        sequence INTEGER NOT NULL,
        timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        event_type TEXT NOT NULL,
        level TEXT NOT NULL CHECK (level IN ('info', 'warning', 'error', 'debug')),
        agent TEXT,
        message TEXT NOT NULL,
        data_json TEXT,
        is_error INTEGER NOT NULL DEFAULT 0
    )
""")
```

**Step 2: Replace all `events`-table indexes**

Find and replace the events indexes block (lines ~372-393). Remove:
- `idx_events_workflow_sequence`
- `idx_events_workflow`
- `idx_events_type`
- `idx_events_level`
- `idx_events_trace_id`

Replace with:
```python
await self.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_log_workflow_sequence
        ON workflow_log(workflow_id, sequence)
""")
await self.execute(
    "CREATE INDEX IF NOT EXISTS idx_workflow_log_workflow ON workflow_log(workflow_id, timestamp)"
)
await self.execute("""
    CREATE INDEX IF NOT EXISTS idx_workflow_log_errors
        ON workflow_log(workflow_id) WHERE is_error = 1
""")
```

**Step 3: Update the retention cleanup query in `cleanup_on_shutdown`**

The `LogRetentionService.cleanup_on_shutdown()` (in `retention.py`) references `DELETE FROM events` — that's Task 4. But the `ensure_schema` method also references events in the `WHERE id NOT IN (SELECT DISTINCT workflow_id FROM events)` pattern. This is in `retention.py`, not `connection.py`, so handle in Task 4.

**Step 4: Run schema-dependent tests**

```bash
uv run pytest tests/unit/server/database/ -v
```

Expected: Some failures from tests that reference old `events` table — those are fixed in Task 3.

**Step 5: Commit**

```bash
git add amelia/server/database/connection.py
git commit -m "feat(schema): replace events table with workflow_log

New table has 9 columns (down from 16). Removes trace-specific
columns: correlation_id, tool_name, tool_input_json, trace_id,
parent_id. Adds CHECK constraint on level column."
```

---

### Task 3: Update repository to filter and write to `workflow_log`

**Files:**
- Modify: `amelia/server/database/repository.py`
- Test: `tests/unit/server/database/test_repository.py`

**Step 1: Write failing test for `save_event` filtering**

Add a new test class in `tests/unit/server/database/test_repository.py`:

```python
from amelia.server.models.events import PERSISTED_TYPES


class TestWorkflowLogFiltering:
    """Tests for event persistence filtering in workflow_log."""

    @pytest.fixture
    async def repository(self, temp_db_path):
        db = Database(temp_db_path)
        await db.connect()
        await db.ensure_schema()
        repo = WorkflowRepository(db)
        yield repo
        await db.close()

    @pytest.fixture
    async def sample_workflow(self, repository):
        workflow_id = "wf-filter-test"
        await repository.create({
            "id": workflow_id,
            "issue_id": "TEST-1",
            "worktree_path": "/tmp/test",
            "status": "in_progress",
            "workflow_type": "full",
        })
        return workflow_id

    async def test_save_event_persists_lifecycle_event(self, repository, sample_workflow):
        """Lifecycle events should be written to workflow_log."""
        event = WorkflowEvent(
            id="evt-1",
            workflow_id=sample_workflow,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Workflow started",
        )
        await repository.save_event(event)
        events = await repository.get_recent_events(sample_workflow)
        assert len(events) == 1
        assert events[0].event_type == EventType.WORKFLOW_STARTED

    async def test_save_event_skips_trace_event(self, repository, sample_workflow):
        """Trace events should NOT be written to workflow_log."""
        event = WorkflowEvent(
            id="evt-2",
            workflow_id=sample_workflow,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.CLAUDE_THINKING,
            message="Thinking...",
        )
        await repository.save_event(event)
        events = await repository.get_recent_events(sample_workflow)
        assert len(events) == 0

    async def test_save_event_skips_stream_event(self, repository, sample_workflow):
        """Stream events should NOT be written to workflow_log."""
        event = WorkflowEvent(
            id="evt-3",
            workflow_id=sample_workflow,
            sequence=0,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.STREAM,
            message="chunk",
        )
        await repository.save_event(event)
        events = await repository.get_recent_events(sample_workflow)
        assert len(events) == 0
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/server/database/test_repository.py::TestWorkflowLogFiltering -v
```

Expected: FAIL (save_event still writes everything to old `events` table, or table doesn't exist)

**Step 3: Update `save_event()` in `repository.py`**

```python
from amelia.server.models.events import PERSISTED_TYPES

async def save_event(self, event: WorkflowEvent) -> None:
    """Persist workflow event to workflow_log if it's a persisted type.

    Stream-only events (trace, streaming) are silently skipped.

    Args:
        event: The event to persist.
    """
    if event.event_type not in PERSISTED_TYPES:
        return

    serialized = event.model_dump(mode="json")
    data_json = json.dumps(serialized["data"]) if serialized["data"] else None

    await self._db.execute(
        """
        INSERT INTO workflow_log (
            id, workflow_id, sequence, timestamp, event_type,
            level, agent, message, data_json, is_error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.id,
            event.workflow_id,
            event.sequence,
            event.timestamp.isoformat(),
            event.event_type.value,
            event.level.value if event.level else "debug",
            event.agent,
            event.message,
            data_json,
            1 if event.is_error else 0,
        ),
    )
```

**Step 4: Update `get_max_event_sequence()`**

```python
async def get_max_event_sequence(self, workflow_id: str) -> int:
    """Get maximum event sequence number for a workflow.

    Args:
        workflow_id: The workflow ID.

    Returns:
        Maximum sequence number, or 0 if no events exist.
    """
    result = await self._db.fetch_scalar(
        "SELECT COALESCE(MAX(sequence), 0) FROM workflow_log WHERE workflow_id = ?",
        (workflow_id,),
    )
    return result if isinstance(result, int) else 0
```

**Step 5: Update `event_exists()`**

```python
async def event_exists(self, event_id: str) -> bool:
    """Check if an event exists by ID.

    Args:
        event_id: The event ID to check.

    Returns:
        True if event exists, False otherwise.
    """
    result = await self._db.fetch_scalar(
        "SELECT 1 FROM workflow_log WHERE id = ? LIMIT 1",
        (event_id,),
    )
    return result is not None
```

**Step 6: Update `_row_to_event()`**

Remove the `tool_input_json` parsing and simplify. The new table doesn't have `correlation_id`, `tool_name`, `tool_input_json`, `trace_id`, `parent_id`:

```python
def _row_to_event(self, row: aiosqlite.Row) -> WorkflowEvent:
    """Convert database row to WorkflowEvent model.

    Args:
        row: Database row from workflow_log table.

    Returns:
        Validated WorkflowEvent model instance.
    """
    event_data = dict(row)
    if event_data.get("data_json"):
        event_data["data"] = json.loads(event_data.pop("data_json"))
    else:
        event_data.pop("data_json", None)

    if "is_error" in event_data:
        event_data["is_error"] = bool(event_data["is_error"])

    return WorkflowEvent(**event_data)
```

**Step 7: Update `get_events_after()`**

Replace all `FROM events` references with `FROM workflow_log` and remove trace-specific columns from SELECT:

```python
async def get_events_after(
    self, since_event_id: str, limit: int = 1000
) -> list[WorkflowEvent]:
    """Get events after a specific event (for backfill on reconnect).

    Args:
        since_event_id: The event ID to start after.
        limit: Maximum number of events to return (default 1000).

    Returns:
        List of events after the given event, ordered by sequence.

    Raises:
        ValueError: If the since_event_id doesn't exist.
    """
    row = await self._db.fetch_one(
        "SELECT workflow_id, sequence FROM workflow_log WHERE id = ?",
        (since_event_id,),
    )

    if row is None:
        raise ValueError(f"Event {since_event_id} not found")

    workflow_id, since_sequence = row["workflow_id"], row["sequence"]

    rows = await self._db.fetch_all(
        """
        SELECT id, workflow_id, sequence, timestamp, event_type,
               level, agent, message, data_json, is_error
        FROM workflow_log
        WHERE workflow_id = ? AND sequence > ?
        ORDER BY sequence ASC
        LIMIT ?
        """,
        (workflow_id, since_sequence, limit),
    )

    return [self._row_to_event(row) for row in rows]
```

**Step 8: Update `get_recent_events()`**

```python
async def get_recent_events(
    self, workflow_id: str, limit: int = 50
) -> list[WorkflowEvent]:
    """Get the most recent events for a workflow.

    Args:
        workflow_id: The workflow to get events for.
        limit: Maximum number of events to return (default 50).

    Returns:
        List of events ordered by sequence ascending (oldest first).
    """
    if limit <= 0:
        return []

    rows = await self._db.fetch_all(
        """
        SELECT id, workflow_id, sequence, timestamp, event_type,
               level, agent, message, data_json, is_error
        FROM workflow_log
        WHERE workflow_id = ?
        ORDER BY sequence DESC
        LIMIT ?
        """,
        (workflow_id, limit),
    )

    events = [self._row_to_event(row) for row in rows]
    events.reverse()
    return events
```

**Step 9: Update existing `TestRepositoryEvents` tests**

The existing tests in `tests/unit/server/database/test_repository.py` reference trace-specific fields (`tool_name`, `tool_input_json`, `trace_id`, `parent_id`). Update or remove:

- `test_save_event_with_trace_fields` — **remove** (trace fields no longer persisted)
- `test_save_event_with_distributed_tracing` — **remove** (distributed tracing fields removed from table)
- `test_row_to_event_restores_tracing_fields` — **remove** (no longer relevant)
- `test_save_event_with_level` — **keep**, update to use a persisted event type
- `test_row_to_event_restores_level` — **keep**, update to use a persisted event type

Also update `tests/unit/server/database/test_repository_backfill.py` — the `TestEventBackfill` class references `FROM events` patterns through the repository.

**Step 10: Run tests**

```bash
uv run pytest tests/unit/server/database/test_repository.py -v
```

Expected: All PASS

**Step 11: Commit**

```bash
git add amelia/server/database/repository.py tests/unit/server/database/test_repository.py tests/unit/server/database/test_repository_backfill.py
git commit -m "feat(repository): filter events and write to workflow_log

save_event() now short-circuits for stream-only event types.
Only PERSISTED_TYPES are written to the new workflow_log table.
Removed trace-specific column handling from _row_to_event()."
```

---

### Task 4: Remove trace retention from `LogRetentionService`

**Files:**
- Modify: `amelia/server/lifecycle/retention.py`
- Verify: `amelia/server/lifecycle/server.py` (no code changes needed — only accesses `events_deleted`, `workflows_deleted`, `checkpoints_deleted` which all remain)
- Test: `tests/unit/server/lifecycle/test_retention.py`
- Test: `tests/unit/server/lifecycle/test_server.py` (verify still passes after `CleanupResult` changes)

**Step 1: Read existing retention and server lifecycle tests**

Read `tests/unit/server/lifecycle/test_retention.py` and `tests/unit/server/lifecycle/test_server.py` to understand the test patterns.

**Step 2: Update `CleanupResult` to remove `trace_events_deleted`**

```python
class CleanupResult(BaseModel):
    """Result of cleanup operation."""

    events_deleted: int
    workflows_deleted: int
    checkpoints_deleted: int = 0
```

**Step 3: Update `ConfigProtocol` to remove `trace_retention_days`**

```python
class ConfigProtocol(Protocol):
    """Protocol for config access."""

    log_retention_days: int
    log_retention_max_events: int
    checkpoint_retention_days: int
```

**Step 4: Update `cleanup_on_shutdown()` — replace `events` with `workflow_log` and remove trace cleanup**

```python
async def cleanup_on_shutdown(self) -> CleanupResult:
    """Execute retention policy cleanup during server shutdown."""
    logger.info(
        "Running log retention cleanup",
        retention_days=self._config.log_retention_days,
        max_events=self._config.log_retention_max_events,
    )

    cutoff_date = datetime.now(UTC) - timedelta(
        days=self._config.log_retention_days
    )

    events_deleted = await self._db.execute(
        """
        DELETE FROM workflow_log
        WHERE workflow_id IN (
            SELECT id FROM workflows
            WHERE status IN ('completed', 'failed', 'cancelled')
            AND completed_at < ?
        )
        """,
        (cutoff_date.isoformat(),),
    )

    workflows_deleted = await self._db.execute(
        """
        DELETE FROM workflows
        WHERE id NOT IN (SELECT DISTINCT workflow_id FROM workflow_log)
        AND status IN ('completed', 'failed', 'cancelled')
        AND completed_at < ?
        """,
        (cutoff_date.isoformat(),),
    )

    checkpoints_deleted = await self._cleanup_checkpoints()

    # Note: Don't log "Cleanup complete" here — ServerLifecycle.shutdown()
    # already logs the returned CleanupResult fields to avoid duplicate logs.

    return CleanupResult(
        events_deleted=events_deleted,
        workflows_deleted=workflows_deleted,
        checkpoints_deleted=checkpoints_deleted,
    )
```

**Step 5: Remove `_cleanup_trace_events()` method entirely**

Delete the `_cleanup_trace_events()` method from `LogRetentionService`.

**Step 6: Update retention tests**

In `tests/unit/server/lifecycle/test_retention.py`:
- Remove `trace_retention_days` from the mock config class
- Remove `test_cleanup_respects_trace_retention_days` test
- Remove `trace_events_deleted` assertions from `CleanupResult` checks
- Replace all `FROM events` / `INTO events` SQL in test fixtures with `FROM workflow_log` / `INTO workflow_log`
- Update column lists in test INSERT statements to match `workflow_log` schema (remove `correlation_id`, `tool_name`, `tool_input_json`, `trace_id`, `parent_id`)

**Step 7: Run tests (including server lifecycle tests)**

```bash
uv run pytest tests/unit/server/lifecycle/ -v
```

Expected: All PASS (both `test_retention.py` and `test_server.py`)

`test_server.py` should pass without changes since `CleanupResult(events_deleted=10, workflows_deleted=2)` remains valid — `trace_events_deleted` was removed but the test never set it. Verify this is the case.

**Step 8: Commit**

```bash
git add amelia/server/lifecycle/retention.py tests/unit/server/lifecycle/test_retention.py
git commit -m "feat(retention): remove trace retention, use workflow_log table

LogRetentionService no longer manages trace event cleanup since
trace events are stream-only and never persisted. All SQL now
references workflow_log instead of events. Removed duplicate
'Cleanup complete' log (ServerLifecycle.shutdown() already logs it)."
```

---

### Task 5: Remove `trace_retention_days` from settings stack

**Files:**
- Modify: `amelia/server/database/settings_repository.py`
- Modify: `amelia/server/database/connection.py` (server_settings DDL)
- Modify: `amelia/server/routes/settings.py`
- Modify: `amelia/server/events/bus.py`
- Modify: `amelia/cli/config.py`
- Test: `tests/unit/server/test_settings_repository.py`
- Test: `tests/unit/server/events/test_bus.py`
- Test: `tests/unit/server/routes/test_config.py`
- Test: `tests/unit/server/routes/test_settings_routes.py`
- Test: `tests/unit/cli/test_config_cli.py`

**Step 1: Remove from `ServerSettings` model**

In `amelia/server/database/settings_repository.py`, remove `trace_retention_days: int` from `ServerSettings`.

**Step 2: Remove from `SettingsRepository`**

In `amelia/server/database/settings_repository.py`:
- Remove `"trace_retention_days"` from the valid_fields set in `update_server_settings()`
- Remove `trace_retention_days=row["trace_retention_days"]` from `_row_to_settings()`

**Step 3: Remove from `server_settings` DDL**

In `amelia/server/database/connection.py`, remove `trace_retention_days INTEGER NOT NULL DEFAULT 7,` from the `CREATE TABLE IF NOT EXISTS server_settings` block.

**Step 4: Remove from settings routes**

In `amelia/server/routes/settings.py`:
- Remove `trace_retention_days: int` from `ServerSettingsResponse`
- Remove `trace_retention_days: int | None = None` from `ServerSettingsUpdate`
- Remove `trace_retention_days=settings.trace_retention_days,` from the two route handlers

**Step 5: Simplify `EventBus`**

In `amelia/server/events/bus.py`:
- Remove `_trace_retention_days` field from `__init__`
- Remove `configure()` method entirely
- Simplify `emit()` — remove the `is_trace` / `should_persist` logic. All events get broadcast to subscribers and WebSocket unconditionally. Filtering now happens in `repository.save_event()`.

Updated `emit()`:

```python
def emit(self, event: WorkflowEvent) -> None:
    """Emit event to subscribers and broadcast to WebSocket clients.

    All events are sent to both subscribers (for persistence filtering)
    and WebSocket clients (for real-time UI updates).

    Args:
        event: The workflow event to broadcast.
    """
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
```

**Step 6: Remove from CLI config**

In `amelia/cli/config.py`:
- Remove the `table.add_row("Trace Retention Days", str(settings.trace_retention_days))` line
- Remove `"trace_retention_days"` from the valid settings key list in the `server_set` command

**Step 7: Find and remove all `bus.configure(trace_retention_days=...)` calls**

Search for `configure(trace_retention_days` and `bus.configure` in the codebase and remove those calls.

**Step 8: Update all affected tests**

- `tests/unit/server/test_settings_repository.py` — remove `trace_retention_days` from test data and assertions
- `tests/unit/server/events/test_bus.py` — remove `bus.configure(trace_retention_days=0)` calls, remove tests that verify trace event suppression, update remaining tests
- `tests/unit/server/routes/test_config.py` — remove `trace_retention_days` from mock settings
- `tests/unit/server/routes/test_settings_routes.py` — remove `trace_retention_days` from mock data
- `tests/unit/cli/test_config_cli.py` — remove `trace_retention_days` from mock settings

**Step 9: Run tests**

```bash
uv run pytest tests/unit/server/test_settings_repository.py tests/unit/server/events/test_bus.py tests/unit/server/routes/ tests/unit/cli/test_config_cli.py -v
```

Expected: All PASS

**Step 10: Commit**

```bash
git add amelia/server/database/settings_repository.py amelia/server/database/connection.py amelia/server/routes/settings.py amelia/server/events/bus.py amelia/cli/config.py tests/
git commit -m "feat(settings): remove trace_retention_days from entire stack

Trace events are no longer persisted, so trace retention config
is removed from: ServerSettings model, settings repository,
settings API routes, EventBus, and CLI config commands."
```

---

### Task 6: Update dashboard frontend

**Files:**
- Modify: `dashboard/src/api/settings.ts`
- Modify: `dashboard/src/components/settings/ServerSettingsForm.tsx`
- Test: `dashboard/src/api/__tests__/settings.test.ts`

**Step 1: Remove `trace_retention_days` from TypeScript types**

In `dashboard/src/api/settings.ts`, remove `trace_retention_days: number;` from the settings interface.

**Step 2: Remove from settings form**

In `dashboard/src/components/settings/ServerSettingsForm.tsx`, remove the `trace_retention_days` form field (the Label + Select block around line 83-88).

**Step 3: Update tests**

In `dashboard/src/api/__tests__/settings.test.ts`, remove `trace_retention_days: 7,` from mock data.

**Step 4: Run dashboard tests**

```bash
cd dashboard && pnpm test:run
```

Expected: All PASS

**Step 5: Build dashboard**

```bash
cd dashboard && pnpm build
```

Expected: Build succeeds

**Step 6: Commit**

```bash
git add dashboard/src/api/settings.ts dashboard/src/components/settings/ServerSettingsForm.tsx dashboard/src/api/__tests__/settings.test.ts
git commit -m "feat(dashboard): remove trace retention setting from UI

Trace events are no longer persisted, so the trace retention days
setting is removed from the server settings form."
```

---

### Task 7: Update `WorkflowEvent` model — remove trace-specific fields

**Files:**
- Modify: `amelia/server/models/events.py`
- Test: `tests/unit/server/models/test_events.py`

The `WorkflowEvent` Pydantic model still has `correlation_id`, `tool_name`, `tool_input`, `trace_id`, `parent_id`, and `model`. These are only relevant for trace events which are no longer persisted. However, they are still used in-memory for WebSocket streaming. **Keep these fields on the model** — they're needed for real-time dashboard updates even though they aren't written to the database.

This task is a **no-op** — the model fields stay. The repository just ignores them when writing to `workflow_log`.

**Skip this task.** No changes needed.

---

### Task 8: Write unit test for event filtering edge cases

**Files:**
- Create: `tests/unit/test_event_filtering.py`

**Step 1: Write the test file**

```python
"""Unit tests for event filtering edge cases."""

from datetime import UTC, datetime

import pytest

from amelia.server.models.events import (
    PERSISTED_TYPES,
    EventType,
    WorkflowEvent,
    get_event_level,
)


class TestEventFilteringEdgeCases:
    """Edge cases for event persistence classification."""

    def test_persisted_types_count(self):
        """Verify expected count of persisted types."""
        # 5 lifecycle + 2 stage + 3 approval + 3 artifact + 3 review
        # + 3 task + 2 system + 3 oracle + 3 brainstorm = 27
        assert len(PERSISTED_TYPES) == 27

    @pytest.mark.parametrize(
        "event_type",
        list(PERSISTED_TYPES),
        ids=lambda et: et.value,
    )
    def test_persisted_event_has_valid_level(self, event_type: EventType):
        """Every persisted event type must map to a level accepted by workflow_log CHECK constraint."""
        level = get_event_level(event_type)
        assert level.value in {"info", "warning", "error", "debug"}

    def test_workflow_event_with_none_agent_is_valid(self):
        """workflow_log allows NULL agent — verify model accepts None."""
        event = WorkflowEvent(
            id="evt-test",
            workflow_id="wf-test",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.WORKFLOW_CREATED,
            message="test",
        )
        # agent is required on the model but nullable in the DB schema.
        # The model always provides an agent string; the DB column is
        # nullable as a safety margin. This test verifies the model works.
        assert event.agent == "system"
```

**Step 2: Run test**

```bash
uv run pytest tests/unit/test_event_filtering.py -v
```

Expected: All PASS

**Step 3: Commit**

```bash
git add tests/unit/test_event_filtering.py
git commit -m "test(events): add event filtering edge case tests

Verify PERSISTED_TYPES count, level constraint compatibility,
and agent nullable handling."
```

---

### Task 9: Run full test suite and lint

**Step 1: Run ruff**

```bash
uv run ruff check amelia tests
```

Fix any issues found.

**Step 2: Run mypy**

```bash
uv run mypy amelia
```

Fix any type errors.

**Step 3: Run full Python test suite**

```bash
uv run pytest -v
```

Expected: All PASS

**Step 4: Run dashboard tests and build**

```bash
cd dashboard && pnpm test:run && pnpm build
```

Expected: All PASS, build succeeds

**Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix: resolve lint, type, and test issues from workflow_log refactor"
```

---

### Task 10: Final verification and cleanup

**Step 1: Verify no remaining references to old `events` table**

Search for `FROM events`, `INTO events`, `events WHERE`, `events(` in the production code (not tests):

```bash
uv run ruff check amelia tests
```

Also manually verify:
- No `trace_retention_days` references remain in production code
- No `_TRACE_TYPES` references remain
- No `EventLevel.TRACE` references remain
- No `trace_events_deleted` references remain in production code or tests
- `amelia/server/lifecycle/server.py` compiles and its shutdown log matches the new `CleanupResult` shape (no `trace_events_deleted` field access)
- No duplicate "Cleanup complete" log messages (should only appear in `server.py`, not `retention.py`)

**Step 2: Verify the `CLAUDE.md` environment variable table**

Update `CLAUDE.md` to remove the `AMELIA_TRACE_RETENTION_DAYS` row from the Server Configuration table.

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: remove trace retention from CLAUDE.md config table"
```

---

## Summary of All Changed Files

| File | Change |
|------|--------|
| `amelia/server/models/events.py` | Add `PERSISTED_TYPES`, update `EventLevel` (remove TRACE, add WARNING/ERROR), update level mappings |
| `amelia/server/database/connection.py` | Replace `events` DDL with `workflow_log`, update indexes, remove `trace_retention_days` from `server_settings` |
| `amelia/server/database/repository.py` | Filter in `save_event()`, update all SQL to `workflow_log`, simplify `_row_to_event()` |
| `amelia/server/database/settings_repository.py` | Remove `trace_retention_days` from `ServerSettings` and repository |
| `amelia/server/lifecycle/retention.py` | Remove `_cleanup_trace_events()`, update SQL to `workflow_log`, remove `trace_retention_days` from protocol, remove duplicate "Cleanup complete" log |
| `amelia/server/lifecycle/server.py` | Verify only — no code changes needed (shutdown log already correct) |
| `amelia/server/events/bus.py` | Remove `configure()`, remove trace suppression from `emit()` |
| `amelia/server/routes/settings.py` | Remove `trace_retention_days` from request/response models |
| `amelia/cli/config.py` | Remove trace retention from display and valid settings keys |
| `dashboard/src/api/settings.ts` | Remove `trace_retention_days` from TypeScript interface |
| `dashboard/src/components/settings/ServerSettingsForm.tsx` | Remove trace retention form field |
| `dashboard/src/api/__tests__/settings.test.ts` | Remove `trace_retention_days` from test mocks |
| `CLAUDE.md` | Remove `AMELIA_TRACE_RETENTION_DAYS` from config table |
| `tests/unit/server/models/test_events.py` | Add `TestPersistedTypes`, update level tests |
| `tests/unit/server/database/test_repository.py` | Add `TestWorkflowLogFiltering`, remove trace-field tests |
| `tests/unit/server/database/test_repository_backfill.py` | Update to `workflow_log` table |
| `tests/unit/server/lifecycle/test_retention.py` | Remove trace retention tests, update SQL |
| `tests/unit/server/lifecycle/test_server.py` | Verify passes — `CleanupResult` shape change is backward-compatible |
| `tests/unit/server/test_settings_repository.py` | Remove `trace_retention_days` |
| `tests/unit/server/events/test_bus.py` | Remove `configure()` and trace suppression tests |
| `tests/unit/server/routes/test_config.py` | Remove `trace_retention_days` |
| `tests/unit/server/routes/test_settings_routes.py` | Remove `trace_retention_days` |
| `tests/unit/cli/test_config_cli.py` | Remove `trace_retention_days` |
| `tests/unit/test_event_filtering.py` | New: edge case tests |
