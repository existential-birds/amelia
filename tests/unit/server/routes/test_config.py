"""Tests for config routes."""
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.dependencies import get_config
from amelia.server.routes.config import router


class TestGetConfig:
    """Tests for GET /api/config endpoint."""

    def test_returns_config_with_working_dir(self) -> None:
        """Should return working_dir when set."""
        mock_config = MagicMock()
        mock_config.working_dir = Path("/tmp/test-repo")
        mock_config.max_concurrent = 5

        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_config] = lambda: mock_config
        client = TestClient(app)

        response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert data["working_dir"] == "/tmp/test-repo"
        assert data["max_concurrent"] == 5

    def test_returns_null_working_dir_when_not_set(self) -> None:
        """Should return null working_dir when not configured."""
        mock_config = MagicMock()
        mock_config.working_dir = None
        mock_config.max_concurrent = 5

        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_config] = lambda: mock_config
        client = TestClient(app)

        response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert data["working_dir"] is None
        assert data["max_concurrent"] == 5
