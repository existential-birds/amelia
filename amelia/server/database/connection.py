"""Database connection management with PostgreSQL via asyncpg."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse, urlunparse

import asyncpg
from loguru import logger


def in_clause_placeholders(count: int, start: int = 1) -> str:
    """Generate SQL IN clause placeholders for parameterized queries.

    Args:
        count: Number of placeholders to generate.
        start: Starting parameter index (1-based).

    Returns:
        Comma-separated placeholder string, e.g. "$1,$2,$3".
    """
    return ",".join(f"${i + start}" for i in range(count))

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

    @property
    def _redacted_url(self) -> str:
        """Return the database URL with any password redacted."""
        parsed = urlparse(self._database_url)
        if parsed.password:
            netloc = f"{parsed.username}:***@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return urlunparse(parsed._replace(netloc=netloc))
        return self._database_url

    async def connect(self) -> None:
        """Create the connection pool.

        Raises:
            ConnectionError: If connection fails with a user-friendly message.
        """
        try:
            self._pool = await asyncpg.create_pool(
                self._database_url,
                min_size=self._min_size,
                max_size=self._max_size,
                init=self._init_connection,
            )
        except asyncpg.InvalidPasswordError:
            raise ConnectionError(
                f"PostgreSQL authentication failed for URL: {self._redacted_url}\n\n"
                "This usually means the database URL is missing credentials or has "
                "the wrong password.\n\n"
                "To fix, set AMELIA_DATABASE_URL with valid credentials:\n"
                "  export AMELIA_DATABASE_URL='postgresql://amelia:amelia@localhost:5432/amelia'\n\n"
                "Or add it to a .env file in your project root:\n"
                "  AMELIA_DATABASE_URL=postgresql://amelia:amelia@localhost:5432/amelia\n\n"
                "To create the database and user with Docker:\n"
                "  docker compose up -d postgres"
            ) from None
        except asyncpg.InvalidCatalogNameError as e:
            raise ConnectionError(
                f"PostgreSQL database not found: {e}\n\n"
                "The database specified in the connection URL does not exist.\n\n"
                "To create it:\n"
                "  createdb amelia\n\n"
                "Or with Docker:\n"
                "  docker compose up -d postgres"
            ) from None
        except OSError as e:
            raise ConnectionError(
                f"Cannot connect to PostgreSQL at {self._redacted_url}: {e}\n\n"
                "Make sure PostgreSQL is running and accepting connections.\n\n"
                "With Docker:\n"
                "  docker compose up -d postgres\n\n"
                "Or check that the host and port in AMELIA_DATABASE_URL are correct."
            ) from None

    @staticmethod
    async def _init_connection(conn: asyncpg.Connection) -> None:
        """Register JSON/JSONB codecs for automatic encoding/decoding."""
        await conn.set_type_codec(
            "jsonb",
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            try:
                await self._pool.close()
            except (asyncpg.PostgresError, OSError, TimeoutError) as e:
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
            return bool(result == 1)
        except (asyncpg.PostgresError, OSError, TimeoutError) as e:
            logger.warning("Database health check failed", error=str(e))
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
            # DDL statements (CREATE, DROP, ALTER) don't return row counts
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
    ) -> list[Any]:
        """Fetch all matching rows.

        Args:
            sql: SQL query.
            *args: Positional parameters.

        Returns:
            List of matching Records.
        """
        return list(await self.pool.fetch(sql, *args))

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
