# PostgreSQL Database Design

## Goal

Replace SQLite with PostgreSQL to enable distributed workers and shared dashboard access.

**No migration:** Delete `~/.amelia/` and start fresh. No data conversion, no backwards compatibility.

**Prerequisite:** ~~Events to Workflow Log Refactor~~ — completed in PR #402. The `workflow_log` table now exists on SQLite with `PERSISTED_TYPES` filtering.

## Motivation

| Driver | Priority |
|--------|----------|
| Distributed workers - workflow execution across multiple machines | Primary |
| Shared dashboard - multiple developers accessing same workflows | Secondary |
| pg_vector for embeddings (future) | Deferred |

## Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Database | PostgreSQL only | Distributed workers require remote DB access |
| Driver | asyncpg with connection pooling | Async, fast, native PostgreSQL support |
| Schema management | Version-based SQL files | Simple, no ORM overhead, full PostgreSQL feature access |
| pg_vector | Deferred | Data model for Knowledge Library/Oracle not yet defined |
| Checkpoints | langgraph-checkpoint-postgres | Single database for all data |
| Event streaming | In-memory only, not persisted | Implemented in PR #402: `PERSISTED_TYPES` controls persistence, trace/stream events are broadcast-only |
| Workflow logging | `workflow_log` table (implemented) | Slim audit log with 27 persisted event types; 10 columns (dropped trace-specific fields) |

## Configuration

Replace `database_path` with `database_url` in `ServerConfig`:

```python
database_url: str = Field(
    default="postgresql://localhost:5432/amelia",
    description="PostgreSQL connection URL",
)
db_pool_min_size: int = Field(default=2, ge=1)
db_pool_max_size: int = Field(default=10, ge=1)
```

