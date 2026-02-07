# PostgreSQL Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace SQLite with PostgreSQL across the entire database layer — connection, schema, repositories, checkpoints, tests, and CI.

**Architecture:** The `Database` class becomes an asyncpg connection pool wrapper. All 5 repositories switch from `?` params to `$1` numbered params and drop manual type conversions (asyncpg returns native Python types). The `OrchestratorService` uses a shared `AsyncPostgresSaver` instance instead of 7 per-call `AsyncSqliteSaver`. Schema is managed by versioned SQL migration files applied on startup.

**Tech Stack:** asyncpg, langgraph-checkpoint-postgres, PostgreSQL 16, Docker Compose for local dev

**Design doc:** `docs/plans/2026-01-19-postgresql-migration-design.md` — the authoritative source for schema DDL, decisions, and rationale.

---

## Prerequisites

Before starting, ensure PostgreSQL is running locally:
```bash
# Start PostgreSQL via Docker (Task 1 creates the compose file)
docker compose up -d postgres
```

---

## Task 1: Docker Compose and CI PostgreSQL service

**Files:**
- Create: `docker-compose.yml`
- Modify: `.github/workflows/ci.yml`

**Step 1: Create docker-compose.yml**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: amelia
      POSTGRES_PASSWORD: amelia
      POSTGRES_DB: amelia
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

**Step 2: Add PostgreSQL service container to CI**

In `.github/workflows/ci.yml`, add a `services` block to the `check` job and set the `DATABASE_URL` env var:

```yaml
jobs:
  check:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: amelia
          POSTGRES_PASSWORD: amelia
          POSTGRES_DB: amelia_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    env:
      DATABASE_URL: postgresql://amelia:amelia@localhost:5432/amelia_test
```

Keep all existing steps unchanged.

**Step 3: Commit**

```bash
git add docker-compose.yml .github/workflows/ci.yml
git commit -m "chore: add Docker Compose and CI PostgreSQL service"
```

---

## Task 2: Update dependencies in pyproject.toml

**Files:**
- Modify: `pyproject.toml`

**Step 1: Replace SQLite dependencies with PostgreSQL equivalents**

In the `[project] dependencies` list:
- Remove: `"aiosqlite>=0.20.0,<0.22.0"` and `"langgraph-checkpoint-sqlite>=3.0.0"`
- Add: `"asyncpg>=0.30.0"` and `"langgraph-checkpoint-postgres>=2.0.0"`

**Step 2: Sync dependencies**

Run: `uv sync`
Expected: Dependencies install without errors.

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: replace aiosqlite with asyncpg and checkpoint-postgres"
```

---

## Task 3: Update ServerConfig for PostgreSQL

**Files:**
- Modify: `amelia/server/config.py`

**Step 1: Write the failing test**

Create a quick sanity test in a new file:

```python
# tests/unit/server/test_config_pg.py
from amelia.server.config import ServerConfig

def test_server_config_has_database_url():
    config = ServerConfig(database_url="postgresql://localhost:5432/test")
    assert config.database_url == "postgresql://localhost:5432/test"

def test_server_config_default_database_url():
    config = ServerConfig()
    assert "postgresql://" in config.database_url

def test_server_config_pool_settings():
    config = ServerConfig()
    assert config.db_pool_min_size >= 1
    assert config.db_pool_max_size >= config.db_pool_min_size
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_config_pg.py -v`
Expected: FAIL — `database_url` attribute doesn't exist yet.

**Step 3: Update ServerConfig**

In `amelia/server/config.py`, replace the `database_path` field with:

```python
database_url: str = Field(
    default="postgresql://localhost:5432/amelia",
    description="PostgreSQL connection URL",
)
db_pool_min_size: int = Field(default=2, ge=1, description="Minimum pool connections")
db_pool_max_size: int = Field(default=10, ge=1, description="Maximum pool connections")
```

Remove the `Path` import if no longer needed.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_config_pg.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/config.py tests/unit/server/test_config_pg.py
git commit -m "feat: replace database_path with database_url in ServerConfig"
```

---

## Task 4: Rewrite Database class for asyncpg

This is the core connection layer. The new `Database` class wraps an asyncpg connection pool instead of a single aiosqlite connection.

**Files:**
- Modify: `amelia/server/database/connection.py`
- Modify: `tests/unit/server/database/test_connection.py`
- Modify: `tests/unit/server/database/conftest.py`
- Modify: `tests/conftest.py`

**Step 1: Write tests for new Database class**

Replace the contents of `tests/unit/server/database/test_connection.py` with tests for asyncpg behavior. These tests require a running PostgreSQL instance.

Key test cases:
- `test_connect_creates_pool` — after `connect()`, `pool` property returns an asyncpg pool
- `test_close_closes_pool` — after `close()`, pool is None
- `test_context_manager` — `async with Database(url)` connects and closes
- `test_is_healthy_returns_true` — connected database returns True
- `test_is_healthy_returns_false_when_not_connected` — returns False before connect
- `test_execute_runs_query` — INSERT returns row count
- `test_fetch_one_returns_record` — returns asyncpg.Record or None
- `test_fetch_all_returns_list` — returns list of Records
- `test_fetch_scalar_returns_value` — returns single value
- `test_transaction_commits_on_success` — data persists after transaction block
- `test_transaction_rolls_back_on_error` — data does not persist when exception raised

