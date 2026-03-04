"""Shared fixtures for server tests."""

import os
from collections.abc import AsyncGenerator, AsyncIterator, Generator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.database import WorkflowRepository
from amelia.server.database.connection import Database
from amelia.server.dependencies import get_repository


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://amelia:amelia@localhost:5432/amelia_test",
)


@pytest.fixture
async def db_with_schema() -> AsyncGenerator[Database, None]:
    """Create a database with schema initialized.

    Connects to database and runs migrations to create all tables.
    The database is automatically closed after the test.

    Yields:
        Database: Connected database instance with schema initialized.
    """
    async with Database(DATABASE_URL) as db:
        from amelia.server.database.migrator import Migrator

        migrator = Migrator(db)
        await migrator.run()
        yield db


@pytest.fixture
def mock_app_client() -> Generator[TestClient, None, None]:
    """FastAPI test client with noop lifespan and dependency overrides.

    Bypasses the real lifespan entirely (no database, migrator, etc.)
    and sets only the app.state attributes that health endpoints need.
    """
    from amelia.server.main import create_app

    app = create_app()

    @asynccontextmanager
    async def noop_lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield

    app.router.lifespan_context = noop_lifespan

    # Set app.state attributes that health endpoints read directly
    mock_lifecycle = MagicMock()
    mock_lifecycle.is_shutting_down = False
    app.state.lifecycle = mock_lifecycle
    app.state.start_time = datetime.now(UTC)

    # Override get_repository for health endpoint
    mock_repo = MagicMock(spec=WorkflowRepository)
    mock_repo.count_active = AsyncMock(return_value=0)
    mock_repo.db = MagicMock()
    mock_repo.db.is_healthy = AsyncMock(return_value=True)
    app.dependency_overrides[get_repository] = lambda: mock_repo

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
