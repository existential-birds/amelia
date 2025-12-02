"""Tests for database integration with FastAPI app."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


class TestAppDatabaseIntegration:
    """Tests for database integration."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Temporary database path."""
        return tmp_path / "test.db"

    def test_health_check_verifies_database(self, temp_db_path):
        """Health endpoint verifies database connectivity."""
        import os
        with patch.dict(os.environ, {"AMELIA_DATABASE_PATH": str(temp_db_path)}):
            from amelia.server.main import create_app

            app = create_app()
            client = TestClient(app)

            # Trigger startup event and make request within context
            with client:
                response = client.get("/api/health")
                data = response.json()
                assert "database" in data
                assert data["database"]["status"] in ("healthy", "degraded")

    def test_database_health_check_writes_and_reads(self, temp_db_path):
        """Database health check performs write/read cycle."""
        import os
        with patch.dict(os.environ, {"AMELIA_DATABASE_PATH": str(temp_db_path)}):
            from amelia.server.main import create_app

            app = create_app()
            client = TestClient(app)

            with client:
                response = client.get("/api/health")
                data = response.json()
                # Should be healthy after successful write/read
                assert data["database"]["status"] == "healthy"

    def test_database_health_reports_error_on_failure(self, temp_db_path):
        """Database health check reports error message when degraded."""
        import os
        with patch.dict(os.environ, {"AMELIA_DATABASE_PATH": str(temp_db_path)}):
            from amelia.server.main import create_app

            app = create_app()
            client = TestClient(app)

            # Mock database to simulate failure after startup
            with client, patch('amelia.server.main.get_database') as mock_get_db:
                mock_db = AsyncMock()
                mock_db.execute.side_effect = Exception("Connection lost")
                mock_get_db.return_value = mock_db

                response = client.get("/api/health")
                data = response.json()

                assert data["database"]["status"] == "degraded"
                assert data["database"]["error"] is not None
                assert "Connection lost" in data["database"]["error"]