Mark all these tests with `@pytest.mark.integration` since they need a real PostgreSQL.

```python
# tests/unit/server/database/test_connection.py
import pytest
import asyncpg
from amelia.server.database.connection import Database

pytestmark = pytest.mark.integration

DATABASE_URL = "postgresql://amelia:amelia@localhost:5432/amelia_test"

@pytest.fixture
async def db():
    database = Database(DATABASE_URL)
    await database.connect()
    # Clean any test tables
    await database.execute("DROP TABLE IF EXISTS _test_table")
    await database.execute("CREATE TABLE _test_table (id SERIAL PRIMARY KEY, name TEXT)")
    yield database
    await database.execute("DROP TABLE IF EXISTS _test_table")
    await database.close()

async def test_connect_creates_pool(db):
    assert db.pool is not None

async def test_close_closes_pool():
    database = Database(DATABASE_URL)
    await database.connect()
    await database.close()
    assert database._pool is None

async def test_context_manager():
    async with Database(DATABASE_URL) as database:
        assert database.pool is not None
    assert database._pool is None

async def test_is_healthy(db):
    assert await db.is_healthy() is True

async def test_is_healthy_not_connected():
    database = Database(DATABASE_URL)
    assert await database.is_healthy() is False

async def test_execute_insert(db):
    count = await db.execute("INSERT INTO _test_table (name) VALUES ($1)", "alice")
    assert count == 1

async def test_fetch_one(db):
    await db.execute("INSERT INTO _test_table (name) VALUES ($1)", "bob")
    row = await db.fetch_one("SELECT name FROM _test_table WHERE name = $1", "bob")
    assert row is not None
    assert row["name"] == "bob"

async def test_fetch_one_returns_none(db):
    row = await db.fetch_one("SELECT name FROM _test_table WHERE name = $1", "nobody")
    assert row is None

async def test_fetch_all(db):
    await db.execute("INSERT INTO _test_table (name) VALUES ($1)", "alice")
    await db.execute("INSERT INTO _test_table (name) VALUES ($1)", "bob")
    rows = await db.fetch_all("SELECT name FROM _test_table ORDER BY name")
    assert len(rows) == 2
    assert rows[0]["name"] == "alice"

async def test_fetch_scalar(db):
    await db.execute("INSERT INTO _test_table (name) VALUES ($1)", "alice")
    count = await db.fetch_scalar("SELECT COUNT(*) FROM _test_table")
    assert count == 1

async def test_transaction_commits(db):
    async with db.transaction():
        await db.execute("INSERT INTO _test_table (name) VALUES ($1)", "committed")
    row = await db.fetch_one("SELECT name FROM _test_table WHERE name = $1", "committed")
    assert row is not None

async def test_transaction_rolls_back(db):
    with pytest.raises(ValueError):
        async with db.transaction():
            await db.execute("INSERT INTO _test_table (name) VALUES ($1)", "rolled_back")
            raise ValueError("force rollback")
    row = await db.fetch_one("SELECT name FROM _test_table WHERE name = $1", "rolled_back")
    assert row is None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/database/test_connection.py -v -m integration`
Expected: FAIL — Database class still uses aiosqlite.

**Step 3: Rewrite Database class**

Replace `amelia/server/database/connection.py` with an asyncpg pool implementation.

Key changes:
- `__init__` takes `database_url: str` instead of `db_path: Path`
- `connect()` creates `asyncpg.create_pool(database_url, min_size, max_size)` with `init=_init_connection` callback for type codecs
- `close()` calls `await self._pool.close()`
- `pool` property replaces `connection` property
- `execute(sql, *args)` uses `await self._pool.execute(sql, *args)` — note asyncpg uses positional args, not a sequence
- `fetch_one(sql, *args)` uses `await self._pool.fetchrow(sql, *args)`
- `fetch_all(sql, *args)` uses `await self._pool.fetch(sql, *args)`
- `fetch_scalar(sql, *args)` uses `await self._pool.fetchval(sql, *args)`
- `transaction()` uses `async with self._pool.acquire() as conn: async with conn.transaction():`
- `is_healthy()` uses `await self._pool.fetchval('SELECT 1')`
- Remove: all SQLite PRAGMAs, `aiosqlite` imports, `ensure_schema()` (moves to migrator), `initialize_prompts()` (moves to migrator), `_check_old_profiles_schema()`, `execute_insert()`, `execute_many()`
- Remove the `SqliteValue` type alias

The `execute` method should parse the `rowcount` from asyncpg's status string (e.g. `"INSERT 0 1"` → 1):

```python
async def execute(self, sql: str, *args: Any) -> int:
    status = await self.pool.execute(sql, *args)
    # asyncpg returns status string like "INSERT 0 1" or "DELETE 3"
    try:
        return int(status.split()[-1])
    except (ValueError, IndexError, AttributeError):
        return 0
```

