# tests/unit/server/database/test_connection.py
"""Tests for database connection management."""

import pytest
from aiosqlite import IntegrityError

from amelia.server.database.connection import Database


class TestDatabaseConnection:
    """Tests for Database class."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Temporary database path for testing."""
        return tmp_path / "test.db"

    @pytest.mark.asyncio
    async def test_database_creates_directory(self, temp_db_path):
        """Database creates parent directory if it doesn't exist."""
        nested_path = temp_db_path.parent / "nested" / "dir" / "test.db"
        db = Database(nested_path)

        await db.connect()
        await db.close()

        assert nested_path.parent.exists()

    @pytest.mark.asyncio
    async def test_database_connect_creates_file(self, temp_db_path):
        """Database file is created on connect."""
        db = Database(temp_db_path)
        await db.connect()
        await db.close()

        assert temp_db_path.exists()

    @pytest.mark.asyncio
    async def test_database_wal_mode_enabled(self, temp_db_path):
        """WAL mode is enabled for concurrent access."""
        db = Database(temp_db_path)
        await db.connect()

        result = await db.fetch_one("PRAGMA journal_mode")
        await db.close()

        assert result[0].lower() == "wal"

    @pytest.mark.asyncio
    async def test_database_foreign_keys_enabled(self, temp_db_path):
        """Foreign keys are enforced."""
        db = Database(temp_db_path)
        await db.connect()

        result = await db.fetch_one("PRAGMA foreign_keys")
        await db.close()

        assert result[0] == 1

    @pytest.mark.asyncio
    async def test_database_execute(self, temp_db_path):
        """Execute runs SQL statements."""
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
        async with Database(temp_db_path) as db:
            await db.execute("CREATE TABLE test (id INTEGER)")

        # Connection should be closed
        assert temp_db_path.exists()

    @pytest.mark.asyncio
    async def test_database_transaction(self, temp_db_path):
        """Transactions can be used for atomic operations."""
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
        db = Database(temp_db_path)
        await db.connect()
        await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val INTEGER UNIQUE)")
        await db.execute("INSERT INTO test (val) VALUES (1)")

        with pytest.raises(IntegrityError):
            async with db.transaction():
                await db.execute("INSERT INTO test (val) VALUES (2)")
                await db.execute("INSERT INTO test (val) VALUES (1)")  # Duplicate - fails

        # Only original row should exist
        results = await db.fetch_all("SELECT val FROM test")
        await db.close()

        assert len(results) == 1
        assert results[0][0] == 1
