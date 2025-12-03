"""Shared fixtures for server tests."""

import pytest

from amelia.server.database.connection import Database


@pytest.fixture
def temp_db_path(tmp_path):
    """Temporary database path for testing."""
    return tmp_path / "test.db"


@pytest.fixture
async def connected_db(temp_db_path):
    """Connected database instance for testing."""
    db = Database(temp_db_path)
    await db.connect()
    yield db
    await db.close()