**Important:** asyncpg parameters are positional `*args`, not a sequence. This changes the call signature from `execute(sql, (param1, param2))` to `execute(sql, param1, param2)`. All repository callers must be updated accordingly (Tasks 7-11).

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/database/test_connection.py -v -m integration`
Expected: PASS

**Step 5: Update test fixtures**

Update `tests/unit/server/database/conftest.py`:
- Replace `connected_db` and `db_with_schema` fixtures to use `Database(database_url)` instead of `Database(temp_db_path)`
- The `db_with_schema` fixture should call the migrator (from Task 5) instead of `ensure_schema()`
- Use `TRUNCATE ... CASCADE` in teardown instead of relying on temp file deletion

Update `tests/conftest.py`:
- Replace or remove `temp_db_path` fixture — no longer needed since PostgreSQL doesn't use file paths
- Add a `database_url` fixture that reads from `DATABASE_URL` env var with fallback to `postgresql://amelia:amelia@localhost:5432/amelia_test`

**Note:** Don't try to get all tests passing in this task. Focus on the connection tests. Repository tests will be updated in Tasks 7-11.

**Step 6: Commit**

```bash
git add amelia/server/database/connection.py tests/unit/server/database/test_connection.py tests/unit/server/database/conftest.py tests/conftest.py
git commit -m "feat: rewrite Database class for asyncpg connection pool"
```

---

## Task 5: Schema migration system

Create the migrator and initial schema SQL file. The schema DDL comes from the design doc (`docs/plans/2026-01-19-postgresql-migration-design.md`).

**Files:**
- Create: `amelia/server/database/migrations/001_initial_schema.sql`
- Create: `amelia/server/database/migrator.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/database/test_migrator.py
import pytest
from amelia.server.database.connection import Database
from amelia.server.database.migrator import Migrator

pytestmark = pytest.mark.integration

DATABASE_URL = "postgresql://amelia:amelia@localhost:5432/amelia_test"

@pytest.fixture
async def db():
    database = Database(DATABASE_URL)
    await database.connect()
    # Drop all tables to test fresh migration
    await database.execute("DROP SCHEMA public CASCADE")
    await database.execute("CREATE SCHEMA public")
    yield database
    await database.close()

async def test_migrator_creates_schema_migrations_table(db):
    migrator = Migrator(db)
    await migrator.run()
    row = await db.fetch_one(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'schema_migrations')"
    )
    assert row[0] is True

async def test_migrator_applies_initial_schema(db):
    migrator = Migrator(db)
    await migrator.run()
    # Check that all core tables exist
    for table in ["workflows", "workflow_log", "token_usage", "profiles", "server_settings",
                  "prompts", "prompt_versions", "workflow_prompt_versions",
                  "brainstorm_sessions", "brainstorm_messages", "brainstorm_artifacts"]:
        row = await db.fetch_one(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = $1)",
            table,
        )
        assert row[0] is True, f"Table {table} not created"

async def test_migrator_records_version(db):
    migrator = Migrator(db)
    await migrator.run()
    version = await db.fetch_scalar("SELECT MAX(version) FROM schema_migrations")
    assert version == 1

async def test_migrator_is_idempotent(db):
    migrator = Migrator(db)
    await migrator.run()
    await migrator.run()  # Should not fail
    version = await db.fetch_scalar("SELECT MAX(version) FROM schema_migrations")
    assert version == 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_migrator.py -v -m integration`
Expected: FAIL — `migrator` module doesn't exist.

**Step 3: Create initial schema SQL**

Create `amelia/server/database/migrations/001_initial_schema.sql` containing all table definitions from the design doc. This is a single file covering ALL tables.

Key points from the design doc:
- Use `UUID` for all primary/foreign keys
- Use `TIMESTAMPTZ` for all timestamps with `DEFAULT NOW()`
- Use `JSONB` for `data`, `parts`, `agents`, `plan_cache`, `issue_cache` columns
- Use `BOOLEAN` for `is_error`, `is_active`, `is_system`, `stream_tool_results`
- Use `NUMERIC(10,6)` for `cost_usd`
- Include all indexes from the design doc
- Include partial unique indexes for active worktree and active profile
- Include the `UNIQUE(workflow_id, sequence)` constraint on `workflow_log`
- Remove brainstorm events from the `event_type` CHECK constraint (per design doc recommendation — brainstorm has its own tables)
- Remove `checkpoint_path` and `log_retention_max_events` from `server_settings`
- Include `schema_migrations` table

**Decision from design doc:** Remove brainstorm event types from `workflow_log.event_type` CHECK — brainstorm already has dedicated tables.

