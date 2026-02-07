"""Tests for schema migrator."""

import pytest

from amelia.server.database.connection import Database
from amelia.server.database.migrator import Migrator

pytestmark = pytest.mark.integration

DATABASE_URL = "postgresql://amelia:amelia@localhost:5432/amelia_test"


@pytest.fixture
async def db():
    database = Database(DATABASE_URL)
    await database.connect()
    # Drop all tables to test fresh migration
    await database.execute("DROP SCHEMA public CASCADE")
    await database.execute("CREATE SCHEMA public")
    yield database
    await database.close()


async def test_migrator_creates_schema_migrations_table(db):
    migrator = Migrator(db)
    await migrator.run()
    row = await db.fetch_one(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'schema_migrations')"
    )
    assert row[0] is True


async def test_migrator_applies_initial_schema(db):
    migrator = Migrator(db)
    await migrator.run()
    # Check that all core tables exist
    for table in [
        "workflows",
        "workflow_log",
        "token_usage",
        "profiles",
        "server_settings",
        "prompts",
        "prompt_versions",
        "workflow_prompt_versions",
        "brainstorm_sessions",
        "brainstorm_messages",
        "brainstorm_artifacts",
    ]:
        row = await db.fetch_one(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = $1)",
            table,
        )
        assert row[0] is True, f"Table {table} not created"


async def test_migrator_records_version(db):
    migrator = Migrator(db)
    await migrator.run()
    version = await db.fetch_scalar("SELECT MAX(version) FROM schema_migrations")
    assert version == 1


async def test_migrator_is_idempotent(db):
    migrator = Migrator(db)
    await migrator.run()
    await migrator.run()  # Should not fail
    version = await db.fetch_scalar("SELECT MAX(version) FROM schema_migrations")
    assert version == 1
