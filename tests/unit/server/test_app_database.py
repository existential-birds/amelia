"""Tests for database integration with FastAPI app."""
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class TestAppDatabaseIntegration:
    """Tests for database integration."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Temporary database path."""
        return tmp_path / "test.db"

    def test_health_returns_database_status(self, temp_db_path):
        """Health endpoint returns database status."""
        with patch.dict(os.environ, {"AMELIA_DATABASE_PATH": str(temp_db_path)}):
            from amelia.server.main import create_app  # noqa: PLC0415

            app = create_app()
            client = TestClient(app)

            with client:
                response = client.get("/api/health")
                data = response.json()
                assert "database" in data
                assert data["database"]["status"] == "healthy"
                assert data["database"]["mode"] == "wal"
