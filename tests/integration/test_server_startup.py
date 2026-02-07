"""Integration tests for server startup."""
import asyncio
import os
from collections.abc import AsyncIterator, Callable
from unittest.mock import patch

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

import amelia.server.dependencies as deps_module
from amelia.server.dependencies import get_config
from amelia.server.main import app, lifespan


@pytest.mark.integration
class TestServerStartup:
    """Integration tests for full server startup."""

    @pytest.fixture
    async def server(self, find_free_port: Callable[[], int]) -> AsyncIterator[str]:
        """Start server in background for testing."""
        port = find_free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)

        # Run server in background task
        task = asyncio.create_task(server.serve())

        # Wait for server to be ready
        base_url = f"http://127.0.0.1:{port}"
        async with httpx.AsyncClient() as client:
            for _ in range(50):  # 5 second timeout
                try:
                    response = await client.get(f"{base_url}/api/health/live")
                    if response.status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                await asyncio.sleep(0.1)

        yield base_url

        # Shutdown
        server.should_exit = True
        await task

    async def test_server_starts_and_responds(self, server: str) -> None:
        """Server starts and responds to health checks."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{server}/api/health/live")

            assert response.status_code == 200
            assert response.json()["status"] == "alive"

    async def test_health_endpoint_returns_metrics(self, server: str) -> None:
        """Health endpoint returns system metrics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{server}/api/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] in ("healthy", "degraded")
            assert "memory_mb" in data
            assert "uptime_seconds" in data

    async def test_docs_endpoint_available(self, server: str) -> None:
        """Swagger docs are accessible."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{server}/api/docs")

            assert response.status_code == 200
            assert "swagger" in response.text.lower() or "openapi" in response.text.lower()

    async def test_openapi_schema_available(self, server: str) -> None:
        """OpenAPI schema is accessible."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{server}/api/openapi.json")

            assert response.status_code == 200
            schema = response.json()
            assert schema["info"]["title"] == "Amelia API"


@pytest.mark.integration
class TestLifespanStartup:
    """Tests for lifespan startup behavior."""

    async def test_lifespan_uses_database_url_from_env(self) -> None:
        """Lifespan picks up AMELIA_DATABASE_URL from environment."""
        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql://amelia:amelia@localhost:5432/amelia_test",
        )

        with patch.dict(os.environ, {"AMELIA_DATABASE_URL": database_url}):
            # Create a fresh app for this test
            test_app = FastAPI(lifespan=lifespan)

            # Run the lifespan — connects to PostgreSQL
            async with lifespan(test_app):
                config = get_config()
                assert config is not None
                assert config.database_url == database_url

    async def test_lifespan_initializes_config(self) -> None:
        """Lifespan initializes config so get_config works."""
        # Ensure config is None before test
        deps_module._config = None

        test_app = FastAPI(lifespan=lifespan)

        async with lifespan(test_app):
            # Config should be available during lifespan
            config = get_config()
            assert config is not None
            assert config.host == "127.0.0.1"

        # Config should be None after lifespan exits
        assert deps_module._config is None
