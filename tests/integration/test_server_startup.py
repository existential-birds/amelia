"""Integration tests for server startup."""
import asyncio
import os
import socket
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

import amelia.server.main as main_module
from amelia.server.main import app, get_config, lifespan


def find_free_port() -> int:
    """Find an available port for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestServerStartup:
    """Integration tests for full server startup."""

    @pytest.fixture
    async def server(self):
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

    @pytest.mark.asyncio
    async def test_server_starts_and_responds(self, server):
        """Server starts and responds to health checks."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{server}/api/health/live")

            assert response.status_code == 200
            assert response.json()["status"] == "alive"

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_metrics(self, server):
        """Health endpoint returns system metrics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{server}/api/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] in ("healthy", "degraded")
            assert "memory_mb" in data
            assert "uptime_seconds" in data

    @pytest.mark.asyncio
    async def test_docs_endpoint_available(self, server):
        """Swagger docs are accessible."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{server}/api/docs")

            assert response.status_code == 200
            assert "swagger" in response.text.lower() or "openapi" in response.text.lower()

    @pytest.mark.asyncio
    async def test_openapi_schema_available(self, server):
        """OpenAPI schema is accessible."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{server}/api/openapi.json")

            assert response.status_code == 200
            schema = response.json()
            assert schema["info"]["title"] == "Amelia API"


class TestLifespanStartup:
    """Tests for lifespan startup behavior."""

    @pytest.mark.asyncio
    async def test_lifespan_creates_database_directory(self):
        """Lifespan creates database parent directory if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set up a database path in a non-existent subdirectory
            db_path = Path(tmpdir) / "nested" / "dir" / "test.db"
            assert not db_path.parent.exists()

            with patch.dict(os.environ, {"AMELIA_DATABASE_PATH": str(db_path)}):
                # Create a fresh app for this test
                test_app = FastAPI(lifespan=lifespan)

                # Run the lifespan
                async with lifespan(test_app):
                    # Directory should be created
                    assert db_path.parent.exists()
                    assert db_path.parent.is_dir()

    @pytest.mark.asyncio
    async def test_lifespan_initializes_config(self):
        """Lifespan initializes config so get_config works."""
        # Ensure config is None before test
        main_module._config = None

        test_app = FastAPI(lifespan=lifespan)

        async with lifespan(test_app):
            # Config should be available during lifespan
            config = get_config()
            assert config is not None
            assert config.host == "127.0.0.1"

        # Config should be None after lifespan exits
        assert main_module._config is None
