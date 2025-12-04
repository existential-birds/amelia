# Database Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement SQLite database with migrations, connection management, and initial schema.

> **Note:** The migration system described in this plan was later simplified. Migrations were removed in favor of inline schema creation via `Database.ensure_schema()`. The database now uses `CREATE TABLE IF NOT EXISTS` for idempotent schema setup.

**Architecture:** SQLite with WAL mode for concurrent read/write, simple sequential migrations (no Alembic), aiosqlite for async operations. Database stores workflows, events, and token usage.

**Tech Stack:** aiosqlite, SQLite, pathlib

**Depends on:** Plan 1 (Server Foundation)

---

## Task 1: Create Database Connection Module

**Files:**
- Create: `amelia/server/database/__init__.py`
- Create: `amelia/server/database/connection.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/database/test_connection.py
"""Tests for database connection management."""
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock


class TestDatabaseConnection:
    """Tests for Database class."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Temporary database path for testing."""
        return tmp_path / "test.db"

    @pytest.mark.asyncio
    async def test_database_creates_directory(self, temp_db_path):
        """Database creates parent directory if it doesn't exist."""
        from amelia.server.database.connection import Database

        nested_path = temp_db_path.parent / "nested" / "dir" / "test.db"
        db = Database(nested_path)

        await db.connect()
        await db.close()

        assert nested_path.parent.exists()

    @pytest.mark.asyncio
    async def test_database_connect_creates_file(self, temp_db_path):
        """Database file is created on connect."""
        from amelia.server.database.connection import Database

        db = Database(temp_db_path)
        await db.connect()
        await db.close()

        assert temp_db_path.exists()

    @pytest.mark.asyncio
    async def test_database_wal_mode_enabled(self, temp_db_path):
        """WAL mode is enabled for concurrent access."""
        from amelia.server.database.connection import Database

        db = Database(temp_db_path)
        await db.connect()

        result = await db.fetch_one("PRAGMA journal_mode")
        await db.close()

        assert result[0].lower() == "wal"

    @pytest.mark.asyncio
    async def test_database_foreign_keys_enabled(self, temp_db_path):
        """Foreign keys are enforced."""
        from amelia.server.database.connection import Database

        db = Database(temp_db_path)
        await db.connect()

        result = await db.fetch_one("PRAGMA foreign_keys")
        await db.close()

        assert result[0] == 1

    @pytest.mark.asyncio
    async def test_database_execute(self, temp_db_path):
        """Execute runs SQL statements."""
        from amelia.server.database.connection import Database

        db = Database(temp_db_path)
        await db.connect()

        await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        await db.execute("INSERT INTO test (name) VALUES (?)", ("hello",))

        result = await db.fetch_one("SELECT name FROM test WHERE id = 1")
        await db.close()

        assert result[0] == "hello"

    @pytest.mark.asyncio
    async def test_database_fetch_all(self, temp_db_path):
        """Fetch_all returns all matching rows."""
        from amelia.server.database.connection import Database

        db = Database(temp_db_path)
        await db.connect()

        await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        await db.execute("INSERT INTO test (name) VALUES (?)", ("a",))
        await db.execute("INSERT INTO test (name) VALUES (?)", ("b",))
        await db.execute("INSERT INTO test (name) VALUES (?)", ("c",))

        results = await db.fetch_all("SELECT name FROM test ORDER BY name")
        await db.close()

        assert len(results) == 3
        assert [r[0] for r in results] == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_database_context_manager(self, temp_db_path):
        """Database can be used as async context manager."""
        from amelia.server.database.connection import Database

        async with Database(temp_db_path) as db:
            await db.execute("CREATE TABLE test (id INTEGER)")

        # Connection should be closed
        assert temp_db_path.exists()

    @pytest.mark.asyncio
    async def test_database_transaction(self, temp_db_path):
        """Transactions can be used for atomic operations."""
        from amelia.server.database.connection import Database

        db = Database(temp_db_path)
        await db.connect()
        await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val INTEGER)")

        async with db.transaction():
            await db.execute("INSERT INTO test (val) VALUES (1)")
            await db.execute("INSERT INTO test (val) VALUES (2)")

        results = await db.fetch_all("SELECT val FROM test")
        await db.close()

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_database_transaction_rollback(self, temp_db_path):
        """Transaction rolls back on exception."""
        from amelia.server.database.connection import Database

        db = Database(temp_db_path)
        await db.connect()
        await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val INTEGER UNIQUE)")
        await db.execute("INSERT INTO test (val) VALUES (1)")

        with pytest.raises(Exception):
            async with db.transaction():
                await db.execute("INSERT INTO test (val) VALUES (2)")
                await db.execute("INSERT INTO test (val) VALUES (1)")  # Duplicate - fails

        # Only original row should exist
        results = await db.fetch_all("SELECT val FROM test")
        await db.close()

        assert len(results) == 1
        assert results[0][0] == 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_connection.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create database and test packages**

```bash
# Create source package
mkdir -p amelia/server/database

