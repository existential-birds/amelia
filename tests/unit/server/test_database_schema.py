"""Tests for database schema including server_settings and profiles tables."""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from amelia.server.database.connection import Database


@pytest.fixture
async def db():
    """Create an in-memory database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")
        await db.connect()
        await db.ensure_schema()
        yield db
        await db.close()


class TestServerSettingsSchema:
    """Tests for server_settings table."""

    async def test_server_settings_table_exists(self, db: Database):
        """Verify server_settings table was created."""
        row = await db.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='server_settings'"
        )
        assert row is not None

    async def test_server_settings_singleton_constraint(self, db: Database):
        """Verify only one row can exist in server_settings (id=1)."""
        # First insert should succeed
        await db.execute(
            """INSERT INTO server_settings (id, log_retention_days) VALUES (1, 30)"""
        )

        # Second insert with id=2 should fail due to CHECK constraint
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute(
                """INSERT INTO server_settings (id, log_retention_days) VALUES (2, 60)"""
            )


class TestProfilesSchema:
    """Tests for profiles table."""

    async def test_profiles_table_exists(self, db: Database):
        """Verify profiles table was created."""
        row = await db.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='profiles'"
        )
        assert row is not None

    async def test_profile_insert(self, db: Database):
        """Verify profile can be inserted."""
        import json
        agents_json = json.dumps({
            "developer": {"driver": "cli", "model": "opus", "options": {}},
            "reviewer": {"driver": "cli", "model": "haiku", "options": {}},
        })
        await db.execute(
            """INSERT INTO profiles (id, tracker, working_dir, agents, is_active)
               VALUES (?, ?, ?, ?, ?)""",
            ("dev", "none", "/path/to/repo", agents_json, True),
        )
        row = await db.fetch_one("SELECT * FROM profiles WHERE id = ?", ("dev",))
        assert row is not None
        agents = json.loads(row["agents"])
        assert agents["developer"]["driver"] == "cli"
        assert row["is_active"] == 1
