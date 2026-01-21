# tests/unit/server/routes/test_settings_routes.py
"""Tests for settings API routes."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.database import ServerSettings
from amelia.server.routes.settings import get_settings_repository, router


@pytest.fixture
def mock_repo():
    """Create mock settings repository."""
    repo = MagicMock()
    repo.get_server_settings = AsyncMock()
    repo.update_server_settings = AsyncMock()
    return repo


@pytest.fixture
def app(mock_repo):
    """Create test FastAPI app with settings router."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings_repository] = lambda: mock_repo
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestSettingsRoutes:
    """Tests for /api/settings endpoints."""

    def test_get_server_settings(self, client, mock_repo):
        """GET /api/settings returns current settings."""
        mock_settings = ServerSettings(
            log_retention_days=30,
            log_retention_max_events=100000,
            trace_retention_days=7,
            checkpoint_retention_days=0,
            checkpoint_path="~/.amelia/checkpoints.db",
            websocket_idle_timeout_seconds=300.0,
            workflow_start_timeout_seconds=60.0,
            max_concurrent=5,
            stream_tool_results=False,
            created_at=None,
            updated_at=None,
        )
        mock_repo.get_server_settings.return_value = mock_settings

        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["log_retention_days"] == 30
        assert data["max_concurrent"] == 5

    def test_update_server_settings(self, client, mock_repo):
        """PUT /api/settings updates settings."""
        # Return updated settings
        mock_repo.update_server_settings.return_value = ServerSettings(
            log_retention_days=60,
            log_retention_max_events=100000,
            trace_retention_days=7,
            checkpoint_retention_days=0,
            checkpoint_path="~/.amelia/checkpoints.db",
            websocket_idle_timeout_seconds=300.0,
            workflow_start_timeout_seconds=60.0,
            max_concurrent=10,
            stream_tool_results=False,
            created_at=None,
            updated_at=None,
        )

        response = client.put(
            "/api/settings",
            json={"log_retention_days": 60, "max_concurrent": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["log_retention_days"] == 60
        assert data["max_concurrent"] == 10
