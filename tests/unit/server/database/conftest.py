"""Shared fixtures for database tests."""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest


if TYPE_CHECKING:
    from amelia.server.database.connection import Database


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Temporary database path for testing.

    Args:
        tmp_path: Pytest's built-in temporary directory fixture.

    Returns:
        Path: Path to a temporary test.db file.
    """
    return tmp_path / "test.db"


@pytest.fixture
async def connected_db(temp_db_path: Path) -> AsyncGenerator["Database", None]:
    """Create a connected Database instance for testing.

    The database is automatically connected before yielding and closed after.

    Args:
        temp_db_path: Path to temporary database file.

    Yields:
        Database: Connected database instance.
    """
    from amelia.server.database.connection import Database
    async with Database(temp_db_path) as db:
        yield db


@pytest.fixture
async def db_with_schema(temp_db_path: Path) -> AsyncGenerator["Database", None]:
    """Create a database with schema initialized.

    Connects to database and runs ensure_schema() to create all tables.
    The database is automatically closed after the test.

    Args:
        temp_db_path: Path to temporary database file.

    Yields:
        Database: Connected database instance with schema initialized.
    """
    from amelia.server.database.connection import Database

    async with Database(temp_db_path) as db:
        await db.ensure_schema()
        yield db