**Settings removed during this migration:**
- `trace_retention_days` — trace events are no longer persisted (already removed in PR #402)
- `checkpoint_path` — still exists in `server_settings` table; remove during migration (checkpoints will share the PostgreSQL database)
- `log_retention_max_events` — still exists in `server_settings` table; remove during migration (retention is time-based only)

Connection URL examples:
- Local Docker: `postgresql://amelia:password@localhost:5432/amelia`
- Supabase: `postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres`
- With SSL: `postgresql://...?sslmode=require`

## Schema

### Type conventions

| Type | Usage |
|------|-------|
| `UUID` | All primary keys and foreign keys |
| `JSONB` | Nested/variable structures (state, log data, agent config) |
| `BOOLEAN` | All boolean flags |
| `NUMERIC(10,6)` | Monetary values (cost_usd) |
| `TIMESTAMPTZ` | All timestamps |

### JSONB columns

- `workflows.state` - Full ServerExecutionState
- `workflow_log.data` - Optional structured data for log entry (rename from `data_json TEXT`)
- `brainstorm_messages.parts` - Message parts (text, tool calls, reasoning) (rename from `parts_json TEXT`)
- `profiles.agents` - Per-agent configuration

### Checkpoints

Use `langgraph-checkpoint-postgres` with `AsyncPostgresSaver`. The library manages its own tables (`checkpoints`, `writes`, `blobs`) in the same database.

## Event Architecture

### Problem (resolved in PR #402)

The old `events` table stored everything: thinking blocks, tool calls, streaming chunks, errors — thousands of rows per workflow. PR #402 replaced it with `workflow_log` using `PERSISTED_TYPES` filtering. The PostgreSQL migration carries this forward.

### Solution

**Persisted (`workflow_log` table):**
- Workflow lifecycle (created, started, completed, failed)
- Stage transitions (architect → developer → reviewer)
- Approval decisions (granted, rejected)
- Errors and failures with context
- File artifacts (created, modified, deleted)

**Stream-only (in-memory, not persisted):**
- `claude_thinking`, `claude_tool_call`, `claude_tool_result`
- `stream` chunks
- `agent_output`
- All verbose trace-level events

### `workflow_log` table

```sql
CREATE TABLE workflow_log (
    id UUID PRIMARY KEY,
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    level TEXT NOT NULL CHECK (level IN ('info', 'warning', 'error', 'debug')),
    event_type TEXT NOT NULL,
    agent TEXT,
    message TEXT NOT NULL,
    data JSONB,
    is_error BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (workflow_id, sequence)
);

-- Sequence provides deterministic ordering under concurrency (timestamps can collide)
CREATE INDEX idx_workflow_log_workflow ON workflow_log(workflow_id, sequence);
CREATE INDEX idx_workflow_log_errors ON workflow_log(workflow_id) WHERE is_error = TRUE;
```

### `token_usage` table

```sql
CREATE TABLE token_usage (
    id UUID PRIMARY KEY,
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    agent TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cost_usd NUMERIC(10,6) NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    num_turns INTEGER NOT NULL DEFAULT 1,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_token_usage_workflow ON token_usage(workflow_id);
CREATE INDEX idx_token_usage_timestamp ON token_usage(timestamp);
```

Powers the Costs page, usage trends, and per-model analytics. Currently has 15+ query methods in `repository.py`.

### Additional tables requiring PostgreSQL DDL

The following tables also need PostgreSQL schemas in `001_initial_schema.sql` (not shown here for brevity):

| Table | Key columns | Notes |
|-------|-------------|-------|
| `workflows` | id, issue_id, worktree_path, status, workflow_type, profile_id, timestamps, plan_cache (JSONB), issue_cache (JSONB) | Main workflow state; add partial unique index on `worktree_path WHERE status IN ('pending', 'in_progress', 'blocked')` |
| `prompts` | id, agent, name, description, current_version_id | Prompt definitions |
| `prompt_versions` | id, prompt_id, version, content, is_default | Versioned prompt content |
| `workflow_prompt_versions` | workflow_id, prompt_id, version_id | Audit trail |
| `server_settings` | Singleton (id=1), retention settings, timeouts, max_concurrent | Remove `checkpoint_path` and `log_retention_max_events` fields |
| `profiles` | id, tracker, working_dir, plan_output_dir, plan_path_pattern, agents (JSONB), is_active, timestamps | Add `CREATE UNIQUE INDEX ... ON profiles(is_active) WHERE is_active = TRUE` to replace SQLite trigger |
| `brainstorm_sessions` | id, profile_id, driver_session_id, driver_type, status, topic, timestamps | Session metadata |
| `brainstorm_messages` | id, session_id, sequence, role, content, parts (JSONB), input_tokens, output_tokens, cost_usd (NUMERIC), is_system (BOOLEAN), timestamps | Message history; rename `parts_json` → `parts`, `cost_usd REAL` → `NUMERIC(10,6)` |
| `brainstorm_artifacts` | id, session_id, type, path, title | Generated artifacts |

Result: ~10-20 rows per workflow instead of thousands.

### New constraints (not in current SQLite schema)

These constraints are new additions for PostgreSQL — they don't exist in the current SQLite schema:

```sql
-- workflow_log: deterministic ordering (new — SQLite has no such constraint)
UNIQUE (workflow_id, sequence)

-- workflows: prevent duplicate active worktrees (enforced in app code today)
CREATE UNIQUE INDEX idx_workflows_active_worktree
    ON workflows(worktree_path)
    WHERE status IN ('pending', 'in_progress', 'blocked');

-- profiles: ensure only one active profile (replaces SQLite trigger)
CREATE UNIQUE INDEX idx_profiles_active
    ON profiles(is_active) WHERE is_active = TRUE;
```

### Persisted event types

```sql
CHECK (event_type IN (
    -- Lifecycle
    'workflow_created', 'workflow_started', 'workflow_completed', 'workflow_failed', 'workflow_cancelled',
    -- Stages
    'stage_started', 'stage_completed',
    -- Approval
    'approval_required', 'approval_granted', 'approval_rejected',
    -- Artifacts
    'file_created', 'file_modified', 'file_deleted',
    -- Review
    'review_requested', 'review_completed', 'revision_requested',
    -- Tasks
    'task_started', 'task_completed', 'task_failed',
    -- Oracle
    'oracle_consultation_started', 'oracle_consultation_completed', 'oracle_consultation_failed',
    -- Brainstorm
    'brainstorm_session_created', 'brainstorm_session_completed', 'brainstorm_artifact_created',
    -- System
    'system_error', 'system_warning'
))

-- DECISION NEEDED: Brainstorm events use workflow_id = session.id (not a real workflow ID).
-- The FK constraint REFERENCES workflows(id) will fail for brainstorm events.
-- Recommended: (a) remove brainstorm events from workflow_log — brainstorm already has
-- its own tables (brainstorm_sessions/messages/artifacts) for persistence.
-- Other options: (b) make workflow_id nullable, (c) add brainstorm_sessions to the FK target.
```

## Schema Management

### Directory structure

```
amelia/server/database/
  migrations/
    001_initial_schema.sql
    002_....sql
  connection.py      # asyncpg pool management
  repository.py      # queries with $1 syntax
  migrator.py        # runs schema migrations on startup
```

### Version tracking

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Checkpoint saver lifecycle

The current code creates `AsyncSqliteSaver.from_conn_string()` at 7 callsites in `service.py`, each opening/closing a connection. With PostgreSQL, initialize `AsyncPostgresSaver` once at startup with the shared connection pool:

```python
# Startup: create once
pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
checkpointer = AsyncPostgresSaver(pool)
await checkpointer.setup()  # Creates checkpoint tables if needed

# Runtime: pass to all graph invocations (no async with per-call)
graph = create_server_graph(checkpointer)

# Shutdown: pool handles cleanup
await pool.close()
```

### Startup behavior

1. Ensure `schema_migrations` table exists
2. Get current version from table
3. Run any SQL files with version > current
4. Record applied versions

## Files to Change

| File | Change |
|------|--------|
| `pyproject.toml` | Add asyncpg and langgraph-checkpoint-postgres, remove aiosqlite and langgraph-checkpoint-sqlite |
| `amelia/server/config.py` | Replace `database_path: Path` with `database_url: str`, add pool settings |
| `amelia/server/database/connection.py` | Rewrite for asyncpg pool (replace aiosqlite, remove PRAGMAs, use `$1` params) |
| `amelia/server/database/migrations/` | New directory with SQL files (001_initial_schema.sql covering ALL tables) |
| `amelia/server/database/migrator.py` | New file, schema version runner |
| `amelia/server/database/repository.py` | Use `$1` parameter syntax, update row-to-model conversions (native datetime/bool) |
| `amelia/server/database/brainstorm_repository.py` | Use `$1` parameter syntax, update row conversions |
| `amelia/server/database/prompt_repository.py` | Use `$1` parameter syntax, update row conversions |
| `amelia/server/database/settings_repository.py` | Use `$1` syntax, `INSERT ... ON CONFLICT` instead of `INSERT OR IGNORE`, remove `checkpoint_path` field |
| `amelia/server/database/profile_repository.py` | Use `$1` parameter syntax, update row conversions |
| `amelia/server/database/__init__.py` | Update exports for new module structure |
| `amelia/server/orchestrator/service.py` | Replace 7x `AsyncSqliteSaver.from_conn_string()` with shared `AsyncPostgresSaver` |
| `amelia/server/main.py` | Update startup lifecycle: create pool, initialize `AsyncPostgresSaver`, wire repositories; remove `checkpoint_path` from `OrchestratorService.__init__()` |
| `amelia/server/models/events.py` | No changes needed (workflow_log refactor already complete) |
| `amelia/server/lifecycle/retention.py` | Rewrite `_cleanup_checkpoints()` to use shared pool instead of direct `aiosqlite.connect()` to separate file; DELETE from `langgraph-checkpoint-postgres` tables via same pool |
| `amelia/server/events/bus.py` | No changes needed (already simplified in PR #402) |
| `amelia/server/events/connection_manager.py` | No changes needed (uses `PERSISTED_TYPES` but no DB operations) |
| `tests/conftest.py` | PostgreSQL test fixtures |
| `tests/unit/server/database/conftest.py` | Replace SQLite fixtures with PostgreSQL fixtures |
| `tests/unit/server/database/test_*.py` | Update all 12 test files for PostgreSQL |
| `docker-compose.yml` | Add PostgreSQL service |
| `.github/workflows/ci.yml` | Add GitHub Actions PostgreSQL service container |
| `CLAUDE.md` | Update env vars (DATABASE_URL replaces DATABASE_PATH, remove CHECKPOINT_PATH) |

## SQLite → PostgreSQL Syntax Changes

| SQLite Syntax | PostgreSQL Equivalent | Location |
|---------------|----------------------|----------|
| `?` parameter placeholders | `$1, $2, ...` | All repositories (100+ queries) |
| `INSERT OR IGNORE` | `INSERT ... ON CONFLICT DO NOTHING` | `settings_repository.py` |
| `INSERT OR REPLACE` | `INSERT ... ON CONFLICT (...) DO UPDATE SET ...` | `prompt_repository.py` (workflow_prompt_versions) |
| `data_json TEXT` column | `data JSONB` (rename) | `workflow_log` table, `repository.py` row conversions |
| `parts_json TEXT` column | `parts JSONB` (rename) | `brainstorm_messages` table, `brainstorm_repository.py` row conversions |
| `INTEGER` for booleans | `BOOLEAN` | `workflow_log.is_error`, `server_settings.stream_tool_results` |
| `TEXT` for timestamps | `TIMESTAMPTZ` (native datetime) | All tables |
| `REAL` for money | `NUMERIC(10,6)` | `token_usage.cost_usd` |
| `PRAGMA` statements | Pool configuration | `connection.py` (WAL, foreign_keys, busy_timeout) |
| `CURRENT_TIMESTAMP` (text) | `NOW()` (timestamptz) | Default values |
| `DATE()` function | `::date` cast | Usage analytics queries in `repository.py` |
| `datetime.fromisoformat(row[...])` | Direct use (asyncpg returns native datetime) | All `_row_to_*` methods |
| `bool(row[...])` | Direct use (asyncpg returns native bool) | Settings, event conversions |

## Connection Pool Lifecycle

| Phase | Action |
|-------|--------|
| **Startup** | `asyncpg.create_pool(database_url, min_size=2, max_size=10)` |
| **Runtime** | Repositories acquire/release connections from pool automatically |
| **Health check** | `pool.fetchval('SELECT 1')` replaces `PRAGMA integrity_check` |
| **Shutdown** | `await pool.close()` then `await pool.wait_closed()` |

## Testing

### Local development

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: amelia
      POSTGRES_PASSWORD: amelia
      POSTGRES_DB: amelia
    ports:
      - "5432:5432"
```

### Test fixtures

```python
@pytest.fixture
async def test_db():
    """Fresh database for each test."""
    db = Database("postgresql://amelia:amelia@localhost:5432/amelia_test")
    await db.connect()
    await db.migrate()
    yield db
    await db.execute("TRUNCATE workflows, workflow_log, ... CASCADE")
    await db.close()
```

### CI

GitHub Actions PostgreSQL service container, same configuration as local Docker.

## Future: pg_vector

When ready (after Knowledge Library/Oracle data model is defined):

1. Add schema migration: `CREATE EXTENSION IF NOT EXISTS vector;`
2. Create embeddings table with `vector(N)` column
3. Register vector type in connection pool setup

## Related Issues

- #280 - Oracle Consulting System
- #290 - RLM Integration (Knowledge Library, RAG)
- #308 - PostgreSQL database implementation
