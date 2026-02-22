"""Tests for database schema including server_settings and profiles tables."""

import json

import asyncpg
import pytest

from amelia.server.database.connection import Database


pytestmark = pytest.mark.integration


@pytest.fixture
async def db(db_with_schema: Database) -> Database:
    """Alias for db_with_schema from database conftest."""
    return db_with_schema


class TestServerSettingsSchema:
    """Tests for server_settings table."""

    async def test_server_settings_table_exists(self, db: Database) -> None:
        """Verify server_settings table was created."""
        row = await db.fetch_one(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'server_settings'"
        )
        assert row is not None

    async def test_server_settings_singleton_constraint(self, db: Database) -> None:
        """Verify only one row can exist in server_settings (id=1)."""
        # First insert should succeed
        await db.execute(
            "INSERT INTO server_settings (id, log_retention_days) VALUES (1, 30) ON CONFLICT DO NOTHING"
        )

        # Second insert with id=2 should fail due to CHECK constraint
        with pytest.raises(asyncpg.CheckViolationError):
            await db.execute(
                "INSERT INTO server_settings (id, log_retention_days) VALUES (2, 60)"
            )


class TestProfilesSchema:
    """Tests for profiles table."""

    async def test_profiles_table_exists(self, db: Database) -> None:
        """Verify profiles table was created."""
        row = await db.fetch_one(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'profiles'"
        )
        assert row is not None

    async def test_profile_insert(self, db: Database) -> None:
        """Verify profile can be inserted."""
        agents_json = json.dumps({
            "developer": {"driver": "claude", "model": "opus", "options": {}},
            "reviewer": {"driver": "claude", "model": "haiku", "options": {}},
        })
        await db.execute(
            """INSERT INTO profiles (id, tracker, repo_root, agents, is_active)
               VALUES ($1, $2, $3, $4::jsonb, $5)""",
            "dev", "none", "/path/to/repo", agents_json, True,
        )
        row = await db.fetch_one("SELECT * FROM profiles WHERE id = $1", "dev")
        assert row is not None
        agents = json.loads(row["agents"]) if isinstance(row["agents"], str) else row["agents"]
        assert agents["developer"]["driver"] == "claude"
        assert row["is_active"] is True
