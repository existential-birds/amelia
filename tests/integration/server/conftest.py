"""Shared fixtures for server integration tests.

Provides common test utilities for FastAPI async client testing,
reducing duplication across test_brainstorm_*.py files.
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from amelia.server.database.brainstorm_repository import BrainstormRepository
from amelia.server.database.connection import Database
from amelia.server.dependencies import get_orchestrator, get_profile_repository
from amelia.server.events.bus import EventBus
from amelia.server.main import create_app
from amelia.server.routes.brainstorm import (
    get_brainstorm_service,
    get_cwd,
    get_driver,
)
from amelia.server.services.brainstorm import BrainstormService


# Type alias for the async client factory
AsyncClientFactory = Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]]


@asynccontextmanager
async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
    """No-op lifespan that skips database/orchestrator initialization.

    Use this when testing routes with dependency overrides that don't
    require the full application lifespan.
    """
    yield


@pytest.fixture
def async_client_factory() -> AsyncClientFactory:
    """Factory for creating httpx.AsyncClient with ASGITransport.

    Use this fixture when you need an async test client that runs in the
    same event loop as the asyncpg pool (unlike TestClient which creates
    a separate thread with its own event loop).

    Example:
        @pytest.fixture
        async def test_client(
            async_client_factory,
            test_brainstorm_service: BrainstormService,
        ) -> AsyncGenerator[httpx.AsyncClient, None]:
            app = create_app()
            app.router.lifespan_context = noop_lifespan
            app.dependency_overrides[get_brainstorm_service] = lambda: test_brainstorm_service
            async with async_client_factory(app) as client:
                yield client
    """

    @asynccontextmanager
    async def _create_client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client

    return _create_client


@pytest.fixture
def test_brainstorm_repository(test_db: Database) -> BrainstormRepository:
    """Create repository backed by test database."""
    return BrainstormRepository(test_db)


@pytest.fixture
def test_brainstorm_service(
    test_brainstorm_repository: BrainstormRepository,
    test_event_bus: EventBus,
) -> BrainstormService:
    """Create real BrainstormService with test dependencies."""
    return BrainstormService(test_brainstorm_repository, test_event_bus)


def _create_app_with_overrides(
    brainstorm_service: BrainstormService,
    driver_dep: Any,
    cwd: str,
) -> FastAPI:
    """Create FastAPI app with noop lifespan and dependency overrides."""
    app = create_app()

    app.router.lifespan_context = noop_lifespan
    app.dependency_overrides[get_brainstorm_service] = lambda: brainstorm_service
    app.dependency_overrides[get_driver] = driver_dep
    app.dependency_overrides[get_cwd] = lambda: cwd

    # Override dependencies that would otherwise require the database lifespan
    mock_profile_repo = AsyncMock()
    mock_profile_repo.get_profile = AsyncMock(return_value=None)
    app.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo

    mock_orch = MagicMock()
    mock_orch.queue_workflow = AsyncMock(
        return_value="00000000-0000-4000-8000-000000000001"
    )
    app.dependency_overrides[get_orchestrator] = lambda: mock_orch

    return app
