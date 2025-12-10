# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# tests/unit/server/database/test_connection.py
"""Tests for database connection management."""

import pytest
from aiosqlite import IntegrityError

from amelia.server.database.connection import Database


class TestDatabaseConnection:
    """Tests for Database class."""

    async def test_database_creates_directory(self, temp_db_path):
        """Database creates parent directory if it doesn't exist."""
        nested_path = temp_db_path.parent / "nested" / "dir" / "test.db"
        db = Database(nested_path)

        await db.connect()
        await db.close()

        assert nested_path.parent.exists()

    async def test_database_connect_creates_file(self, temp_db_path):
        """Database file is created on connect."""
        db = Database(temp_db_path)
        await db.connect()
        await db.close()

        assert temp_db_path.exists()

    async def test_database_wal_mode_enabled(self, connected_db):
        """WAL mode is enabled for concurrent access."""
        result = await connected_db.fetch_one("PRAGMA journal_mode")
        assert result[0].lower() == "wal"

    async def test_database_foreign_keys_enabled(self, connected_db):
        """Foreign keys are enforced."""
        result = await connected_db.fetch_one("PRAGMA foreign_keys")
        assert result[0] == 1

    async def test_database_context_manager(self, temp_db_path):
        """Database can be used as async context manager."""
        async with Database(temp_db_path) as db:
            await db.execute("CREATE TABLE test (id INTEGER)")

        # Connection should be closed
        assert temp_db_path.exists()

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
