"""Integration tests for server startup."""
import asyncio
import socket

import httpx
import pytest
import uvicorn

from amelia.server.main import app


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