```sql
-- Schema migrations tracking
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ DEFAULT NOW()
);

-- Profiles
CREATE TABLE profiles (
    id TEXT PRIMARY KEY,
    tracker TEXT NOT NULL DEFAULT 'noop',
    working_dir TEXT NOT NULL,
    plan_output_dir TEXT NOT NULL DEFAULT 'docs/plans',
    plan_path_pattern TEXT NOT NULL DEFAULT 'docs/plans/{date}-{issue_key}.md',
    agents JSONB NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_profiles_active ON profiles(is_active) WHERE is_active = TRUE;

-- Workflows
CREATE TABLE workflows (
    id UUID PRIMARY KEY,
    issue_id TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failure_reason TEXT,
    workflow_type TEXT NOT NULL DEFAULT 'full',
    profile_id TEXT,
    plan_cache JSONB,
    issue_cache JSONB
);
CREATE INDEX idx_workflows_issue_id ON workflows(issue_id);
CREATE INDEX idx_workflows_status ON workflows(status);
CREATE INDEX idx_workflows_worktree ON workflows(worktree_path);
CREATE INDEX idx_workflows_started_at ON workflows(started_at DESC);
CREATE UNIQUE INDEX idx_workflows_active_worktree
    ON workflows(worktree_path) WHERE status IN ('pending', 'in_progress', 'blocked');

-- Workflow log
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
CREATE INDEX idx_workflow_log_workflow ON workflow_log(workflow_id, sequence);
CREATE INDEX idx_workflow_log_errors ON workflow_log(workflow_id) WHERE is_error = TRUE;

-- Token usage
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

-- Prompts
CREATE TABLE prompts (
    id TEXT PRIMARY KEY,
    agent TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    current_version_id TEXT
);

CREATE TABLE prompt_versions (
    id TEXT PRIMARY KEY,
    prompt_id TEXT NOT NULL REFERENCES prompts(id),
    version_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    change_note TEXT,
    UNIQUE(prompt_id, version_number)
);

CREATE TABLE workflow_prompt_versions (
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    prompt_id TEXT NOT NULL REFERENCES prompts(id),
    version_id TEXT NOT NULL REFERENCES prompt_versions(id),
    PRIMARY KEY (workflow_id, prompt_id)
);

-- Server settings (singleton)
CREATE TABLE server_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    log_retention_days INTEGER NOT NULL DEFAULT 30,
    checkpoint_retention_days INTEGER NOT NULL DEFAULT 0,
    websocket_idle_timeout_seconds NUMERIC NOT NULL DEFAULT 300.0,
    workflow_start_timeout_seconds NUMERIC NOT NULL DEFAULT 60.0,
    max_concurrent INTEGER NOT NULL DEFAULT 5,
    stream_tool_results BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Brainstorm sessions
CREATE TABLE brainstorm_sessions (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    driver_session_id TEXT,
    driver_type TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    topic TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_brainstorm_sessions_profile ON brainstorm_sessions(profile_id);
CREATE INDEX idx_brainstorm_sessions_status ON brainstorm_sessions(status);

-- Brainstorm messages
CREATE TABLE brainstorm_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES brainstorm_sessions(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    parts JSONB,
    created_at TIMESTAMPTZ NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd NUMERIC(10,6),
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(session_id, sequence)
);
CREATE INDEX idx_brainstorm_messages_session ON brainstorm_messages(session_id, sequence);

-- Brainstorm artifacts
CREATE TABLE brainstorm_artifacts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES brainstorm_sessions(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_brainstorm_artifacts_session ON brainstorm_artifacts(session_id);

-- Prompt indexes
CREATE INDEX idx_prompt_versions_prompt ON prompt_versions(prompt_id);
CREATE INDEX idx_workflow_prompts_workflow ON workflow_prompt_versions(workflow_id);
```

**Step 4: Create Migrator class**

Create `amelia/server/database/migrator.py`:

```python
"""Schema migration runner for PostgreSQL."""

from importlib import resources
from loguru import logger
from amelia.server.database.connection import Database


class Migrator:
    """Runs versioned SQL migrations on startup."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def run(self) -> None:
        """Apply pending migrations."""
        await self._ensure_migrations_table()
        current = await self._current_version()
        migrations = self._load_migrations()

        for version, sql in migrations:
            if version > current:
                logger.info("Applying migration", version=version)
                await self._db.execute(sql)
                await self._db.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)", version
                )
                logger.info("Migration applied", version=version)

    async def _ensure_migrations_table(self) -> None:
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

    async def _current_version(self) -> int:
        result = await self._db.fetch_scalar(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
        )
        return int(result) if result is not None else 0

    def _load_migrations(self) -> list[tuple[int, str]]:
        """Load SQL migration files from the migrations directory."""
        migrations_dir = resources.files("amelia.server.database") / "migrations"
        result = []
        for path in sorted(migrations_dir.iterdir()):
            name = path.name if hasattr(path, 'name') else str(path).split('/')[-1]
            if name.endswith(".sql") and name[:3].isdigit():
                version = int(name[:3])
                sql = path.read_text(encoding="utf-8")
                result.append((version, sql))
        return sorted(result, key=lambda x: x[0])
```

Also create `amelia/server/database/migrations/__init__.py` (empty file for package discovery).

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/database/test_migrator.py -v -m integration`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/database/migrations/ amelia/server/database/migrator.py tests/unit/server/database/test_migrator.py
git commit -m "feat: add schema migrator and initial PostgreSQL schema"
```

---

## Task 6: Prompt initialization in migrator

The `Database.initialize_prompts()` method seeded the prompts table. Move this logic into the migrator or into a post-migration step.

**Files:**
- Modify: `amelia/server/database/migrator.py`
- Modify: `amelia/server/database/connection.py` (remove `initialize_prompts`)

**Step 1: Add prompt seeding to migrator**

Add an `initialize_prompts` method to `Migrator` that reads from `PROMPT_DEFAULTS` and inserts if not exists. This mirrors what `Database.initialize_prompts()` does today, using `$1` syntax.

