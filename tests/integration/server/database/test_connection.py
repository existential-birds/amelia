"""Tests for asyncpg database connection management."""

import pytest
import asyncpg

from amelia.server.database.connection import Database

pytestmark = pytest.mark.integration

DATABASE_URL = "postgresql://amelia:amelia@localhost:5432/amelia_test"


@pytest.fixture
async def db():
    """Create a connected Database instance with a test table."""
    database = Database(DATABASE_URL)
    await database.connect()
    await database.execute("DROP TABLE IF EXISTS _test_table")
    await database.execute(
        "CREATE TABLE _test_table (id SERIAL PRIMARY KEY, name TEXT)"
    )
    yield database
    await database.execute("DROP TABLE IF EXISTS _test_table")
    await database.close()


async def test_connect_creates_pool(db):
    """After connect(), pool property returns an asyncpg pool."""
    assert db.pool is not None


async def test_close_closes_pool():
    """After close(), pool is None."""
    database = Database(DATABASE_URL)
    await database.connect()
    await database.close()
    assert database._pool is None


async def test_context_manager():
    """async with Database(url) connects and closes."""
    async with Database(DATABASE_URL) as database:
        assert database.pool is not None
    assert database._pool is None


async def test_is_healthy(db):
    """Connected database returns True for is_healthy."""
    assert await db.is_healthy() is True


async def test_is_healthy_not_connected():
    """Unconnected database returns False for is_healthy."""
    database = Database(DATABASE_URL)
    assert await database.is_healthy() is False


async def test_execute_insert(db):
    """INSERT returns row count of 1."""
    count = await db.execute(
        "INSERT INTO _test_table (name) VALUES ($1)", "alice"
    )
    assert count == 1


async def test_fetch_one(db):
    """fetch_one returns a Record with expected data."""
    await db.execute("INSERT INTO _test_table (name) VALUES ($1)", "bob")
    row = await db.fetch_one(
        "SELECT name FROM _test_table WHERE name = $1", "bob"
    )
    assert row is not None
    assert row["name"] == "bob"


async def test_fetch_one_returns_none(db):
    """fetch_one returns None when no match."""
    row = await db.fetch_one(
        "SELECT name FROM _test_table WHERE name = $1", "nobody"
    )
    assert row is None


async def test_fetch_all(db):
    """fetch_all returns list of Records."""
    await db.execute("INSERT INTO _test_table (name) VALUES ($1)", "alice")
    await db.execute("INSERT INTO _test_table (name) VALUES ($1)", "bob")
    rows = await db.fetch_all("SELECT name FROM _test_table ORDER BY name")
    assert len(rows) == 2
    assert rows[0]["name"] == "alice"


async def test_fetch_scalar(db):
    """fetch_scalar returns single value."""
    await db.execute("INSERT INTO _test_table (name) VALUES ($1)", "alice")
    count = await db.fetch_scalar("SELECT COUNT(*) FROM _test_table")
    assert count == 1


async def test_transaction_commits(db):
    """Data persists after successful transaction."""
    async with db.transaction() as conn:
        await conn.execute(
            "INSERT INTO _test_table (name) VALUES ($1)", "committed"
        )
    row = await db.fetch_one(
        "SELECT name FROM _test_table WHERE name = $1", "committed"
    )
    assert row is not None


async def test_transaction_rolls_back(db):
    """Data does not persist when exception raised in transaction."""
    with pytest.raises(ValueError):
        async with db.transaction() as conn:
            await conn.execute(
                "INSERT INTO _test_table (name) VALUES ($1)", "rolled_back"
            )
            raise ValueError("force rollback")
    row = await db.fetch_one(
        "SELECT name FROM _test_table WHERE name = $1", "rolled_back"
    )
    assert row is None
