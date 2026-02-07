"""Shared fixtures for server tests."""

import os
from collections.abc import AsyncGenerator, Callable, Generator
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from amelia.server.database import WorkflowRepository
from amelia.server.database.connection import Database
from amelia.server.dependencies import get_repository
from amelia.server.models.events import EventType, WorkflowEvent


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
def make_event() -> Callable[..., WorkflowEvent]:
    """Factory fixture for creating WorkflowEvent instances with sensible defaults.

    Returns:
        A function that creates WorkflowEvent instances with default values
        that can be overridden via keyword arguments.

    Example:
        def test_something(make_event):
            event = make_event(agent="developer", event_type=EventType.FILE_CREATED)
            assert event.agent == "developer"
    """

    def _make_event(**overrides: Any) -> WorkflowEvent:
        """Create a WorkflowEvent with sensible defaults."""
        defaults: dict[str, Any] = {
            "id": "event-123",
            "workflow_id": "wf-456",
            "sequence": 1,
            "timestamp": datetime(2025, 1, 1, 12, 0, 0),
            "agent": "system",
            "event_type": EventType.WORKFLOW_STARTED,
            "message": "Test event",
        }
        return WorkflowEvent(**{**defaults, **overrides})

    return _make_event


@pytest.fixture
def mock_app_client() -> Generator[TestClient, None, None]:
    """FastAPI test client with mocked lifespan dependencies.

    Patches Database, Migrator, AsyncPostgresSaver, and other lifespan
    components so the app can start without a real PostgreSQL connection.
    """
    mock_db = MagicMock()
    mock_db.connect = AsyncMock()
    mock_db.close = AsyncMock()
    mock_db.pool = MagicMock()

    mock_migrator = MagicMock()
    mock_migrator.run = AsyncMock()
    mock_migrator.initialize_prompts = AsyncMock()

    mock_settings_repo = MagicMock()
    mock_settings_repo.ensure_defaults = AsyncMock()
    mock_settings_repo.get_server_settings = AsyncMock(
        return_value=MagicMock(max_concurrent=5)
    )

    mock_checkpointer = AsyncMock()
    mock_checkpointer.setup = AsyncMock()

    with (
        patch("amelia.server.main.Database", return_value=mock_db),
        patch("amelia.server.main.Migrator", return_value=mock_migrator),
        patch("amelia.server.main.SettingsRepository", return_value=mock_settings_repo),
        patch(
            "langgraph.checkpoint.postgres.aio.AsyncPostgresSaver",
            return_value=mock_checkpointer,
        ),
        patch("amelia.server.main.LogRetentionService"),
        patch("amelia.server.main.ServerLifecycle") as mock_lifecycle_cls,
        patch("amelia.server.main.WorktreeHealthChecker") as mock_health_cls,
    ):
        mock_lifecycle = mock_lifecycle_cls.return_value
        mock_lifecycle.startup = AsyncMock()
        mock_lifecycle.shutdown = AsyncMock()
        mock_health = mock_health_cls.return_value
        mock_health.start = AsyncMock()
        mock_health.stop = AsyncMock()

        from amelia.server.main import app

        # Mock workflow repository for health endpoint
        mock_repo = MagicMock(spec=WorkflowRepository)
        mock_repo.count_active = AsyncMock(return_value=0)
        app.dependency_overrides[get_repository] = lambda: mock_repo

        with TestClient(app) as client:
            yield client

        app.dependency_overrides.clear()
