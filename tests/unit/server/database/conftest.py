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
def migrations_dir(tmp_path: Path) -> Path:
    """Create a temporary migrations directory for testing.

    Args:
        tmp_path: Pytest's built-in temporary directory fixture.

    Returns:
        Path: Path to a temporary migrations directory.
    """
    migrations_path = tmp_path / "migrations"
    migrations_path.mkdir(exist_ok=True)
    return migrations_path


@pytest.fixture
def production_migrations_dir() -> Path:
    """Get the actual production migrations directory.

    Returns:
        Path: Path to the production migrations directory in the package.
    """
    import amelia.server.database
    return Path(amelia.server.database.__file__).parent / "migrations"


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
async def migrated_db(temp_db_path: Path, production_migrations_dir: Path) -> AsyncGenerator["Database", None]:
    """Create a database with production migrations applied.

    Runs all production migrations and yields a connected database instance.
    The database is automatically closed after the test.

    Args:
        temp_db_path: Path to temporary database file.
        production_migrations_dir: Path to production migrations directory.

    Yields:
        Database: Connected database instance with migrations applied.
    """
    from amelia.server.database.connection import Database
    from amelia.server.database.migrate import MigrationRunner

    runner = MigrationRunner(temp_db_path, production_migrations_dir)
    await runner.run_migrations()

    async with Database(temp_db_path) as db:
        yield db