```python
async def initialize_prompts(self) -> None:
    """Seed prompts table from defaults. Idempotent."""
    for prompt_id, default in PROMPT_DEFAULTS.items():
        existing = await self._db.fetch_one(
            "SELECT 1 FROM prompts WHERE id = $1", prompt_id
        )
        if not existing:
            await self._db.execute(
                """INSERT INTO prompts (id, agent, name, description, current_version_id)
                   VALUES ($1, $2, $3, $4, NULL)""",
                prompt_id, default.agent, default.name, default.description,
            )
```

**Step 2: Remove methods from Database class**

Remove `ensure_schema()`, `initialize_prompts()`, and `_check_old_profiles_schema()` from `connection.py`. These are no longer needed — the migrator handles schema and the old profiles check is SQLite-specific.

**Step 3: Commit**

```bash
git add amelia/server/database/migrator.py amelia/server/database/connection.py
git commit -m "refactor: move prompt initialization to migrator"
```

---

## Task 7: Update WorkflowRepository for asyncpg

This is the largest repository with ~27 methods. All queries need `?` → `$N` conversion, and row conversions drop manual type parsing.

**Files:**
- Modify: `amelia/server/database/repository.py`

**Step 1: Global changes across all methods**

Apply these systematic changes:

1. **Import**: Replace `import aiosqlite` with `import asyncpg`. Change all type hints from `aiosqlite.Row` to `asyncpg.Record`.

2. **Parameter syntax**: Every `?` becomes `$1`, `$2`, etc. in order. Every `execute(sql, (param1, param2))` becomes `execute(sql, param1, param2)` (positional args, not tuple).

3. **Column renames in queries**:
   - `data_json` → `data` in all workflow_log queries
   - `is_error` values: `1`/`0` → `TRUE`/`FALSE` (or just pass Python bool directly)

4. **Row conversions** (`_row_to_*` methods):
   - Remove `datetime.fromisoformat()` calls — asyncpg returns native `datetime`
   - Remove `bool()` casts — asyncpg returns native `bool`
   - Remove `json.loads()` for `data_json` — asyncpg returns Python dict for JSONB
   - `_row_to_event`: `data_json` key → `data`, no `json.loads` needed, no `bool()` cast
   - `_row_to_token_usage`: Remove `datetime.fromisoformat()` for timestamp
   - `_row_to_state`: `plan_cache` column is now JSONB (dict), not TEXT; use `PlanCache.model_validate(row["plan_cache"])` instead of `model_validate_json`

5. **DATE() function**: In `get_usage_trend` and `get_usage_by_model`, replace `DATE(t.timestamp)` with `t.timestamp::date`

6. **save_event method**:
   - Remove `json.dumps(serialized["data"])` — pass the dict directly (asyncpg serializes JSONB automatically)
   - Pass `event.is_error` directly (bool), not `1 if event.is_error else 0`
   - Pass `event.timestamp` directly (datetime), not `.isoformat()`
   - Column: `data_json` → `data`

7. **create method**:
   - `plan_cache`: Use `.model_dump()` (dict) instead of `.model_dump_json()` (string) for JSONB
   - Pass datetimes directly, not as strings

8. **update method**: Same datetime/bool/JSONB adjustments

**Step 2: Update tests**

Update `tests/unit/server/database/test_repository.py` and related files:
- Mark with `pytestmark = pytest.mark.integration`
- Use the new PostgreSQL-based fixtures
- Remove any SQLite-specific assertions
- UUID primary keys: workflow IDs should be UUIDs. Update test data accordingly (the app currently uses string IDs like `"wf-test"` — these will need to be valid UUIDs since the column is `UUID` type)

**Important note on IDs:** The design doc specifies `UUID` for workflow IDs, token_usage IDs, and workflow_log IDs. The current code uses string IDs like `"wf-test"`. You have two options:
- (a) Use `TEXT` instead of `UUID` for these columns to maintain backward compatibility with string IDs — simpler
- (b) Generate proper UUIDs everywhere — more work but cleaner

**Recommendation:** Use `TEXT` for `profiles.id` (profile names are human-readable strings like "work"), `prompts.id`, `prompt_versions.id`, `brainstorm_sessions.id`, `brainstorm_messages.id`, `brainstorm_artifacts.id` (all currently strings). Use `UUID` only for `workflows.id`, `workflow_log.id`, `token_usage.id` — these are already generated UUIDs in the codebase.

**Step 3: Run tests**

Run: `uv run pytest tests/unit/server/database/test_repository.py -v -m integration`
Expected: PASS

**Step 4: Commit**

```bash
git add amelia/server/database/repository.py tests/unit/server/database/test_repository.py
git commit -m "feat: update WorkflowRepository for asyncpg"
```

Repeat for `test_repository_tokens.py`, `test_repository_usage.py`, `test_repository_backfill.py`, and `test_usage_repository.py`. Commit each fix as you go.

---

## Task 8: Update SettingsRepository for asyncpg

**Files:**
- Modify: `amelia/server/database/settings_repository.py`
- Modify: `tests/unit/server/database/test_schema.py` (settings tests)

**Step 1: Update ServerSettings model**

Remove `checkpoint_path` and `log_retention_max_events` fields from `ServerSettings`:

