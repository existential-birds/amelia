# Database Schema Review

Pre-PostgreSQL migration audit of the current SQLite schema. Documents every table, index,
trigger, and constraint, then proposes changes to lock in before migrations make schema
changes expensive.

Reference: [#308 - Migrate from SQLite to PostgreSQL](https://github.com/existential-birds/amelia-feature/issues/308)

---

## Current Schema

**Source:** `amelia/server/database/connection.py` — `Database.ensure_schema()`

**SQLite configuration:** WAL mode, foreign keys ON, 5s busy timeout, 64MB journal limit, autocommit with explicit transaction management.

### Tables

#### 1. `workflows`

Stores workflow execution state and metadata.

```sql
CREATE TABLE workflows (
    id                TEXT PRIMARY KEY,         -- UUID as text
    issue_id          TEXT NOT NULL,            -- issue key (e.g. "PROJ-123")
    worktree_path     TEXT NOT NULL,            -- absolute git worktree path
    status            TEXT NOT NULL DEFAULT 'pending',
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at        TIMESTAMP,
    completed_at      TIMESTAMP,
    failure_reason    TEXT,
    workflow_type     TEXT NOT NULL DEFAULT 'full',  -- 'full' or 'review'
    profile_id        TEXT,                     -- active profile at time of creation
    plan_cache        TEXT,                     -- cached plan data (JSON-serialized PlanCache)
    issue_cache       TEXT                      -- cached issue data
);
```

**Indexes:**
| Name | Definition |
|------|-----------|
| `idx_workflows_issue_id` | `(issue_id)` |
| `idx_workflows_status` | `(status)` |
| `idx_workflows_worktree` | `(worktree_path)` |
| `idx_workflows_started_at` | `(started_at DESC)` |
| `idx_workflows_active_worktree` | `UNIQUE (worktree_path) WHERE status IN ('in_progress', 'blocked')` |

**Notes:**
- Partial unique index allows multiple pending workflows per worktree but only one active.
- `plan_cache` contains a JSON-serialized `PlanCache` Pydantic model.
- Execution state now lives in LangGraph checkpoints, not in the database.

---

#### 2. `events`

Stores workflow execution events (logs, tool calls, traces).

```sql
CREATE TABLE events (
    id              TEXT PRIMARY KEY,
    workflow_id     TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    sequence        INTEGER NOT NULL,
    timestamp       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    agent           TEXT NOT NULL,              -- architect | developer | reviewer
    event_type      TEXT NOT NULL,              -- log, tool_call, etc.
    level           TEXT NOT NULL DEFAULT 'debug',
    message         TEXT NOT NULL,
    data_json       TEXT,                       -- structured event data
    correlation_id  TEXT,
    tool_name       TEXT,
    tool_input_json TEXT,                       -- tool input parameters
    is_error        INTEGER NOT NULL DEFAULT 0, -- boolean
    trace_id        TEXT,
    parent_id       TEXT                        -- hierarchical traces
);
```

**Indexes:**
| Name | Definition |
|------|-----------|
| `idx_events_workflow_sequence` | `UNIQUE (workflow_id, sequence)` |
| `idx_events_workflow` | `(workflow_id, timestamp)` |
| `idx_events_type` | `(event_type)` |
| `idx_events_level` | `(level)` |
| `idx_events_trace_id` | `(trace_id)` |

**Notes:**
- Highest-volume table. A single workflow can produce thousands of events.
- `parent_id` references another event `id` but has no FK constraint.

---

#### 3. `token_usage`

Tracks LLM token consumption and costs per agent invocation.

```sql
CREATE TABLE token_usage (
    id                    TEXT PRIMARY KEY,
    workflow_id           TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    agent                 TEXT NOT NULL,
    model                 TEXT NOT NULL DEFAULT 'claude-sonnet-4-20250514',
    input_tokens          INTEGER NOT NULL,
    output_tokens         INTEGER NOT NULL,
    cache_read_tokens     INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cost_usd              REAL NOT NULL,
    duration_ms           INTEGER NOT NULL DEFAULT 0,
    num_turns             INTEGER NOT NULL DEFAULT 1,
    timestamp             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Indexes:**
| Name | Definition |
|------|-----------|
| `idx_tokens_workflow` | `(workflow_id)` |
| `idx_tokens_agent` | `(agent)` |

---

#### 4. `prompts`

Stores prompt definitions for each agent.

```sql
CREATE TABLE prompts (
    id                 TEXT PRIMARY KEY,
    agent              TEXT NOT NULL,
    name               TEXT NOT NULL,
    description        TEXT,
    current_version_id TEXT          -- FK to prompt_versions.id (soft reference)
);
```

**Notes:**
- `current_version_id` has no explicit FK constraint (circular reference with `prompt_versions`).
- Seeded from `PROMPT_DEFAULTS` on startup via `initialize_prompts()`.

---

#### 5. `prompt_versions`

Versioned prompt content.

```sql
CREATE TABLE prompt_versions (
    id             TEXT PRIMARY KEY,
    prompt_id      TEXT NOT NULL REFERENCES prompts(id),
    version_number INTEGER NOT NULL,
    content        TEXT NOT NULL,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    change_note    TEXT,
    UNIQUE(prompt_id, version_number)
);
```

**Indexes:**
| Name | Definition |
|------|-----------|
| `idx_prompt_versions_prompt` | `(prompt_id)` |

---

#### 6. `workflow_prompt_versions`

Junction table linking workflows to the prompt versions they used.

```sql
CREATE TABLE workflow_prompt_versions (
    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    prompt_id   TEXT NOT NULL REFERENCES prompts(id),
    version_id  TEXT NOT NULL REFERENCES prompt_versions(id),
    PRIMARY KEY (workflow_id, prompt_id)
);
```

**Indexes:**
| Name | Definition |
|------|-----------|
| `idx_workflow_prompts_workflow` | `(workflow_id)` |

---

#### 7. `brainstorm_sessions`

Brainstorming session metadata.

```sql
CREATE TABLE brainstorm_sessions (
    id                 TEXT PRIMARY KEY,
    profile_id         TEXT NOT NULL,       -- no FK to profiles
    driver_session_id  TEXT,
    driver_type        TEXT,                -- added via ALTER TABLE migration
    status             TEXT NOT NULL DEFAULT 'active',
    topic              TEXT,
    created_at         TIMESTAMP NOT NULL,  -- no default (app-provided)
    updated_at         TIMESTAMP NOT NULL
);
```

**Indexes:**
| Name | Definition |
|------|-----------|
| `idx_brainstorm_sessions_profile` | `(profile_id)` |
| `idx_brainstorm_sessions_status` | `(status)` |

---

#### 8. `brainstorm_messages`

Messages within brainstorming sessions.

```sql
CREATE TABLE brainstorm_messages (
    id            TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL REFERENCES brainstorm_sessions(id) ON DELETE CASCADE,
    sequence      INTEGER NOT NULL,
    role          TEXT NOT NULL,              -- user | assistant
    content       TEXT NOT NULL,
    parts_json    TEXT,                       -- structured message parts
    created_at    TIMESTAMP NOT NULL,         -- no default (app-provided)
    input_tokens  INTEGER,                    -- added via ALTER TABLE
    output_tokens INTEGER,
    cost_usd      REAL,
    is_system     INTEGER NOT NULL DEFAULT 0, -- added via ALTER TABLE
    UNIQUE(session_id, sequence)
);
```

**Indexes:**
| Name | Definition |
|------|-----------|
| `idx_brainstorm_messages_session` | `(session_id, sequence)` |

---

#### 9. `brainstorm_artifacts`

Artifacts (specs, designs) generated during brainstorming.

```sql
CREATE TABLE brainstorm_artifacts (
    id         TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES brainstorm_sessions(id) ON DELETE CASCADE,
    type       TEXT NOT NULL,
    path       TEXT NOT NULL,
    title      TEXT,
    created_at TIMESTAMP NOT NULL
);
```

**Indexes:**
| Name | Definition |
|------|-----------|
| `idx_brainstorm_artifacts_session` | `(session_id)` |

---

#### 10. `server_settings`

Server configuration singleton.

```sql
CREATE TABLE server_settings (
    id                              INTEGER PRIMARY KEY CHECK (id = 1),
    log_retention_days              INTEGER NOT NULL DEFAULT 30,
    log_retention_max_events        INTEGER NOT NULL DEFAULT 100000,
    trace_retention_days            INTEGER NOT NULL DEFAULT 7,
    checkpoint_retention_days       INTEGER NOT NULL DEFAULT 0,
    checkpoint_path                 TEXT NOT NULL DEFAULT '~/.amelia/checkpoints.db',
    websocket_idle_timeout_seconds  REAL NOT NULL DEFAULT 300.0,
    workflow_start_timeout_seconds  REAL NOT NULL DEFAULT 60.0,
    max_concurrent                  INTEGER NOT NULL DEFAULT 5,
    stream_tool_results             INTEGER NOT NULL DEFAULT 0,
    created_at                      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

#### 11. `profiles`

User profiles for workflow execution.

```sql
CREATE TABLE profiles (
    id                TEXT PRIMARY KEY,       -- profile name
    tracker           TEXT NOT NULL DEFAULT 'noop',
    working_dir       TEXT NOT NULL,
    plan_output_dir   TEXT NOT NULL DEFAULT 'docs/plans',
    plan_path_pattern TEXT NOT NULL DEFAULT 'docs/plans/{date}-{issue_key}.md',
    agents            TEXT NOT NULL,          -- JSON: per-agent config {driver, model, options}
    is_active         INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Indexes:**
| Name | Definition |
|------|-----------|
| `idx_profiles_active` | `(is_active)` |

**Triggers:**
| Name | Fires | Purpose |
|------|-------|---------|
| `ensure_single_active_profile` | `AFTER UPDATE OF is_active` | Deactivate all other profiles when one is activated |
| `ensure_single_active_profile_insert` | `AFTER INSERT` | Same, for new profiles |

---

### Inline Migrations

The following ad-hoc migrations run inside `ensure_schema()` on every startup:

| Migration | Description |
|-----------|-------------|
| `ALTER TABLE workflows ADD COLUMN workflow_type/profile_id/plan_cache/issue_cache` | Phase 1: discrete columns replacing `state_json` |
| `ALTER TABLE workflows DROP COLUMN state_json` | Removed monolithic state blob (execution state now in LangGraph checkpoints) |
| `ALTER TABLE brainstorm_sessions ADD COLUMN driver_type` | Added driver type tracking |
| `ALTER TABLE brainstorm_messages ADD COLUMN input_tokens/output_tokens/cost_usd/is_system` | Added token tracking and system message flag |
| `UPDATE brainstorm_messages SET is_system = 1 WHERE ...` | Data migration for existing priming messages |
| `UPDATE profiles SET tracker = 'noop' WHERE tracker = 'none'` | Rename legacy tracker type |
| `UPDATE profiles SET agents = REPLACE(...)` | Rewrite legacy driver type strings in JSON |
| `UPDATE brainstorm_sessions SET driver_type = 'cli' WHERE ...` | Rewrite legacy driver types |
| `DROP INDEX + CREATE UNIQUE INDEX idx_workflows_active_worktree` | Recreate partial index with correct predicate |

---

### Summary

| Metric | Count |
|--------|-------|
| Tables | 11 |
| Indexes | 17 (15 regular + 2 unique) |
| Triggers | 2 |
| Foreign keys with CASCADE | 6 |
| Foreign keys without CASCADE | 2 (`prompt_versions.prompt_id`, `workflow_prompt_versions.prompt_id`) |
| Soft FKs (no constraint) | 2 (`prompts.current_version_id`, `brainstorm_sessions.profile_id`) |

---

## Proposed Schema Improvements

Changes to make before or during the PostgreSQL migration. Grouped by category.

### 1. Use native PostgreSQL types

**Problem:** SQLite's limited type system forces workarounds — UUIDs as TEXT, booleans as INTEGER, JSON as TEXT, money as REAL.

**Changes:**

| Column(s) | Current | Proposed | Rationale |
|-----------|---------|----------|-----------|
| All `id` PKs, all `*_id` FKs | `TEXT` | `UUID` | 16 bytes vs 36, native validation, better index performance |
| `data_json`, `parts_json`, `tool_input_json`, `agents`, `plan_cache` | `TEXT` | `JSONB` | Queryable, indexable, validated on INSERT. Also drop `_json` suffix where applicable. |
| `is_error`, `is_active`, `is_system`, `stream_tool_results` | `INTEGER` | `BOOLEAN` | Native type with `TRUE`/`FALSE` |
| `cost_usd` (token_usage, brainstorm_messages) | `REAL` | `NUMERIC(10,6)` | No floating-point rounding for monetary values |
| All `TIMESTAMP` / `TEXT` timestamp columns | Mixed | `TIMESTAMPTZ` | Timezone-aware, consistent across all tables |

**JSONB column renames:**

```
data_json        → data
parts_json       → parts
tool_input_json  → tool_input
```

> **Note:** `state_json` was removed in #389. Execution state now lives in LangGraph checkpoints. The new `plan_cache` column stores focused JSON (PlanCache model) and should become JSONB.

---

### 2. Add CHECK constraints for enums

**Problem:** Status and type columns accept arbitrary text. Invalid values are only caught by application code.

**Changes (verified against codebase 2026-01-31):**

```sql
-- workflows.status (from WorkflowStatus Literal type)
CHECK (status IN ('pending', 'in_progress', 'blocked', 'completed', 'failed', 'cancelled'))

-- workflows.workflow_type (from WorkflowType Literal type)
CHECK (workflow_type IN ('full', 'review'))

-- events.level (from EventLevel Literal type)
CHECK (level IN ('info', 'debug', 'trace'))

-- events.event_type (from EventType - many values for different domains)
-- Note: Event types are extensible; consider NOT adding a CHECK constraint here.
-- Current values include: workflow_created, workflow_started, workflow_completed, workflow_failed,
-- workflow_cancelled, stage_started, stage_completed, approval_required, approval_granted,
-- approval_rejected, file_created, file_modified, file_deleted, review_requested, review_completed,
-- revision_requested, agent_message, task_started, task_completed, task_failed, system_error,
-- system_warning, stream, claude_thinking, claude_tool_call, claude_tool_result, agent_output,
-- brainstorm_session_created, brainstorm_reasoning, brainstorm_tool_call, brainstorm_tool_result,
-- brainstorm_text, brainstorm_message_complete, brainstorm_artifact_created, brainstorm_session_completed,
-- oracle_consultation_started, oracle_consultation_thinking, oracle_tool_call, oracle_tool_result,
-- oracle_consultation_completed, oracle_consultation_failed

-- brainstorm_sessions.status (from BrainstormStatus Literal type)
CHECK (status IN ('active', 'ready_for_handoff', 'completed', 'failed'))

-- brainstorm_messages.role (actual stored values - no 'system' role)
CHECK (role IN ('user', 'assistant'))

-- brainstorm_artifacts.type (from _infer_artifact_type logic)
CHECK (type IN ('adr', 'spec', 'readme', 'design', 'document'))

-- profiles.tracker (from TrackerType Literal type)
CHECK (tracker IN ('noop', 'github', 'jira'))
```

> **Note:** `events.event_type` has many values across different domains (workflow, brainstorm, oracle). Consider using a PostgreSQL `text` type without CHECK constraint, or creating an enum type that can be extended via ALTER TYPE.

---

### 3. Add missing foreign key constraints

**Problem:** Two soft references have no database-enforced FK.

**Changes:**

| Column | Reference | Proposed |
|--------|-----------|----------|
| `prompts.current_version_id` | `prompt_versions(id)` | Add deferred FK: `REFERENCES prompt_versions(id) DEFERRABLE INITIALLY DEFERRED` (resolves circular dependency — insert prompt first, then version, then update FK) |
| `brainstorm_sessions.profile_id` | `profiles(id)` | Add FK: `REFERENCES profiles(id)` (no cascade — don't delete sessions when profile is deleted) |

---

### 4. Replace active-profile trigger with partial unique index

**Problem:** Two triggers enforce "one active profile" invariant. Triggers are harder to reason about and debug than constraints.

**Change:**

```sql
-- Drop triggers, replace with:
CREATE UNIQUE INDEX idx_profiles_single_active
    ON profiles (is_active)
    WHERE is_active = TRUE;
```

This prevents more than one `is_active = TRUE` row. Application code handles deactivating the old profile before activating a new one (already does this). The advantage: violations produce a clear constraint error instead of silent trigger side effects.

---

### 5. Add `updated_at` to workflows

**Problem:** The `workflows` table has `created_at`, `started_at`, and `completed_at` but no general `updated_at`. Status changes that don't set `started_at`/`completed_at` (e.g., `pending` → `blocked`) have no timestamp.

**Change:**

```sql
ALTER TABLE workflows ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
```

---

### 6. Remove hardcoded model default

**Problem:** `token_usage.model` defaults to `'claude-sonnet-4-20250514'`, a specific dated model. This will go stale as models are updated.

**Change:** Remove the column default. The application already provides the model name on every insert — the default is never actually used. Make it `NOT NULL` with no default so inserts without a model name fail explicitly.

```sql
model TEXT NOT NULL  -- no DEFAULT
```

---

### 7. Add `events.parent_id` FK constraint

**Problem:** `events.parent_id` references another event's `id` but has no FK constraint. Orphaned references are possible.

**Change:**

```sql
parent_id UUID REFERENCES events(id) ON DELETE SET NULL
```

`SET NULL` rather than `CASCADE` — if a parent event is deleted during retention cleanup, child events should still survive with a cleared parent.

---

### 8. Normalize `profiles.agents` JSON blob

**Problem:** Per-agent configuration is stored as a JSON blob in `profiles.agents`:
```json
{"architect": {"driver": "api", "model": "claude-sonnet-4"}, ...}
```
This isn't queryable, can't be validated by the database, and makes it impossible to FK-reference agent configs.

**Proposed: Keep as JSONB (don't normalize)**

This is a deliberate non-change. The structure is small (3 agents), the full blob is always read/written together, and JSONB already gives queryability. A separate `profile_agents` table would add JOINs for zero practical benefit.

---

### 9. Standardize timestamp defaults

**Problem:** Inconsistent timestamp handling:
- `workflows`, `events`, `token_usage`, `prompt_versions`: use `DEFAULT CURRENT_TIMESTAMP`
- `brainstorm_sessions`, `brainstorm_messages`, `brainstorm_artifacts`: no default (app-provided)
- `server_settings`, `profiles`: use `DEFAULT CURRENT_TIMESTAMP` (as TEXT)

**Change:** Standardize all to `TIMESTAMPTZ NOT NULL DEFAULT NOW()`. Application code can still override, but the database provides a fallback. This eliminates a class of bugs where application code forgets to set the timestamp.

---

### 10. Consider `events` table partitioning

**Problem:** The `events` table is the highest-volume table. A single workflow can produce thousands of events. With PostgreSQL's retention cleanup, DELETE operations on a large table are expensive.

**Proposed: Defer, but design for it.**

PostgreSQL native partitioning by `workflow_id` hash or by `timestamp` range would make retention cleanup efficient (`DROP PARTITION` vs `DELETE`). However, this adds complexity and may not be needed until event volume is actually a problem.

**Recommendation:** Don't partition in the initial migration. If retention cleanup becomes slow, add range partitioning by month on `timestamp`. The schema is already compatible — no changes needed now, just awareness.

---

### 11. Migration system for the initial schema

**Problem:** Current schema uses `CREATE TABLE IF NOT EXISTS` with inline `ALTER TABLE` migrations in `ensure_schema()`. This approach won't work once we need sequential, versioned migrations.

**Change (already planned in #308):**

```
amelia/server/database/migrations/
  001_initial_schema.sql       -- full PostgreSQL schema
  002_...sql                   -- future changes
```

With a `schema_migrations` tracking table. The `ensure_schema()` method is replaced by a `Migrator` that runs pending SQL files on startup.

---

## Summary of Changes

| # | Change | Impact | Effort | Status |
|---|--------|--------|--------|--------|
| 1 | Native PostgreSQL types (UUID, JSONB, BOOLEAN, NUMERIC, TIMESTAMPTZ) | All tables, all repositories | Part of migration rewrite | Pending |
| 2 | CHECK constraints for enums | All status/type columns | Low — add to CREATE TABLE | Pending (values verified) |
| 3 | Missing FK constraints | `prompts`, `brainstorm_sessions` | Low | Pending |
| 4 | Partial unique index replaces triggers | `profiles` | Low | Pending |
| 5 | Add `workflows.updated_at` | `workflows` table + repository | Low | Pending |
| 6 | Remove model default | `token_usage` | Trivial | Pending |
| 7 | `events.parent_id` FK | `events` table | Low | Pending |
| 8 | Keep `agents` as JSONB (no normalize) | None | None | N/A |
| 9 | Standardize timestamp defaults | All tables | Low — part of migration | Pending |
| 10 | Events partitioning | Deferred | — | Deferred |
| 11 | Migration system | New `migrations/` directory | Medium — already planned | Pending |

---

## Recent Schema Changes

Changes made since this review was created:

| PR | Change | Date |
|----|--------|------|
| #389 | Removed `state_json` blob, added discrete columns (`workflow_type`, `profile_id`, `plan_cache`, `issue_cache`) | 2026-01-31 |
| #386 | Removed `current_stage` from ServerExecutionState | 2026-01-30 |
| #385 | Removed `planned_at` field from ServerExecutionState | 2026-01-30 |

These changes align with the goal of moving away from monolithic JSON blobs. Execution state now lives in LangGraph checkpoints rather than the database.