# Create test package
mkdir -p tests/unit/server/database
touch tests/unit/server/database/__init__.py
```

```python
# amelia/server/database/__init__.py
"""Database package for Amelia server."""
from amelia.server.database.connection import Database

__all__ = ["Database"]
```

**Step 4: Implement Database class**

```python
# amelia/server/database/connection.py
"""Database connection management with SQLite."""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Sequence

import aiosqlite


class Database:
    """Async SQLite database connection manager.

    Configures SQLite with:
    - WAL mode for concurrent read/write
    - Foreign keys enforced
    - 5 second busy timeout
    - 64MB journal size limit
    """

    def __init__(self, db_path: Path):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file.
        """
        self._db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open database connection with optimized settings."""
        # Ensure parent directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection = await aiosqlite.connect(
            self._db_path,
            isolation_level=None,  # Autocommit mode (we manage transactions)
        )

        # Enable row factory for dict-like access
        self._connection.row_factory = aiosqlite.Row

        # Configure SQLite for optimal performance
        await self._connection.execute("PRAGMA journal_mode = WAL")
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._connection.execute("PRAGMA busy_timeout = 5000")
        await self._connection.execute("PRAGMA journal_size_limit = 67108864")

    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def __aenter__(self) -> "Database":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    @property
    def connection(self) -> aiosqlite.Connection:
        """Get the active connection.

        Raises:
            RuntimeError: If not connected.
        """
        if self._connection is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._connection

    async def execute(
        self,
        sql: str,
        parameters: Sequence[Any] = (),
    ) -> int:
        """Execute SQL statement.

        Args:
            sql: SQL statement to execute.
            parameters: Optional parameters for the statement.

        Returns:
            Number of rows affected (for INSERT/UPDATE/DELETE).

        Note:
            With isolation_level=None (autocommit mode), statements are
            automatically committed. Do not add explicit commit() here
            as it would break explicit transactions started with transaction().
        """
        cursor = await self.connection.execute(sql, parameters)
        return cursor.rowcount

    async def execute_many(
        self,
        sql: str,
        parameters: Sequence[Sequence[Any]],
    ) -> int:
        """Execute SQL statement with multiple parameter sets.

        Args:
            sql: SQL statement to execute.
            parameters: Sequence of parameter sequences.

        Returns:
            Total rows affected.

        Note:
            With isolation_level=None (autocommit mode), statements are
            automatically committed. Do not add explicit commit() here
            as it would break explicit transactions started with transaction().
        """
        cursor = await self.connection.executemany(sql, parameters)
        return cursor.rowcount

    async def fetch_one(
        self,
        sql: str,
        parameters: Sequence[Any] = (),
    ) -> aiosqlite.Row | None:
        """Fetch a single row.

        Args:
            sql: SQL query.
            parameters: Optional parameters.

        Returns:
            Single row or None if not found.
        """
        cursor = await self.connection.execute(sql, parameters)
        return await cursor.fetchone()

    async def fetch_all(
        self,
        sql: str,
        parameters: Sequence[Any] = (),
    ) -> list[aiosqlite.Row]:
        """Fetch all matching rows.

        Args:
            sql: SQL query.
            parameters: Optional parameters.

        Returns:
            List of matching rows.
        """
        cursor = await self.connection.execute(sql, parameters)
        return await cursor.fetchall()

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None, None]:
        """Context manager for database transactions.

        Commits on success, rolls back on exception.
        """
        await self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            await self.connection.execute("COMMIT")
        except Exception:
            await self.connection.execute("ROLLBACK")
            raise
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_connection.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/database/__init__.py amelia/server/database/connection.py \
        tests/unit/server/database/__init__.py tests/unit/server/database/test_connection.py
git commit -m "feat(database): add SQLite connection manager with WAL mode"
```

---

## Task 2: Create Migration Runner

**Files:**
- Create: `amelia/server/database/migrate.py`
- Create: `amelia/server/database/migrations/` directory

**Step 1: Write the failing test**

```python
# tests/unit/server/database/test_migrate.py
"""Tests for database migrations."""
import pytest
from pathlib import Path


