"""Tests for database integration with FastAPI app."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.integration


class TestAppDatabaseIntegration:
    """Tests for database integration."""

    @pytest.fixture
    def database_url(self) -> str:
        """PostgreSQL test database URL."""
        return os.environ.get(
            "DATABASE_URL",
            "postgresql://amelia:amelia@localhost:5432/amelia_test",
        )

    def test_health_returns_database_status(self, database_url: str) -> None:
        """Health endpoint returns database status."""
        with patch.dict(os.environ, {"AMELIA_DATABASE_URL": database_url}):
            from amelia.server.main import create_app  # noqa: PLC0415

            app = create_app()
            client = TestClient(app)

            with client:
                response = client.get("/api/health")
                data = response.json()
                assert "database" in data
                assert data["database"]["status"] == "healthy"
