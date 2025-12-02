"""Database connection management with SQLite."""
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

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
        result = await cursor.fetchall()
        return list(result)

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
