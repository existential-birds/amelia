"""Database connection management with SQLite."""
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

from amelia.agents.prompts.defaults import PROMPT_DEFAULTS


# Type alias for SQLite-compatible values
SqliteValue = None | int | float | str | bytes | datetime


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
        """Open database connection with optimized settings.

        Raises:
            RuntimeError: If PRAGMA verification fails.
        """
        # Ensure parent directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection = await aiosqlite.connect(
            self._db_path,
            isolation_level=None,  # Autocommit mode (we manage transactions)
        )

        # Enable row factory for dict-like access
        self._connection.row_factory = aiosqlite.Row

        # Configure SQLite for optimal performance
        # Verify WAL mode was applied
        cursor = await self._connection.execute("PRAGMA journal_mode = WAL")
        result = await cursor.fetchone()
        if result is None or result[0].lower() != "wal":
            raise RuntimeError(
                f"Failed to set WAL journal mode. Got: {result[0] if result else None}"
            )

        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._connection.execute("PRAGMA busy_timeout = 5000")
        await self._connection.execute("PRAGMA journal_size_limit = 67108864")

    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            try:
                await self._connection.close()
            except Exception as e:
                logger.warning(f"Error closing database connection: {e}")
            finally:
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

    async def is_healthy(self) -> bool:
        """Check if connection is valid and database is accessible.

        Returns:
            True if the connection is healthy, False otherwise.
        """
        if self._connection is None:
            return False
        try:
            cursor = await self._connection.execute("SELECT 1")
            result = await cursor.fetchone()
            return result is not None and result[0] == 1
        except Exception:
            return False

    async def execute(
        self,
        sql: str,
        parameters: Sequence[SqliteValue] = (),
    ) -> int:
        """Execute SQL statement.

        Args:
            sql: SQL statement to execute.
            parameters: Optional parameters for the statement.

        Returns:
            Number of rows affected (for INSERT/UPDATE/DELETE).
            Note: May return -1 for SELECT statements.

        Note:
            With isolation_level=None (autocommit mode), statements are
            automatically committed. Do not add explicit commit() here
            as it would break explicit transactions started with transaction().
        """
        cursor = await self.connection.execute(sql, parameters)
        return cursor.rowcount

    async def execute_insert(
        self,
        sql: str,
        parameters: Sequence[SqliteValue] = (),
    ) -> int:
        """Execute INSERT statement and return the last inserted row ID.

        Args:
            sql: INSERT SQL statement to execute.
            parameters: Optional parameters for the statement.

        Returns:
            The rowid of the last inserted row.

        Note:
            With isolation_level=None (autocommit mode), statements are
            automatically committed. Do not add explicit commit() here
            as it would break explicit transactions started with transaction().
        """
        cursor = await self.connection.execute(sql, parameters)
        return cursor.lastrowid if cursor.lastrowid is not None else 0

    async def execute_many(
        self,
        sql: str,
        parameters: Sequence[Sequence[SqliteValue]],
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
        parameters: Sequence[SqliteValue] = (),
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
        parameters: Sequence[SqliteValue] = (),
    ) -> list[aiosqlite.Row]:
        """Fetch all matching rows.

        Args:
            sql: SQL query.
            parameters: Optional parameters.

        Returns:
            List of matching rows.
        """
        cursor = await self.connection.execute(sql, parameters)
        result = await cursor.fetchall()
        return list(result)

    async def fetch_scalar(
        self,
        sql: str,
        parameters: Sequence[SqliteValue] = (),
    ) -> SqliteValue:
        """Fetch a single scalar value.

        Args:
            sql: SQL query expected to return one row with one column.
            parameters: Optional parameters.

        Returns:
            The scalar value, or None if no rows found.
        """
        row = await self.fetch_one(sql, parameters)
        return row[0] if row else None

    @asynccontextmanager
    async def transaction(self, read_only: bool = False) -> AsyncGenerator[None, None]:
        """Context manager for database transactions.

        Args:
            read_only: If True, use a read-only transaction (BEGIN DEFERRED).
                      If False, use a write transaction (BEGIN IMMEDIATE).
                      Default is False.

        Yields:
            None

        Commits on success, rolls back on exception.
        """
        transaction_type = "BEGIN DEFERRED" if read_only else "BEGIN IMMEDIATE"
        await self.connection.execute(transaction_type)
        try:
            yield
            await self.connection.execute("COMMIT")
        except Exception:
            await self.connection.execute("ROLLBACK")
            raise

    async def ensure_schema(self) -> None:
        """Create database schema if it doesn't exist.

        Uses CREATE TABLE IF NOT EXISTS for idempotent schema creation.
        Call this after connect() to ensure tables exist.
        """
        # Tables
        await self.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                issue_id TEXT NOT NULL,
                worktree_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                failure_reason TEXT,
                state_json TEXT NOT NULL
            )
        """)

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
                is_error INTEGER NOT NULL DEFAULT 0,
                trace_id TEXT,
                parent_id TEXT
            )
        """)

        await self.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
                agent TEXT NOT NULL,
                model TEXT NOT NULL DEFAULT 'claude-sonnet-4-20250514',
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                cache_read_tokens INTEGER DEFAULT 0,
                cache_creation_tokens INTEGER DEFAULT 0,
                cost_usd REAL NOT NULL,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                num_turns INTEGER NOT NULL DEFAULT 1,
                timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Prompt configuration tables
        await self.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                id TEXT PRIMARY KEY,
                agent TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                current_version_id TEXT
            )
        """)

        await self.execute("""
            CREATE TABLE IF NOT EXISTS prompt_versions (
                id TEXT PRIMARY KEY,
                prompt_id TEXT NOT NULL REFERENCES prompts(id),
                version_number INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                change_note TEXT,
                UNIQUE(prompt_id, version_number)
            )
        """)

        await self.execute("""
            CREATE TABLE IF NOT EXISTS workflow_prompt_versions (
                workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
                prompt_id TEXT NOT NULL REFERENCES prompts(id),
                version_id TEXT NOT NULL REFERENCES prompt_versions(id),
                PRIMARY KEY (workflow_id, prompt_id)
            )
        """)

        # Indexes
        await self.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflows_issue_id ON workflows(issue_id)"
        )
        await self.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status)"
        )
        await self.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflows_worktree ON workflows(worktree_path)"
        )
        await self.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflows_started_at ON workflows(started_at DESC)"
        )
        # Unique constraint: one active workflow per worktree
        # Note: 'pending' is intentionally excluded - multiple pending workflows
        # are allowed per worktree (per queue workflows design doc). Only
        # in_progress and blocked workflows must be unique per worktree.
        #
        # Drop and recreate to ensure predicate is correct on upgraded DBs.
        # Older versions may have had 'pending' in the predicate.
        await self.execute("DROP INDEX IF EXISTS idx_workflows_active_worktree")
        await self.execute("""
            CREATE UNIQUE INDEX idx_workflows_active_worktree
                ON workflows(worktree_path)
                WHERE status IN ('in_progress', 'blocked')
        """)
        await self.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_events_workflow_sequence
                ON events(workflow_id, sequence)
        """)
        await self.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_workflow ON events(workflow_id, timestamp)"
        )
        await self.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)"
        )
        await self.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_level ON events(level)"
        )
        await self.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_trace_id ON events(trace_id)"
        )
        await self.execute(
            "CREATE INDEX IF NOT EXISTS idx_tokens_workflow ON token_usage(workflow_id)"
        )
        await self.execute(
            "CREATE INDEX IF NOT EXISTS idx_tokens_agent ON token_usage(agent)"
        )
        await self.execute(
            "CREATE INDEX IF NOT EXISTS idx_prompt_versions_prompt ON prompt_versions(prompt_id)"
        )
        await self.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflow_prompts_workflow ON workflow_prompt_versions(workflow_id)"
        )

        # Brainstorming tables
        await self.execute("""
            CREATE TABLE IF NOT EXISTS brainstorm_sessions (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                driver_session_id TEXT,
                driver_type TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                topic TEXT,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
        """)

        await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_brainstorm_sessions_profile
            ON brainstorm_sessions(profile_id)
        """)

        await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_brainstorm_sessions_status
            ON brainstorm_sessions(status)
        """)

        # Migration: Add driver_type column to existing brainstorm_sessions tables
        try:
            await self.execute(
                "ALTER TABLE brainstorm_sessions ADD COLUMN driver_type TEXT"
            )
        except Exception as e:
            # SQLite "duplicate column" error - safe to ignore for idempotent migrations
            if "duplicate column" not in str(e).lower():
                raise
            logger.debug("Column already exists, skipping", column="driver_type", error=str(e))

        await self.execute("""
            CREATE TABLE IF NOT EXISTS brainstorm_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES brainstorm_sessions(id) ON DELETE CASCADE,
                sequence INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                parts_json TEXT,
                created_at TIMESTAMP NOT NULL,
                input_tokens INTEGER,
                output_tokens INTEGER,
                cost_usd REAL,
                is_system INTEGER NOT NULL DEFAULT 0,
                UNIQUE(session_id, sequence)
            )
        """)

        # Migration: Add columns to existing brainstorm_messages tables
        # These ALTER TABLE statements are idempotent (ignore if column exists)
        for column, col_type, default in [
            ("input_tokens", "INTEGER", None),
            ("output_tokens", "INTEGER", None),
            ("cost_usd", "REAL", None),
            ("is_system", "INTEGER NOT NULL", "0"),
        ]:
            try:
                if default is not None:
                    await self.execute(
                        f"ALTER TABLE brainstorm_messages ADD COLUMN {column} {col_type} DEFAULT {default}"
                    )
                else:
                    await self.execute(
                        f"ALTER TABLE brainstorm_messages ADD COLUMN {column} {col_type}"
                    )
            except Exception as e:
                # SQLite "duplicate column" error - safe to ignore for idempotent migrations
                if "duplicate column" not in str(e).lower():
                    raise
                logger.debug("Column already exists, skipping", column=column, error=str(e))

        # Data migration: Mark existing priming messages as system messages
        # Priming messages are sequence 1, user role, and start with the skill header
        await self.execute("""
            UPDATE brainstorm_messages
            SET is_system = 1
            WHERE sequence = 1
              AND role = 'user'
              AND content LIKE '# Brainstorming Ideas Into Designs%'
              AND is_system = 0
        """)

        await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_brainstorm_messages_session
            ON brainstorm_messages(session_id, sequence)
        """)

        await self.execute("""
            CREATE TABLE IF NOT EXISTS brainstorm_artifacts (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES brainstorm_sessions(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                path TEXT NOT NULL,
                title TEXT,
                created_at TIMESTAMP NOT NULL
            )
        """)

        await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_brainstorm_artifacts_session
            ON brainstorm_artifacts(session_id)
        """)

        # Server settings singleton table
        await self.execute("""
            CREATE TABLE IF NOT EXISTS server_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                log_retention_days INTEGER NOT NULL DEFAULT 30,
                log_retention_max_events INTEGER NOT NULL DEFAULT 100000,
                trace_retention_days INTEGER NOT NULL DEFAULT 7,
                checkpoint_retention_days INTEGER NOT NULL DEFAULT 0,
                checkpoint_path TEXT NOT NULL DEFAULT '~/.amelia/checkpoints.db',
                websocket_idle_timeout_seconds REAL NOT NULL DEFAULT 300.0,
                workflow_start_timeout_seconds REAL NOT NULL DEFAULT 60.0,
                max_concurrent INTEGER NOT NULL DEFAULT 5,
                stream_tool_results INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Profiles table
        await self.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                tracker TEXT NOT NULL DEFAULT 'noop',
                working_dir TEXT NOT NULL,
                plan_output_dir TEXT NOT NULL DEFAULT 'docs/plans',
                plan_path_pattern TEXT NOT NULL DEFAULT 'docs/plans/{date}-{issue_key}.md',
                auto_approve_reviews INTEGER NOT NULL DEFAULT 0,
                agents TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Check for old schema with 'driver' column (breaking change migration)
        await self._check_old_profiles_schema()

        # Data migration: Convert legacy type values to new simplified values
        # TrackerType: 'none' -> 'noop'
        await self.execute("UPDATE profiles SET tracker = 'noop' WHERE tracker = 'none'")

        # DriverType in agents JSON: 'cli:claude' -> 'cli', 'api:openrouter' -> 'api'
        await self.execute("""
            UPDATE profiles
            SET agents = REPLACE(REPLACE(agents, '"cli:claude"', '"cli"'), '"api:openrouter"', '"api"')
            WHERE agents LIKE '%cli:claude%' OR agents LIKE '%api:openrouter%'
        """)

        # DriverType in brainstorm_sessions
        await self.execute(
            "UPDATE brainstorm_sessions SET driver_type = 'cli' WHERE driver_type = 'cli:claude'"
        )
        await self.execute(
            "UPDATE brainstorm_sessions SET driver_type = 'api' WHERE driver_type = 'api:openrouter'"
        )

        # Triggers to ensure only one active profile (both INSERT and UPDATE)
        await self.execute("""
            CREATE TRIGGER IF NOT EXISTS ensure_single_active_profile
            AFTER UPDATE OF is_active ON profiles
            WHEN NEW.is_active = 1
            BEGIN
                UPDATE profiles SET is_active = 0 WHERE id != NEW.id;
            END
        """)
        await self.execute("""
            CREATE TRIGGER IF NOT EXISTS ensure_single_active_profile_insert
            AFTER INSERT ON profiles
            WHEN NEW.is_active = 1
            BEGIN
                UPDATE profiles SET is_active = 0 WHERE id != NEW.id;
            END
        """)

        # Index for active profile lookup
        await self.execute(
            "CREATE INDEX IF NOT EXISTS idx_profiles_active ON profiles(is_active)"
        )

    async def _check_old_profiles_schema(self) -> None:
        """Check for old profiles schema and warn user to migrate.

        The database schema changed from having separate driver/model columns
        to a single 'agents' JSON column. Users with old databases need to
        delete and recreate.
        """
        try:
            cursor = await self.connection.execute("PRAGMA table_info(profiles)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

            # Old schema had 'driver' column, new schema has 'agents' column
            if "driver" in column_names:
                logger.warning(
                    "Database has old schema with 'driver' column in profiles table. "
                    "The schema has changed to use per-agent configuration. "
                    "Please delete the database file and restart Amelia.",
                    database_path=str(self._db_path),
                )
                logger.warning(
                    "To delete the database, run: rm {database_path}",
                    database_path=str(self._db_path),
                )
        except Exception as e:
            logger.debug("Failed to check profiles schema", error=str(e))

    async def initialize_prompts(self) -> None:
        """Seed prompts table from defaults. Idempotent.

        Creates prompt entries for each default if they don't exist.
        Call this after ensure_schema().
        """
        for prompt_id, default in PROMPT_DEFAULTS.items():
            existing = await self.fetch_one(
                "SELECT 1 FROM prompts WHERE id = ?", (prompt_id,)
            )
            if not existing:
                await self.execute(
                    """INSERT INTO prompts (id, agent, name, description, current_version_id)
                       VALUES (?, ?, ?, ?, NULL)""",
                    (prompt_id, default.agent, default.name, default.description),
                )
