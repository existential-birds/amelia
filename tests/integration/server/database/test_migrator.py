"""Tests for schema migrator."""

import os
from collections.abc import AsyncIterator

import asyncpg
import pytest

from amelia.server.database.connection import Database
from amelia.server.database.migrator import Migrator


pytestmark = pytest.mark.integration

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://amelia:amelia@localhost:5434/amelia_test",
)

@pytest.fixture
def migration_versions() -> set[int]:
    """Load migration versions at test time, not import time."""
    return {v for v, _ in Migrator._load_migrations()}


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = Database(DATABASE_URL)
    await database.connect()
    # Drop all tables to test fresh migration
    await database.execute("DROP SCHEMA public CASCADE")
    await database.execute("CREATE SCHEMA public")
    yield database
    await database.close()


async def test_migrator_creates_schema_migrations_table(db: Database) -> None:
    migrator = Migrator(db)
    await migrator.run()
    row = await db.fetch_one(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'schema_migrations')"
    )
    assert row is not None and row[0] is True


async def test_migrator_applies_initial_schema(db: Database) -> None:
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
        assert row is not None and row[0] is True, f"Table {table} not created"


async def test_migrator_records_version(db: Database, migration_versions: set[int]) -> None:
    migrator = Migrator(db)
    await migrator.run()
    rows: list[asyncpg.Record] = await db.fetch_all(
        "SELECT version FROM schema_migrations ORDER BY version"
    )
    recorded: set[int] = {row["version"] for row in rows}
    assert recorded == migration_versions


async def test_migrator_is_idempotent(db: Database, migration_versions: set[int]) -> None:
    migrator = Migrator(db)
    await migrator.run()
    await migrator.run()  # Should not fail
    rows: list[asyncpg.Record] = await db.fetch_all(
        "SELECT version FROM schema_migrations ORDER BY version"
    )
    recorded: set[int] = {row["version"] for row in rows}
    assert recorded == migration_versions
