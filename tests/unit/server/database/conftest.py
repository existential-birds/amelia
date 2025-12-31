"""Shared fixtures for database tests."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from amelia.server.database.connection import Database
from amelia.server.database.repository import WorkflowRepository
from amelia.server.models.state import ServerExecutionState


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
async def connected_db(temp_db_path: Path) -> AsyncGenerator[Database, None]:
    """Create a connected Database instance for testing.

    The database is automatically connected before yielding and closed after.

    Args:
        temp_db_path: Path to temporary database file.

    Yields:
        Database: Connected database instance.
    """
    async with Database(temp_db_path) as db:
        yield db


@pytest.fixture
async def db_with_schema(temp_db_path: Path) -> AsyncGenerator[Database, None]:
    """Create a database with schema initialized.

    Connects to database and runs ensure_schema() to create all tables.
    The database is automatically closed after the test.

    Args:
        temp_db_path: Path to temporary database file.

    Yields:
        Database: Connected database instance with schema initialized.
    """
    async with Database(temp_db_path) as db:
        await db.ensure_schema()
        yield db


@pytest.fixture
async def repository(db_with_schema: Database) -> WorkflowRepository:
    """Create WorkflowRepository with initialized schema.

    Args:
        db_with_schema: Database with schema initialized.

    Returns:
        WorkflowRepository: Repository instance.
    """
    return WorkflowRepository(db_with_schema)


@pytest.fixture
async def workflow(repository: WorkflowRepository) -> ServerExecutionState:
    """Create and save a test workflow.

    Args:
        repository: WorkflowRepository instance.

    Returns:
        ServerExecutionState: Created workflow.
    """
    wf = ServerExecutionState(
        id="wf-test",
        issue_id="ISSUE-1",
        worktree_path="/tmp/test",
        worktree_name="test",
        workflow_status="pending",
        started_at=datetime.now(UTC),
    )
    await repository.create(wf)
    return wf