```python
class ServerSettings(BaseModel):
    """Server settings data class."""
    log_retention_days: int
    checkpoint_retention_days: int
    websocket_idle_timeout_seconds: float
    workflow_start_timeout_seconds: float
    max_concurrent: int
    stream_tool_results: bool
    created_at: datetime
    updated_at: datetime
```

**Step 2: Update repository methods**

- `ensure_defaults`: Change `INSERT OR IGNORE` to `INSERT INTO server_settings (id) VALUES (1) ON CONFLICT DO NOTHING`
- `_row_to_settings`: Remove `checkpoint_path` and `log_retention_max_events`, remove `bool()` cast (asyncpg native), remove `datetime.fromisoformat()` (asyncpg native)
- `update_server_settings`: Remove `checkpoint_path` and `log_retention_max_events` from `valid_fields`. Replace `CURRENT_TIMESTAMP` with `NOW()`. Use `$N` params.
- `get_server_settings`: Use `$1` syntax.

**Step 3: Update tests, run, commit**

```bash
git add amelia/server/database/settings_repository.py tests/unit/server/database/test_schema.py
git commit -m "feat: update SettingsRepository for asyncpg, remove checkpoint_path"
```

---

## Task 9: Update ProfileRepository for asyncpg

**Files:**
- Modify: `amelia/server/database/profile_repository.py`
- Modify: `tests/unit/server/database/test_profile_repository.py`

**Step 1: Update repository methods**

