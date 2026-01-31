# Events to Workflow Log Refactor

## Goal

Replace the `events` table with a slim `workflow_log` table that only persists high-level workflow events. Verbose trace events become stream-only (in-memory).

**Breaking change:** Requires deleting `~/.amelia/` (clean break).

**Prerequisite for:** PostgreSQL migration (`docs/plans/2026-01-19-postgresql-migration-design.md`)

## Motivation

The current `events` table stores everything—thinking blocks, tool calls, streaming chunks, agent output—resulting in thousands of rows per workflow. Most of this data is only useful during live execution for the dashboard's real-time updates.

| Metric | Before | After |
|--------|--------|-------|
| Rows per workflow | Thousands | 10-50 |
| Columns | 16 | 9 |
| Retention settings | 2 (`log` + `trace`) | 1 (`log` only) |

## Event Classification

### Persisted (workflow_log)

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

## Schema

### Current `events` table (16 columns)

```sql
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    agent TEXT NOT NULL,
    event_type TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'debug',
    message TEXT NOT NULL,
    data_json TEXT,
    correlation_id TEXT,
    tool_name TEXT,           -- trace-only
    tool_input_json TEXT,     -- trace-only
    is_error INTEGER NOT NULL DEFAULT 0,
    trace_id TEXT,            -- trace-only
    parent_id TEXT            -- trace-only
)
```

### New `workflow_log` table (9 columns)

```sql
CREATE TABLE workflow_log (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,
    level TEXT NOT NULL CHECK (level IN ('info', 'warning', 'error')),
    agent TEXT,               -- nullable, not all events have agent context
    message TEXT NOT NULL,
    data_json TEXT,           -- optional structured data
    is_error INTEGER NOT NULL DEFAULT 0
)

CREATE INDEX idx_workflow_log_workflow ON workflow_log(workflow_id, sequence);
CREATE INDEX idx_workflow_log_errors ON workflow_log(workflow_id) WHERE is_error = 1;
```

**Removed columns:** `correlation_id`, `tool_name`, `tool_input_json`, `trace_id`, `parent_id` — only relevant for trace-level events.

## Implementation

### Key logic change

```python
# amelia/server/models/events.py
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

```python
# amelia/server/database/repository.py
async def save_event(self, event: WorkflowEvent) -> None:
    """Save event to workflow_log if it's a persisted type."""
    if event.event_type not in PERSISTED_TYPES:
        return  # Stream-only, don't persist

    await self.execute(
        "INSERT INTO workflow_log (...) VALUES (...)",
        ...
    )
```

### Event bus unchanged

The `EventBus` still broadcasts all events to WebSocket subscribers for real-time dashboard updates. Filtering only happens at the persistence layer.

## Files to Change

| File | Change |
|------|--------|
| `amelia/server/database/connection.py` | Replace `events` DDL with `workflow_log` |
| `amelia/server/database/repository.py` | Add `PERSISTED_TYPES`, filter in `save_event()`, rename table references |
| `amelia/server/models/events.py` | Export `PERSISTED_TYPES` frozenset |
| `amelia/server/lifecycle/retention.py` | Remove trace retention logic |
| `amelia/server/config.py` | Remove `trace_retention_days` setting |
| `tests/integration/test_workflow_log.py` | New E2E test for event persistence |
| `tests/unit/test_event_filtering.py` | Unit tests for edge cases |

## Testing

### Primary: End-to-end integration test

One comprehensive test that runs a real workflow with only the LLM HTTP boundary mocked:

```python
async def test_workflow_log_persistence_e2e(test_db, mock_llm_responses):
    """Verify correct events persist through full workflow execution.

    Only mocks: HTTP calls to LLM API
    Real: Orchestrator, agents, event bus, repository, database
    """
    # Run workflow through architect -> developer -> reviewer
    workflow = await orchestrator.start(issue, profile)
    await orchestrator.wait_for_completion(workflow.id)

    # Verify persisted events
    logs = await repo.get_workflow_log(workflow.id)

    # Assert lifecycle events present
    assert_event_types_present(logs, [
        "workflow_created", "workflow_started",
        "stage_started", "stage_completed",  # multiple
        "workflow_completed"
    ])

    # Assert trace events NOT persisted
    assert_no_event_types(logs, [
        "claude_thinking", "claude_tool_call", "agent_output"
    ])

    # Verify reasonable count (~10-50, not thousands)
    assert 10 <= len(logs) <= 100
```

### Secondary: Unit tests for edge cases

- `test_save_event_filters_stream_only_types` — verify filtering logic
- `test_workflow_log_schema_constraints` — verify CHECK constraints work

## Migration

**Approach:** Clean break (delete `~/.amelia/`).

No data migration needed because:
1. Amelia is pre-1.0, users expect breaking changes
2. Historical trace events have no long-term value
3. Simplifies implementation significantly

## Configuration Changes

| Setting | Before | After |
|---------|--------|-------|
| `log_retention_days` | Keep (default 30) | Keep (default 30) |
| `trace_retention_days` | Remove | N/A |
| `stream_tool_results` | Keep | Keep (controls WebSocket streaming) |
