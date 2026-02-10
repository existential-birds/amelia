"""Shared fixtures for server integration tests.

Provides common test utilities for FastAPI async client testing,
reducing duplication across test_brainstorm_*.py files.
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import httpx
import pytest
from fastapi import FastAPI


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
