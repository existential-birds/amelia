# PostgreSQL Database Design

## Goal

Replace SQLite with PostgreSQL to enable distributed workers and shared dashboard access.

**No migration:** Delete `~/.amelia/` and start fresh. No data conversion, no backwards compatibility.

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
| Event streaming | In-memory only, not persisted | Verbose trace data only useful live |
| Workflow logging | New `workflow_log` table | Slim audit log for debugging and history |

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
- `workflow_log.data` - Optional structured data for log entry
- `brainstorm_messages.parts` - Message parts (text, tool calls, reasoning)
- `profiles.agents` - Per-agent configuration

### Checkpoints

Use `langgraph-checkpoint-postgres` with `AsyncPostgresSaver`. The library manages its own tables (`checkpoints`, `writes`, `blobs`) in the same database.

## Event Architecture

### Problem

The current `events` table stores everything: thinking blocks, tool calls, streaming chunks, errors - thousands of rows per workflow. Most of this is only useful during live execution.

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
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    level TEXT NOT NULL CHECK (level IN ('info', 'warning', 'error')),
    event_type TEXT NOT NULL,
    agent TEXT,
    message TEXT NOT NULL,
    data JSONB,
    is_error BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_workflow_log_workflow ON workflow_log(workflow_id, timestamp);
CREATE INDEX idx_workflow_log_errors ON workflow_log(workflow_id) WHERE is_error = TRUE;
```

Result: ~10-20 rows per workflow instead of thousands.

### Persisted event types

```sql
CHECK (event_type IN (
    'workflow_created', 'workflow_started', 'workflow_completed', 'workflow_failed', 'workflow_cancelled',
    'stage_started', 'stage_completed',
    'approval_required', 'approval_granted', 'approval_rejected',
    'file_created', 'file_modified', 'file_deleted',
    'review_requested', 'review_completed', 'revision_requested',
    'system_error', 'system_warning'
))
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

### Startup behavior

1. Ensure `schema_migrations` table exists
2. Get current version from table
3. Run any SQL files with version > current
4. Record applied versions

## Files to Change

| File | Change |
|------|--------|
| `pyproject.toml` | Add asyncpg and langgraph-checkpoint-postgres, remove aiosqlite and langgraph-checkpoint-sqlite |
| `amelia/server/config.py` | Replace `database_path` with `database_url`, add pool settings |
| `amelia/server/database/connection.py` | Rewrite for asyncpg pool |
| `amelia/server/database/migrations/` | New directory with SQL files |
| `amelia/server/database/migrator.py` | New file, schema version runner |
| `amelia/server/database/repository.py` | Replace `events` with `workflow_log`, use `$1` parameter syntax |
| `amelia/server/database/brainstorm_repository.py` | Use `$1` parameter syntax |
| `amelia/server/database/prompt_repository.py` | Use `$1` parameter syntax |
| `amelia/server/database/settings_repository.py` | Use `$1` parameter syntax |
| `amelia/server/database/profile_repository.py` | Use `$1` parameter syntax |
| `amelia/server/orchestrator/service.py` | Use AsyncPostgresSaver from langgraph-checkpoint-postgres |
| `amelia/server/models/events.py` | Split into persisted log events vs stream-only events |
| `amelia/server/lifecycle/retention.py` | Simplify - smaller `workflow_log` table |
| `tests/conftest.py` | PostgreSQL test fixtures |
| `docker-compose.yml` | Add PostgreSQL service |
| `.github/workflows/*.yml` | Add GitHub Actions PostgreSQL service container |

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

## Completed Prep Work

The following schema changes have already been completed on `main` to prepare for PostgreSQL:

| PR | Change |
|----|--------|
| #389 | Removed `state_json` blob from `workflows` table, replaced with discrete columns: `workflow_type`, `profile_id`, `plan_cache`, `issue_cache` |

The PostgreSQL migration should use the current schema as the starting point (no `state_json` column).

## Related Issues

- #280 - Oracle Consulting System
- #290 - RLM Integration (Knowledge Library, RAG)
- #308 - PostgreSQL database implementation