- All `?` → `$N` params, positional args
- `_row_to_profile`: `json.loads(row["agents"])` → use `row["agents"]` directly (JSONB returns dict). Remove `is_active` parsing (if used elsewhere — currently `_row_to_profile` doesn't use it, but `set_active` and `list_profiles` queries reference it)
- `set_active`: The SQLite trigger for single-active-profile is replaced by the partial unique index `idx_profiles_active`. The repository needs to explicitly deactivate other profiles before activating the new one (since triggers are gone):

```python
async def set_active(self, profile_id: str) -> None:
    async with self._db.transaction():
        await self._db.execute("UPDATE profiles SET is_active = FALSE WHERE is_active = TRUE")
        result = await self._db.execute(
            "UPDATE profiles SET is_active = TRUE, updated_at = NOW() WHERE id = $1",
            profile_id,
        )
        if result == 0:
            raise ValueError(f"Profile not found: {profile_id}")
```

- `create_profile`: The agents column should be passed as a dict (for JSONB), not `json.dumps()`. Actually, asyncpg requires you to pass JSON as a string for `JSONB` columns — use `json.dumps()` and cast with `$N::jsonb` in the SQL. OR register a custom JSONB codec on the pool. **Simpler approach:** use `json.dumps()` and `$N::jsonb` cast in SQL.

**Step 2: Update tests, run, commit**

```bash
git add amelia/server/database/profile_repository.py tests/unit/server/database/test_profile_repository.py
git commit -m "feat: update ProfileRepository for asyncpg"
```

---

## Task 10: Update BrainstormRepository for asyncpg

**Files:**
- Modify: `amelia/server/database/brainstorm_repository.py`
- Modify: `tests/unit/server/database/test_brainstorm_repository.py`
- Modify: `tests/unit/server/database/test_brainstorm_schema.py`

**Step 1: Update repository methods**

- All `?` → `$N`, positional args
- Column renames in queries: `parts_json` → `parts`
- `_row_to_message`: `json.loads(row["parts_json"])` → `row["parts"]` (JSONB returns list of dicts directly). `datetime.fromisoformat` → direct use.
- `_row_to_session`: Remove `datetime.fromisoformat()` calls.
- `_row_to_artifact`: Remove `datetime.fromisoformat()` if present.
- `save_message`: `parts_json` param → `parts`, pass as `json.dumps()` with `::jsonb` cast (or dict if codec registered). `cost_usd` is now `NUMERIC(10,6)` — asyncpg handles `Decimal`, but float works too.
- Remove `is_system` int→bool conversion (`0`/`1` → native bool)

**Step 2: Update tests, run, commit**

```bash
git add amelia/server/database/brainstorm_repository.py tests/unit/server/database/test_brainstorm_repository.py tests/unit/server/database/test_brainstorm_schema.py
git commit -m "feat: update BrainstormRepository for asyncpg"
```

---

## Task 11: Update PromptRepository for asyncpg

**Files:**
- Modify: `amelia/server/database/prompt_repository.py`
- Modify: `tests/unit/server/database/test_prompt_repository.py`
- Modify: `tests/unit/server/database/test_prompt_schema.py`

**Step 1: Update repository methods**

- All `?` → `$N`, positional args
- `record_workflow_prompt`: `INSERT OR REPLACE` → `INSERT INTO ... ON CONFLICT (workflow_id, prompt_id) DO UPDATE SET version_id = EXCLUDED.version_id`
- Row conversions: remove `datetime.fromisoformat()` for `created_at`

**Step 2: Update tests, run, commit**

```bash
git add amelia/server/database/prompt_repository.py tests/unit/server/database/test_prompt_repository.py tests/unit/server/database/test_prompt_schema.py
git commit -m "feat: update PromptRepository for asyncpg"
```

---

## Task 12: Replace AsyncSqliteSaver with shared AsyncPostgresSaver

The orchestrator currently creates 7 `AsyncSqliteSaver.from_conn_string()` contexts. Replace with a single shared `AsyncPostgresSaver` instance.

**Files:**
- Modify: `amelia/server/orchestrator/service.py`
- Modify: `amelia/server/main.py`

**Step 1: Update OrchestratorService.__init__**

Replace `checkpoint_path: str` parameter with `checkpointer: AsyncPostgresSaver`:

```python
def __init__(
    self,
    event_bus: EventBus,
    repository: WorkflowRepository,
    profile_repo: ProfileRepository | None = None,
    max_concurrent: int = 5,
    checkpointer: AsyncPostgresSaver | None = None,
) -> None:
    ...
    self._checkpointer = checkpointer
    # Remove: self._checkpoint_path and all Path expansion logic
```

**Step 2: Replace all 7 AsyncSqliteSaver usages**

Find all 7 locations with `async with AsyncSqliteSaver.from_conn_string(self._checkpoint_path) as checkpointer:` and replace the pattern:

Before:
```python
async with AsyncSqliteSaver.from_conn_string(self._checkpoint_path) as checkpointer:
    graph = self._create_server_graph(checkpointer)
    # ... use graph ...
```

After:
```python
graph = self._create_server_graph(self._checkpointer)
# ... use graph (no async with needed) ...
```

This eliminates the context manager indentation. The shared checkpointer persists for the app lifetime.

Also update `_delete_checkpoint` method — it currently opens a separate aiosqlite connection to delete checkpoint rows. With PostgreSQL, use the shared pool:

```python
async def _delete_checkpoint(self, workflow_id: str) -> None:
    """Delete checkpoint for a workflow."""
    if self._checkpointer is None:
        return
    # Use the pool from the checkpointer to delete
    pool = self._checkpointer.pool  # or however the pool is exposed
    await pool.execute("DELETE FROM checkpoints WHERE thread_id = $1", workflow_id)
    await pool.execute("DELETE FROM writes WHERE thread_id = $1", workflow_id)
```

Check the `langgraph-checkpoint-postgres` API for the correct way to access the pool and delete checkpoints.

**Step 3: Update imports**

Remove: `from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver`
Add: `from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver`

**Step 4: Update main.py lifespan**

In the `lifespan` function:

```python
# Before (SQLite):
orchestrator = OrchestratorService(
    event_bus=event_bus,
    repository=repository,
    profile_repo=profile_repo,
    max_concurrent=server_settings.max_concurrent,
    checkpoint_path=server_settings.checkpoint_path,
)

# After (PostgreSQL):
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

checkpointer = AsyncPostgresSaver(database.pool)
await checkpointer.setup()  # Creates checkpoint tables if needed

orchestrator = OrchestratorService(
    event_bus=event_bus,
    repository=repository,
    profile_repo=profile_repo,
    max_concurrent=server_settings.max_concurrent,
    checkpointer=checkpointer,
)
```

Also update the database initialization to use the migrator:

```python
# Before:
database = Database(config.database_path)
await database.connect()
await database.ensure_schema()
await database.initialize_prompts()

# After:
database = Database(config.database_url, min_size=config.db_pool_min_size, max_size=config.db_pool_max_size)
await database.connect()
migrator = Migrator(database)
await migrator.run()
await migrator.initialize_prompts()
```

Remove the `checkpoint_path` reference in `LogRetentionService` instantiation (Task 13 handles this).

Update `log_server_startup` call: replace `database_path=str(config.database_path)` with `database_url=config.database_url`.

**Step 5: Commit**

```bash
git add amelia/server/orchestrator/service.py amelia/server/main.py
git commit -m "feat: replace AsyncSqliteSaver with shared AsyncPostgresSaver"
```

---

## Task 13: Update LogRetentionService for PostgreSQL

**Files:**
- Modify: `amelia/server/lifecycle/retention.py`

**Step 1: Update cleanup_on_shutdown**

- Replace `?` params with `$1` and pass as positional args
- Pass datetime directly instead of `.isoformat()`

**Step 2: Rewrite _cleanup_checkpoints**

Remove the separate `aiosqlite.connect()` call. Use the shared database pool:

```python
async def _cleanup_checkpoints(self) -> int:
    """Delete LangGraph checkpoints for finished workflows."""
    retention_days = self._config.checkpoint_retention_days
    if retention_days < 0:
        return 0

    if retention_days == 0:
        finished = await self._db.fetch_all(
            "SELECT id FROM workflows WHERE status IN ('completed', 'failed', 'cancelled')"
        )
    else:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        finished = await self._db.fetch_all(
            "SELECT id FROM workflows WHERE status IN ('completed', 'failed', 'cancelled') AND completed_at < $1",
            cutoff,
        )

    if not finished:
        return 0

    workflow_ids = [row["id"] for row in finished]
    total = 0
    try:
        for wf_id in workflow_ids:
            r1 = await self._db.execute("DELETE FROM checkpoints WHERE thread_id = $1", str(wf_id))
            r2 = await self._db.execute("DELETE FROM writes WHERE thread_id = $1", str(wf_id))
            total += r1 + r2
    except Exception as e:
        logger.warning("Failed to cleanup checkpoints", error=str(e))

    return total
```

Remove:
- `checkpoint_path` parameter from `__init__`
- `aiosqlite` import
- All file-path based checkpoint access

Update `__init__` signature:
```python
def __init__(self, db: Any, config: Any) -> None:
    self._db = db
    self._config = config
```

**Step 3: Update main.py LogRetentionService instantiation**

```python
# Before:
log_retention = LogRetentionService(
    db=database,
    config=server_settings,
    checkpoint_path=Path(server_settings.checkpoint_path),
)

# After:
log_retention = LogRetentionService(db=database, config=server_settings)
```

**Step 4: Commit**

```bash
git add amelia/server/lifecycle/retention.py amelia/server/main.py
git commit -m "feat: update LogRetentionService for PostgreSQL shared pool"
```

---

## Task 14: Update __init__.py exports and type check

**Files:**
- Modify: `amelia/server/database/__init__.py`

**Step 1: Update exports**

Add `Migrator` to exports. Update the module docstring to say PostgreSQL instead of SQLite.

```python
"""Database package for Amelia server.

Provides PostgreSQL database connectivity and repository patterns for workflow
persistence. Handles connection pooling, schema migration, and CRUD
operations for workflow state.
"""

from amelia.server.database.connection import Database
from amelia.server.database.migrator import Migrator
from amelia.server.database.profile_repository import ProfileRecord, ProfileRepository
from amelia.server.database.repository import WorkflowRepository
from amelia.server.database.settings_repository import ServerSettings, SettingsRepository

__all__ = [
    "Database",
    "Migrator",
    "ProfileRecord",
    "ProfileRepository",
    "ServerSettings",
    "SettingsRepository",
    "WorkflowRepository",
]
```

**Step 2: Run type checking**

Run: `uv run mypy amelia`
Expected: No type errors (fix any that arise from the migration).

**Step 3: Run linting**

Run: `uv run ruff check amelia tests`
Expected: No lint errors.

**Step 4: Commit**

```bash
git add amelia/server/database/__init__.py
git commit -m "refactor: update database package exports for PostgreSQL"
```

---

## Task 15: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update configuration section**

Replace SQLite references with PostgreSQL:
- `AMELIA_DATABASE_PATH` → `AMELIA_DATABASE_URL` with default `postgresql://localhost:5432/amelia`
- Remove `AMELIA_CHECKPOINT_PATH` — checkpoints share the PostgreSQL database
- Add `AMELIA_DB_POOL_MIN_SIZE` (default 2) and `AMELIA_DB_POOL_MAX_SIZE` (default 10)
- Update the Configuration section description

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for PostgreSQL configuration"
```

---

## Task 16: Clean up remaining SQLite references

**Files:** Various

**Step 1: Search for remaining SQLite references**

Run: `rg -l "sqlite\|aiosqlite\|PRAGMA\|SqliteValue\|temp_db_path\|checkpoint_path" amelia/ tests/ --type py`

Fix any remaining references found. Common locations:
- Test files still importing aiosqlite types
- Any remaining `datetime.fromisoformat()` in row conversions you missed
- The `temp_db_path` fixture in `tests/conftest.py`

**Step 2: Search for remaining `?` params in SQL**

Run: `rg "VALUES\s*\(" amelia/server/database/ --type py | grep "?"` to find unconverted queries.

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v -m integration`
Expected: All tests pass.

Run: `uv run pytest tests/unit/ -v -m "not integration"`
Expected: Non-database tests still pass.

**Step 4: Run linting and type checking**

Run: `uv run ruff check amelia tests && uv run mypy amelia`
Expected: Clean.

**Step 5: Commit any fixes**

```bash
git add -A
git commit -m "chore: remove remaining SQLite references"
```

---

## Task 17: Integration smoke test

**Step 1: Start PostgreSQL**

```bash
docker compose up -d postgres
```

**Step 2: Run the server**

```bash
AMELIA_DATABASE_URL=postgresql://amelia:amelia@localhost:5432/amelia uv run amelia dev
```

Expected: Server starts, migrations run, no errors.

**Step 3: Check dashboard**

Open `http://localhost:8420` — dashboard should load, settings page should work.

**Step 4: Verify database tables**

```bash
docker compose exec postgres psql -U amelia -c "\dt"
```

Expected: All tables exist (workflows, workflow_log, token_usage, profiles, etc.)

---

## Summary of removed fields

| Removed | Location | Reason |
|---------|----------|--------|
| `checkpoint_path` | ServerSettings, server_settings table, OrchestratorService.__init__ | Checkpoints share PostgreSQL database |
| `log_retention_max_events` | ServerSettings, server_settings table | Retention is time-based only |
| `database_path` | ServerConfig | Replaced by `database_url` |
| `ensure_schema()` | Database class | Replaced by Migrator |
| `initialize_prompts()` | Database class | Moved to Migrator |
| `_check_old_profiles_schema()` | Database class | SQLite-specific migration |
| `execute_insert()` | Database class | Not needed with asyncpg |
| `execute_many()` | Database class | Not needed (use executemany on pool if needed) |
| `SqliteValue` | connection.py | SQLite-specific type alias |
| SQLite triggers | Schema | Replaced by partial unique index + explicit deactivation |
