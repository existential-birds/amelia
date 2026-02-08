"""Shared fixtures for database tests."""

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from amelia.server.database.connection import Database
from amelia.server.database.repository import WorkflowRepository
from amelia.server.models.state import ServerExecutionState


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://amelia:amelia@localhost:5432/amelia_test",
)


@pytest.fixture
async def connected_db() -> AsyncGenerator[Database, None]:
    """Create a connected Database instance for testing.

    Yields:
        Database: Connected database instance.
    """
    async with Database(DATABASE_URL) as db:
        yield db


@pytest.fixture
async def db_with_schema() -> AsyncGenerator[Database, None]:
    """Create a database with schema initialized.

    Connects to database and runs migrations to create all tables.
    Truncates all data tables before each test for isolation.

    Yields:
        Database: Connected database instance with schema initialized.
    """
    async with Database(DATABASE_URL) as db:
        from amelia.server.database.migrator import Migrator

        migrator = Migrator(db)
        await migrator.run()
        # Truncate all data tables to ensure test isolation
        await db.execute("""
            TRUNCATE TABLE
                workflow_prompt_versions, prompt_versions, prompts,
                brainstorm_artifacts, brainstorm_messages, brainstorm_sessions,
                token_usage, workflow_log, workflows,
                profiles, server_settings
            CASCADE
        """)
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
        id=str(uuid4()),
        issue_id="ISSUE-1",
        worktree_path="/tmp/test",
        workflow_status="pending",
        started_at=datetime.now(UTC),
    )
    await repository.create(wf)
    return wf
