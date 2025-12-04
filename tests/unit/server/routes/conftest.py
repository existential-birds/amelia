"""Shared fixtures for route tests."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from amelia.server.database import WorkflowRepository
from amelia.server.routes.workflows import configure_exception_handlers, get_repository, router


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Create a mock workflow repository."""
    return AsyncMock(spec=WorkflowRepository)


@pytest.fixture
def app(mock_repository: AsyncMock) -> FastAPI:
    """Create a test FastAPI app."""
    test_app = FastAPI()
    configure_exception_handlers(test_app)
    test_app.include_router(router)

    # Override the repository dependency
    test_app.dependency_overrides[get_repository] = lambda: mock_repository

    return test_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    """Create an async test client."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
