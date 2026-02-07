"""Database connection management with PostgreSQL via asyncpg."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from loguru import logger


class Database:
    """Async PostgreSQL database connection pool manager.

    Wraps an asyncpg connection pool for concurrent database access.
    """

    def __init__(
        self,
        database_url: str,
        min_size: int = 2,
        max_size: int = 10,
    ) -> None:
        """Initialize database connection pool.

        Args:
            database_url: PostgreSQL connection URL.
            min_size: Minimum number of connections in the pool.
            max_size: Maximum number of connections in the pool.
        """
        self._database_url = database_url
        self._min_size = min_size
        self._max_size = max_size
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Create the connection pool.

        Raises:
            asyncpg.PostgresError: If connection fails.
        """
        self._pool = await asyncpg.create_pool(
            self._database_url,
            min_size=self._min_size,
            max_size=self._max_size,
        )

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            try:
                await self._pool.close()
            except Exception as e:
                logger.warning("Error closing database pool", error=str(e))
            finally:
                self._pool = None

    async def __aenter__(self) -> "Database":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    @property
    def pool(self) -> asyncpg.Pool:
        """Get the active connection pool.

        Raises:
            RuntimeError: If not connected.
        """
        if self._pool is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._pool

    async def is_healthy(self) -> bool:
        """Check if pool is valid and database is accessible.

        Returns:
            True if the connection is healthy, False otherwise.
        """
        if self._pool is None:
            return False
        try:
            result = await self._pool.fetchval("SELECT 1")
            return result == 1
        except Exception:
            return False

    async def execute(self, sql: str, *args: Any) -> int:
        """Execute SQL statement.

        Args:
            sql: SQL statement to execute.
            *args: Positional parameters for the statement.

        Returns:
            Number of rows affected (for INSERT/UPDATE/DELETE).
        """
        status = await self.pool.execute(sql, *args)
        try:
            return int(status.split()[-1])
        except (ValueError, IndexError, AttributeError):
            return 0

    async def fetch_one(
        self, sql: str, *args: Any
    ) -> asyncpg.Record | None:
        """Fetch a single row.

        Args:
            sql: SQL query.
            *args: Positional parameters.

        Returns:
            Single Record or None if not found.
        """
        return await self.pool.fetchrow(sql, *args)

    async def fetch_all(
        self, sql: str, *args: Any
    ) -> list[asyncpg.Record]:
        """Fetch all matching rows.

        Args:
            sql: SQL query.
            *args: Positional parameters.

        Returns:
            List of matching Records.
        """
        return await self.pool.fetch(sql, *args)

    async def fetch_scalar(
        self, sql: str, *args: Any
    ) -> Any:
        """Fetch a single scalar value.

        Args:
            sql: SQL query expected to return one row with one column.
            *args: Positional parameters.

        Returns:
            The scalar value, or None if no rows found.
        """
        return await self.pool.fetchval(sql, *args)

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """Context manager for database transactions.

        Yields:
            asyncpg.Connection: The connection with an active transaction.

        Commits on success, rolls back on exception.
        """
        async with self.pool.acquire() as conn, conn.transaction():
            yield conn
