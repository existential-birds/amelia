"""Database connection management with SQLite."""
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger


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
                worktree_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
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
                message TEXT NOT NULL,
                data_json TEXT,
                correlation_id TEXT
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
                cost_usd REAL,
                timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        await self.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_workflows_active_worktree
                ON workflows(worktree_path)
                WHERE status IN ('pending', 'in_progress', 'blocked')
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
            "CREATE INDEX IF NOT EXISTS idx_tokens_workflow ON token_usage(workflow_id)"
        )
        await self.execute(
            "CREATE INDEX IF NOT EXISTS idx_tokens_agent ON token_usage(agent)"
        )
