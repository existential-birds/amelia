# PostgreSQL Migration Design

## Overview

Migrate Amelia from SQLite to PostgreSQL to enable distributed workers and shared dashboard access.

## Motivation

| Driver | Priority |
|--------|----------|
| Distributed workers - workflow execution across multiple machines | Primary |
| Shared dashboard - multiple developers accessing same workflows | Secondary |
| pg_vector for embeddings (future) | Deferred |

## Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Database | PostgreSQL only, remove SQLite | Distributed workers require remote DB access |
| Driver | asyncpg with connection pooling | Async, fast, native PostgreSQL support |
| Migrations | Version-based SQL files | Simple, no ORM overhead, full PostgreSQL feature access |
| pg_vector | Deferred | Data model for Knowledge Library/Oracle not yet defined |
| Backwards compatibility | None | Single user, no migration from SQLite needed |

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

## Schema Changes

### SQLite to PostgreSQL mapping

| SQLite | PostgreSQL |
|--------|------------|
| `TEXT` for JSON | `JSONB` (queryable) |
| `?` parameters | `$1, $2, ...` parameters |
| `CURRENT_TIMESTAMP` | `NOW()` |

### JSONB columns

These columns become JSONB for queryability:
- `state_json` → `state JSONB`
- `data_json` → `data JSONB`
- `parts_json` → `parts JSONB`
- `tool_input_json` → `tool_input JSONB`

## Migration System

### Directory structure

```
amelia/server/database/
  migrations/
    001_initial_schema.sql
    002_....sql
  connection.py      # asyncpg pool management
  repository.py      # queries with $1 syntax
  migrator.py        # runs migrations on startup
```

### Schema version tracking

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT NOW()
);
```

### Migration runner

On startup:
1. Ensure `schema_migrations` table exists
2. Get current version from table
3. Run any SQL files with version > current
4. Record applied versions

## Files to Change

| File | Change |
|------|--------|
| `pyproject.toml` | Add asyncpg, remove aiosqlite |
| `amelia/server/config.py` | Replace `database_path` with `database_url`, add pool settings |
| `amelia/server/database/connection.py` | Rewrite for asyncpg pool |
| `amelia/server/database/migrations/` | New directory with SQL files |
| `amelia/server/database/migrator.py` | New file, migration runner |
| `amelia/server/database/repository.py` | Update `?` → `$1` parameter syntax |
| `amelia/server/database/brainstorm_repository.py` | Update `?` → `$1` parameter syntax |
| `amelia/server/database/prompt_repository.py` | Update `?` → `$1` parameter syntax |
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
    await db.execute("TRUNCATE workflows, events, ... CASCADE")
    await db.close()
```

### CI

GitHub Actions PostgreSQL service container, same configuration as local Docker.

## Future: pg_vector Integration

When ready (after Knowledge Library/Oracle data model is defined):

1. Add migration: `CREATE EXTENSION IF NOT EXISTS vector;`
2. Create embeddings table with `vector(N)` column
3. Register vector type in connection pool setup

This is a separate migration, not part of initial PostgreSQL work.

## Related Issues

- #280 - Oracle Consulting System
- #290 - RLM Integration (Knowledge Library, RAG)
