"""Tests for FastAPI application setup."""
import pytest
from fastapi.testclient import TestClient


class TestAppSetup:
    """Tests for FastAPI app configuration."""

    def test_app_title(self):
        """App has correct title."""
        from amelia.server.main import app

        assert app.title == "Amelia API"

    def test_app_version(self):
        """App has version set."""
        from amelia import __version__
        from amelia.server.main import app

        assert app.version == __version__

    def test_docs_url(self):
        """Swagger docs available at /api/docs."""
        from amelia.server.main import app

        assert app.docs_url == "/api/docs"

    def test_openapi_url(self):
        """OpenAPI schema at /api/openapi.json."""
        from amelia.server.main import app

        assert app.openapi_url == "/api/openapi.json"


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    @pytest.fixture
    def client(self):
        """FastAPI test client."""
        from amelia.server.main import app
        # Use context manager to ensure lifespan events are triggered
        with TestClient(app) as test_client:
            yield test_client

    def test_health_live_returns_200(self, client):
        """Liveness probe returns 200."""
        response = client.get("/api/health/live")

        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

    def test_health_ready_returns_200(self, client):
        """Readiness probe returns 200 when ready."""
        response = client.get("/api/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"

    def test_health_returns_detailed_info(self, client):
        """Main health endpoint returns detailed info."""
        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()

        # Required fields
        assert "status" in data
        assert "version" in data
        assert "uptime_seconds" in data
        assert "active_workflows" in data
        assert "websocket_connections" in data
        assert "memory_mb" in data
        assert "database" in data

        # Status should be healthy or degraded
        assert data["status"] in ("healthy", "degraded")

    def test_health_includes_database_status(self, client):
        """Health check includes database status."""
        response = client.get("/api/health")
        data = response.json()

        assert "database" in data
        assert "status" in data["database"]
