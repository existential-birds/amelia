"""Tests for FastAPI application setup."""

from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from amelia.server.main import app


class TestAppSetup:
    """Tests for FastAPI app configuration."""

    def test_openapi_url(self) -> None:
        """OpenAPI schema at /api/openapi.json."""
        assert app.openapi_url == "/api/openapi.json"

    def test_cors_middleware_configured(self) -> None:
        """CORS middleware is configured on the app."""
        cors_middleware = None
        for middleware in app.user_middleware:
            if middleware.cls is CORSMiddleware:
                cors_middleware = middleware
                break

        assert cors_middleware is not None, "CORSMiddleware not found in app middleware"
        assert "http://127.0.0.1:8420" in cors_middleware.kwargs["allow_origins"]
        assert "http://localhost:8420" in cors_middleware.kwargs["allow_origins"]
        assert "http://127.0.0.1:8421" in cors_middleware.kwargs["allow_origins"]
        assert "http://localhost:8421" in cors_middleware.kwargs["allow_origins"]
        assert cors_middleware.kwargs["allow_credentials"] is True


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_live_returns_200(self, mock_app_client: TestClient) -> None:
        """Liveness probe returns 200."""
        response = mock_app_client.get("/api/health/live")

        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

    def test_health_ready_returns_200(self, mock_app_client: TestClient) -> None:
        """Readiness probe returns 200 when ready."""
        response = mock_app_client.get("/api/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"

    def test_health_returns_detailed_info(self, mock_app_client: TestClient) -> None:
        """Main health endpoint returns detailed info."""
        response = mock_app_client.get("/api/health")

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

    def test_health_includes_database_status(self, mock_app_client: TestClient) -> None:
        """Health check includes database status."""
        response = mock_app_client.get("/api/health")
        data = response.json()

        assert "database" in data
        assert "status" in data["database"]