class TestMigrationRunner:
    """Tests for MigrationRunner."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Temporary database path."""
        return tmp_path / "test.db"

    @pytest.fixture
    def migrations_dir(self, tmp_path):
        """Temporary migrations directory."""
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        return migrations

    @pytest.mark.asyncio
    async def test_creates_version_table(self, temp_db_path, migrations_dir):
        """Migration runner creates schema_version table."""
        from amelia.server.database.migrate import MigrationRunner
        from amelia.server.database.connection import Database

        runner = MigrationRunner(temp_db_path, migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            result = await db.fetch_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_applies_migrations_in_order(self, temp_db_path, migrations_dir):
        """Migrations are applied in version order."""
        from amelia.server.database.migrate import MigrationRunner
        from amelia.server.database.connection import Database

        # Create test migrations
        (migrations_dir / "001_first.sql").write_text(
            "CREATE TABLE first (id INTEGER);"
        )
        (migrations_dir / "002_second.sql").write_text(
            "CREATE TABLE second (id INTEGER);"
        )
        (migrations_dir / "003_third.sql").write_text(
            "CREATE TABLE third (id INTEGER);"
        )

        runner = MigrationRunner(temp_db_path, migrations_dir)
        applied = await runner.run_migrations()

        assert applied == 3

        async with Database(temp_db_path) as db:
            # All tables should exist
            for table in ["first", "second", "third"]:
                result = await db.fetch_one(
                    f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
                )
                assert result is not None

    @pytest.mark.asyncio
    async def test_skips_already_applied_migrations(self, temp_db_path, migrations_dir):
        """Migrations are only applied once."""
        from amelia.server.database.migrate import MigrationRunner

        (migrations_dir / "001_first.sql").write_text(
            "CREATE TABLE first (id INTEGER);"
        )

        runner = MigrationRunner(temp_db_path, migrations_dir)

        # First run
        applied1 = await runner.run_migrations()
        assert applied1 == 1

        # Second run - should skip
        applied2 = await runner.run_migrations()
        assert applied2 == 0

    @pytest.mark.asyncio
    async def test_applies_new_migrations_only(self, temp_db_path, migrations_dir):
        """Only new migrations are applied on subsequent runs."""
        from amelia.server.database.migrate import MigrationRunner

        (migrations_dir / "001_first.sql").write_text(
            "CREATE TABLE first (id INTEGER);"
        )

        runner = MigrationRunner(temp_db_path, migrations_dir)
        await runner.run_migrations()

        # Add new migration
        (migrations_dir / "002_second.sql").write_text(
            "CREATE TABLE second (id INTEGER);"
        )

        # Run again
        applied = await runner.run_migrations()
        assert applied == 1

    @pytest.mark.asyncio
    async def test_records_applied_versions(self, temp_db_path, migrations_dir):
        """Applied migrations are recorded in schema_version."""
        from amelia.server.database.migrate import MigrationRunner
        from amelia.server.database.connection import Database

        (migrations_dir / "001_first.sql").write_text("SELECT 1;")
        (migrations_dir / "002_second.sql").write_text("SELECT 1;")

        runner = MigrationRunner(temp_db_path, migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            result = await db.fetch_all(
                "SELECT version FROM schema_version ORDER BY version"
            )
            versions = [r[0] for r in result]
            assert versions == [1, 2]

    @pytest.mark.asyncio
    async def test_get_current_version(self, temp_db_path, migrations_dir):
        """get_current_version returns highest applied version."""
        from amelia.server.database.migrate import MigrationRunner

        (migrations_dir / "001_first.sql").write_text("SELECT 1;")
        (migrations_dir / "002_second.sql").write_text("SELECT 1;")

        runner = MigrationRunner(temp_db_path, migrations_dir)
        await runner.run_migrations()

        current = await runner.get_current_version()
        assert current == 2

    @pytest.mark.asyncio
    async def test_migration_with_multiple_statements(self, temp_db_path, migrations_dir):
        """Migrations can contain multiple SQL statements."""
        from amelia.server.database.migrate import MigrationRunner
        from amelia.server.database.connection import Database

        (migrations_dir / "001_multi.sql").write_text("""
            CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);
            CREATE INDEX idx_users_name ON users(name);
            INSERT INTO users (name) VALUES ('test');
        """)

        runner = MigrationRunner(temp_db_path, migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            result = await db.fetch_one("SELECT name FROM users WHERE id = 1")
            assert result[0] == "test"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_migrate.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement MigrationRunner**

```python
# amelia/server/database/migrate.py
"""Sequential database migration runner."""
from pathlib import Path

import aiosqlite
from loguru import logger


class MigrationRunner:
    """Sequential SQL migration runner for SQLite.

    Migrations are SQL files named with a numeric prefix:
    - 001_initial_schema.sql
    - 002_add_indexes.sql
    - etc.

    The version number is extracted from the filename prefix.
    """

    VERSION_TABLE = "schema_version"

    def __init__(self, db_path: Path, migrations_dir: Path):
        """Initialize migration runner.

        Args:
            db_path: Path to SQLite database file.
            migrations_dir: Directory containing migration SQL files.
        """
        self._db_path = db_path
        self._migrations_dir = migrations_dir

    async def run_migrations(self) -> int:
        """Run all pending migrations.

        Returns:
            Number of migrations applied.
        """
        # Ensure parent directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self._db_path) as conn:
            await self._ensure_version_table(conn)
            current = await self._get_current_version_internal(conn)
            migrations = self._get_pending_migrations(current)

            applied = 0
            for version, sql_file in migrations:
                logger.info(f"Applying migration {version}: {sql_file.name}")
                sql = sql_file.read_text()
                await self._execute_migration(conn, version, sql)
                applied += 1

            return applied

    async def get_current_version(self) -> int:
        """Get current schema version.

        Returns:
            Current version number (0 if no migrations applied).
        """
        if not self._db_path.exists():
            return 0

        async with aiosqlite.connect(self._db_path) as conn:
            try:
                return await self._get_current_version_internal(conn)
            except aiosqlite.OperationalError:
                return 0

    async def _ensure_version_table(self, conn: aiosqlite.Connection) -> None:
        """Create schema_version table if it doesn't exist."""
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.VERSION_TABLE} (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.commit()

    async def _get_current_version_internal(
        self,
        conn: aiosqlite.Connection,
    ) -> int:
        """Get current version from database.

        Args:
            conn: Active database connection.

        Returns:
            Current version (0 if none).
        """
        cursor = await conn.execute(
            f"SELECT MAX(version) FROM {self.VERSION_TABLE}"
        )
        result = await cursor.fetchone()
        return result[0] if result and result[0] else 0

    def _get_pending_migrations(
        self,
        current_version: int,
    ) -> list[tuple[int, Path]]:
        """Get migrations with version > current, sorted by version.

        Args:
            current_version: Current schema version.

        Returns:
            List of (version, path) tuples for pending migrations.
        """
        if not self._migrations_dir.exists():
            return []

        migrations = []
        for sql_file in self._migrations_dir.glob("*.sql"):
            # Extract version from filename: 001_initial_schema.sql -> 1
            try:
                version = int(sql_file.stem.split("_")[0])
            except (ValueError, IndexError):
                logger.warning(f"Skipping invalid migration filename: {sql_file.name}")
                continue

            if version > current_version:
                migrations.append((version, sql_file))

        return sorted(migrations, key=lambda x: x[0])

    async def _execute_migration(
        self,
        conn: aiosqlite.Connection,
        version: int,
        sql: str,
    ) -> None:
        """Execute migration in transaction and record version.

        Args:
            conn: Database connection.
            version: Migration version number.
            sql: SQL to execute.
        """
        # Execute migration in transaction
        await conn.execute("BEGIN IMMEDIATE")
        try:
            await conn.executescript(sql)
            await conn.execute(
                f"INSERT INTO {self.VERSION_TABLE} (version) VALUES (?)",
                (version,),
            )
            await conn.commit()
        except Exception:
            await conn.execute("ROLLBACK")
            raise
```

**Step 4: Create migrations directory**

```bash
mkdir -p amelia/server/database/migrations
touch amelia/server/database/migrations/.gitkeep
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_migrate.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/database/migrate.py amelia/server/database/migrations/.gitkeep tests/unit/server/database/test_migrate.py
git commit -m "feat(database): add sequential migration runner"
```

---

## Task 3: Create Initial Schema Migration

**Files:**
- Create: `amelia/server/database/migrations/001_initial_schema.sql`

**Step 1: Write the failing test**

```python
# tests/unit/server/database/test_schema.py
"""Tests for initial database schema."""
import pytest
from pathlib import Path


class TestInitialSchema:
    """Tests for 001_initial_schema.sql migration."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Temporary database path."""
        return tmp_path / "test.db"

    @pytest.fixture
    def production_migrations_dir(self):
        """Path to actual migrations directory."""
        import amelia.server.database
        return Path(amelia.server.database.__file__).parent / "migrations"

    @pytest.mark.asyncio
    async def test_workflows_table_exists(self, temp_db_path, production_migrations_dir):
        """Initial schema creates workflows table."""
        from amelia.server.database.migrate import MigrationRunner
        from amelia.server.database.connection import Database

        runner = MigrationRunner(temp_db_path, production_migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            result = await db.fetch_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='workflows'"
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_events_table_exists(self, temp_db_path, production_migrations_dir):
        """Initial schema creates events table."""
        from amelia.server.database.migrate import MigrationRunner
        from amelia.server.database.connection import Database

        runner = MigrationRunner(temp_db_path, production_migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            result = await db.fetch_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_token_usage_table_exists(self, temp_db_path, production_migrations_dir):
        """Initial schema creates token_usage table."""
        from amelia.server.database.migrate import MigrationRunner
        from amelia.server.database.connection import Database

        runner = MigrationRunner(temp_db_path, production_migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            result = await db.fetch_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='token_usage'"
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_health_check_table_exists(self, temp_db_path, production_migrations_dir):
        """Initial schema creates health_check table."""
        from amelia.server.database.migrate import MigrationRunner
        from amelia.server.database.connection import Database

        runner = MigrationRunner(temp_db_path, production_migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            result = await db.fetch_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='health_check'"
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_workflows_has_required_columns(self, temp_db_path, production_migrations_dir):
        """Workflows table has all required columns."""
        from amelia.server.database.migrate import MigrationRunner
        from amelia.server.database.connection import Database

        runner = MigrationRunner(temp_db_path, production_migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            # Get column info
            result = await db.fetch_all("PRAGMA table_info(workflows)")
            columns = {row[1] for row in result}

            required = {
                "id", "issue_id", "worktree_path", "worktree_name",
                "status", "started_at", "completed_at", "failure_reason", "state_json"
            }
            assert required.issubset(columns)

    @pytest.mark.asyncio
    async def test_events_has_required_columns(self, temp_db_path, production_migrations_dir):
        """Events table has all required columns."""
        from amelia.server.database.migrate import MigrationRunner
        from amelia.server.database.connection import Database

        runner = MigrationRunner(temp_db_path, production_migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            result = await db.fetch_all("PRAGMA table_info(events)")
            columns = {row[1] for row in result}

            required = {
                "id", "workflow_id", "sequence", "timestamp",
                "agent", "event_type", "message", "data_json", "correlation_id"
            }
            assert required.issubset(columns)

    @pytest.mark.asyncio
    async def test_unique_active_worktree_constraint(self, temp_db_path, production_migrations_dir):
        """Only one active workflow per worktree is allowed."""
        from amelia.server.database.migrate import MigrationRunner
        from amelia.server.database.connection import Database
        import aiosqlite

        runner = MigrationRunner(temp_db_path, production_migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            # Insert first workflow
            await db.execute("""
                INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, status, state_json)
                VALUES ('id1', 'ISSUE-1', '/path/to/worktree', 'main', 'in_progress', '{}')
            """)

            # Second workflow in same worktree should fail
            with pytest.raises(aiosqlite.IntegrityError):
                await db.execute("""
                    INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, status, state_json)
                    VALUES ('id2', 'ISSUE-2', '/path/to/worktree', 'main', 'pending', '{}')
                """)

    @pytest.mark.asyncio
    async def test_completed_workflows_dont_conflict(self, temp_db_path, production_migrations_dir):
        """Completed workflows don't block new workflows in same worktree."""
        from amelia.server.database.migrate import MigrationRunner
        from amelia.server.database.connection import Database

        runner = MigrationRunner(temp_db_path, production_migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            # Insert completed workflow
            await db.execute("""
                INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, status, state_json)
                VALUES ('id1', 'ISSUE-1', '/path/to/worktree', 'main', 'completed', '{}')
            """)

            # New workflow in same worktree should succeed
            await db.execute("""
                INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, status, state_json)
                VALUES ('id2', 'ISSUE-2', '/path/to/worktree', 'main', 'in_progress', '{}')
            """)

            # Verify both exist
            result = await db.fetch_all("SELECT id FROM workflows")
            assert len(result) == 2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_schema.py -v`
Expected: FAIL (migration file doesn't exist)

**Step 3: Create initial schema migration**

```sql
-- amelia/server/database/migrations/001_initial_schema.sql
-- Initial database schema for Amelia server

-- Workflows table with indexed columns for common queries
CREATE TABLE workflows (
    id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    worktree_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    failure_reason TEXT,
    state_json TEXT NOT NULL
);

-- Indexes for efficient querying
CREATE INDEX idx_workflows_issue_id ON workflows(issue_id);
CREATE INDEX idx_workflows_status ON workflows(status);
CREATE INDEX idx_workflows_worktree ON workflows(worktree_path);
CREATE INDEX idx_workflows_started_at ON workflows(started_at DESC);

-- Unique constraint: one active workflow per worktree
-- Active statuses: pending, in_progress, blocked
CREATE UNIQUE INDEX idx_workflows_active_worktree
    ON workflows(worktree_path)
    WHERE status IN ('pending', 'in_progress', 'blocked');

-- Events table with monotonic sequence for ordering
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    agent TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    data_json TEXT,
    correlation_id TEXT
);

-- Unique constraint ensures no duplicate sequences per workflow
CREATE UNIQUE INDEX idx_events_workflow_sequence ON events(workflow_id, sequence);
CREATE INDEX idx_events_workflow ON events(workflow_id, timestamp);
CREATE INDEX idx_events_type ON events(event_type);

-- Token usage table
CREATE TABLE token_usage (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    agent TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT 'claude-sonnet-4-20250514',
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cost_usd REAL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tokens_workflow ON token_usage(workflow_id);
CREATE INDEX idx_tokens_agent ON token_usage(agent);

-- Health check table (for write capability verification)
CREATE TABLE health_check (
    id TEXT PRIMARY KEY,
    checked_at TIMESTAMP NOT NULL
);
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_schema.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/database/migrations/001_initial_schema.sql tests/unit/server/database/test_schema.py
git commit -m "feat(database): add initial schema migration with workflows, events, tokens"
```

---

## Task 4: Integrate Database with Server Startup

**Files:**
- Modify: `amelia/server/main.py`
- Modify: `amelia/server/__init__.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/test_app_database.py
"""Tests for database integration with FastAPI app."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock


class TestAppDatabaseIntegration:
    """Tests for database integration."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Temporary database path."""
        return tmp_path / "test.db"

    def test_health_check_verifies_database(self, temp_db_path):
        """Health endpoint verifies database connectivity."""
        import os
        with patch.dict(os.environ, {"AMELIA_DATABASE_PATH": str(temp_db_path)}):
            from amelia.server.main import create_app

            app = create_app()
            client = TestClient(app)

            # Trigger startup event and make request within context
            with client:
                response = client.get("/api/health")
                data = response.json()
                assert "database" in data
                assert data["database"]["status"] in ("healthy", "degraded")

    def test_database_health_check_writes_and_reads(self, temp_db_path):
        """Database health check performs write/read cycle."""
        import os
        with patch.dict(os.environ, {"AMELIA_DATABASE_PATH": str(temp_db_path)}):
            from amelia.server.main import create_app

            app = create_app()
            client = TestClient(app)

            with client:
                response = client.get("/api/health")
                data = response.json()
                # Should be healthy after successful write/read
                assert data["database"]["status"] == "healthy"

    def test_database_health_reports_error_on_failure(self, temp_db_path):
        """Database health check reports error message when degraded."""
        import os
        with patch.dict(os.environ, {"AMELIA_DATABASE_PATH": str(temp_db_path)}):
            from amelia.server.main import create_app

            app = create_app()
            client = TestClient(app)

            with client:
                # Mock database to simulate failure after startup
                with patch('amelia.server.routes.health.get_database') as mock_get_db:
                    mock_db = AsyncMock()
                    mock_db.execute.side_effect = Exception("Connection lost")
                    mock_get_db.return_value = mock_db

                    response = client.get("/api/health")
                    data = response.json()

                    assert data["database"]["status"] == "degraded"
                    assert data["database"]["error"] is not None
                    assert "Connection lost" in data["database"]["error"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_app_database.py -v`
Expected: FAIL (database not integrated)

**Step 3: Update server main.py with database lifecycle**

Modify the existing `amelia/server/main.py` to add database support. The key changes are:
1. Add imports for Database and MigrationRunner
2. Add `_database` global and `get_database()` function (alongside existing `_config`/`get_config()`)
3. Update `lifespan()` to run migrations and connect to database

```python
# amelia/server/main.py
"""FastAPI application setup and configuration."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from loguru import logger

from amelia import __version__
from amelia.server.config import ServerConfig
from amelia.server.database.connection import Database
from amelia.server.database.migrate import MigrationRunner
from amelia.server.routes import health_router


# Module-level config storage for DI
_config: ServerConfig | None = None
# Global database instance
_database: Database | None = None


def get_config() -> ServerConfig:
    """FastAPI dependency that provides the server configuration.

    Returns:
        The current ServerConfig instance.

    Raises:
        RuntimeError: If config is not initialized (server not started).
    """
    if _config is None:
        raise RuntimeError("Server config not initialized. Is the server running?")
    return _config


def get_database() -> Database:
    """Get the database instance.

    Returns:
        The current Database instance.

    Raises:
        RuntimeError: If database not initialized.
    """
    if _database is None:
        raise RuntimeError("Database not initialized. Is the server running?")
    return _database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifespan events.

    Sets start_time on startup for uptime calculation.
    Initializes configuration, runs migrations, and connects to database.
    """
    global _config, _database

    # Initialize configuration
    _config = ServerConfig()

    # Ensure database directory exists
    db_dir = _config.database_path.parent
    db_dir.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Ensured database directory exists: {db_dir}")

    # Run migrations
    migrations_dir = Path(__file__).parent / "database" / "migrations"
    runner = MigrationRunner(_config.database_path, migrations_dir)
    applied = await runner.run_migrations()
    if applied:
        logger.info(f"Applied {applied} database migrations")

    # Connect to database
    _database = Database(_config.database_path)
    await _database.connect()
    logger.info(f"Database connected: {_config.database_path}")

    # Log effective configuration
    logger.info(
        f"Server starting: host={_config.host}, port={_config.port}, "
        f"database={_config.database_path}"
    )

    app.state.start_time = datetime.now(UTC)
    yield

    # Cleanup
    if _database:
        await _database.close()
        _database = None
    _config = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    application = FastAPI(
        title="Amelia API",
        description="Agentic coding orchestrator REST API",
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Mount health routes
    application.include_router(health_router, prefix="/api")

    return application


# Create app instance
app = create_app()
```

**Step 4: Update health endpoint with real database check**

Modify the existing `amelia/server/routes/health.py` to add real database health checks. The key changes are:
1. Add `check_database_health()` async function
2. Update `health()` endpoint to use real database check instead of hardcoded status
3. Preserve existing Pydantic models and `request.app.state.start_time` pattern

```python
# amelia/server/routes/health.py
"""Health check endpoints for liveness and readiness probes."""
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

import psutil
from fastapi import APIRouter, Request
from loguru import logger
from pydantic import BaseModel, Field

from amelia import __version__


router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    """Response model for liveness probe."""

    status: Literal["alive"] = "alive"


class ReadinessResponse(BaseModel):
    """Response model for readiness probe."""

    status: Literal["ready", "not_ready"]


class DatabaseStatus(BaseModel):
    """Database health status."""

    status: Literal["healthy", "degraded", "unhealthy"]
    mode: str = Field(description="Database mode (e.g., 'wal')")
    error: str | None = Field(default=None, description="Error message if degraded")


class HealthResponse(BaseModel):
    """Response model for detailed health check."""

    status: Literal["healthy", "degraded"]
    version: str
    uptime_seconds: float
    active_workflows: int
    websocket_connections: int
    memory_mb: float
    cpu_percent: float
    database: DatabaseStatus


async def check_database_health() -> DatabaseStatus:
    """Verify database read and write capability.

    Performs a lightweight write/read cycle to ensure the database
    is fully operational, not just connected.

    Returns:
        DatabaseStatus with health check results.
    """
    try:
        from amelia.server.main import get_database

        db = get_database()

        # Test write capability
        test_id = str(uuid4())
        await db.execute(
            "INSERT INTO health_check (id, checked_at) VALUES (?, ?)",
            (test_id, datetime.now(UTC)),
        )
        # Cleanup test row
        await db.execute("DELETE FROM health_check WHERE id = ?", (test_id,))
        # Test read capability
        await db.fetch_one("SELECT 1")

        return DatabaseStatus(status="healthy", mode="wal")
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        return DatabaseStatus(status="degraded", mode="wal", error=str(e))


@router.get("/live", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    """Minimal liveness check - is the server responding?

    Returns:
        Simple alive status.
    """
    return LivenessResponse()


@router.get("/ready", response_model=ReadinessResponse)
async def readiness() -> ReadinessResponse:
    """Readiness check - is the server ready to accept requests?

    Returns:
        Ready status or 503 if shutting down.
    """
    # TODO: Check lifecycle.is_shutting_down when implemented
    return ReadinessResponse(status="ready")


@router.get("", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Detailed health check with server metrics.

    Returns:
        Comprehensive health status including:
        - Server status (healthy/degraded)
        - Version info
        - Uptime
        - Active workflow count
        - WebSocket connection count
        - Memory usage
        - Database status
    """
    process = psutil.Process()
    start_time: datetime = request.app.state.start_time
    uptime = (datetime.now(UTC) - start_time).total_seconds()

    # TODO: Get actual counts when services are implemented
    active_workflows = 0
    websocket_connections = 0

    # Real database health check
    db_status = await check_database_health()

    overall_status: Literal["healthy", "degraded"] = (
        "healthy" if db_status.status == "healthy" else "degraded"
    )

    return HealthResponse(
        status=overall_status,
        version=__version__,
        uptime_seconds=uptime,
        active_workflows=active_workflows,
        websocket_connections=websocket_connections,
        memory_mb=round(process.memory_info().rss / 1024 / 1024, 2),
        cpu_percent=process.cpu_percent(),
        database=db_status,
    )
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_app_database.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/main.py amelia/server/routes/health.py tests/unit/server/test_app_database.py
git commit -m "feat(server): integrate database with app lifecycle and health checks"
```

---

## Task 5: Update Database Package Exports

**Files:**
- Modify: `amelia/server/database/__init__.py`
- Modify: `amelia/server/__init__.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/database/test_exports.py
"""Tests for database package exports."""


def test_database_exportable_from_package():
    """Database class is exported from database package."""
    from amelia.server.database import Database
    assert Database is not None


def test_migration_runner_exportable():
    """MigrationRunner is exported from database package."""
    from amelia.server.database import MigrationRunner
    assert MigrationRunner is not None


def test_database_available_from_server_package():
    """Database is accessible from server package."""
    from amelia.server import Database
    assert Database is not None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_exports.py -v`
Expected: FAIL (exports not configured)

**Step 3: Update database package init**

```python
# amelia/server/database/__init__.py
"""Database package for Amelia server."""
from amelia.server.database.connection import Database
from amelia.server.database.migrate import MigrationRunner

__all__ = ["Database", "MigrationRunner"]
```

**Step 4: Update server package init**

```python
# amelia/server/__init__.py
"""Amelia FastAPI server package."""
from amelia.server.config import ServerConfig
from amelia.server.database import Database, MigrationRunner

__all__ = [
    "ServerConfig",
    "Database",
    "MigrationRunner",
]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_exports.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/database/__init__.py amelia/server/__init__.py tests/unit/server/database/test_exports.py
git commit -m "feat(database): update package exports for Database and MigrationRunner"
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] `tests/unit/server/database/__init__.py` exists
- [ ] `uv run pytest tests/unit/server/database/ -v` - All database tests pass
- [ ] `uv run pytest tests/unit/server/test_app_database.py -v` - Integration tests pass
- [ ] `uv run ruff check amelia/server/database` - No linting errors
- [ ] `uv run mypy amelia/server/database` - No type errors
- [ ] `uv run amelia server` starts and creates database at `~/.amelia/amelia.db`
- [ ] Database has tables: `workflows`, `events`, `token_usage`, `health_check`, `schema_version`
- [ ] Health endpoint reports database status (including `error` field when degraded)

```bash
# Manual verification
curl http://127.0.0.1:8420/api/health | jq .database
# Expected: {"status": "healthy", "mode": "wal", "error": null}
```

---

## Summary

This plan creates the database foundation:

| Component | File | Purpose |
|-----------|------|---------|
| Connection | `amelia/server/database/connection.py` | Async SQLite with WAL mode |
| Migrations | `amelia/server/database/migrate.py` | Sequential migration runner |
| Schema | `migrations/001_initial_schema.sql` | Workflows, events, tokens tables |
| Integration | `amelia/server/main.py` | Lifecycle hooks for DB |

**Schema tables:**
- `workflows` - Workflow state with unique active worktree constraint
- `events` - Activity log with sequence ordering
- `token_usage` - Token consumption tracking
- `health_check` - Write capability verification
- `schema_version` - Migration tracking

**Next PR:** Workflow Repository & State Machine (Plan 3)
