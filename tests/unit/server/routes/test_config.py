"""Tests for config routes."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.core.types import AgentConfig, Profile
from amelia.server.database.settings_repository import ServerSettings
from amelia.server.dependencies import get_profile_repository, get_settings_repository
from amelia.server.routes.config import router


class TestGetConfig:
    """Tests for GET /api/config endpoint."""

    @pytest.fixture
    def mock_profile_repo(self) -> MagicMock:
        """Create a mock profile repository."""
        repo = MagicMock()
        repo.get_active_profile = AsyncMock(return_value=None)
        return repo

    @pytest.fixture
    def mock_settings_repo(self) -> MagicMock:
        """Create a mock settings repository."""
        repo = MagicMock()
        repo.get_server_settings = AsyncMock(
            return_value=ServerSettings(
                log_retention_days=30,
                log_retention_max_events=100000,
                trace_retention_days=7,
                checkpoint_retention_days=0,
                checkpoint_path="~/.amelia/checkpoints.db",
                websocket_idle_timeout_seconds=300.0,
                workflow_start_timeout_seconds=30.0,
                max_concurrent=5,
                stream_tool_results=False,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        )
        return repo

    @pytest.fixture
    def client(
        self, mock_profile_repo: MagicMock, mock_settings_repo: MagicMock
    ) -> TestClient:
        """Create a test client with mock dependencies."""
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo
        app.dependency_overrides[get_settings_repository] = lambda: mock_settings_repo
        return TestClient(app)

    def test_returns_empty_working_dir_when_no_active_profile(
        self,
        mock_profile_repo: MagicMock,
        mock_settings_repo: MagicMock,
        client: TestClient,
    ) -> None:
        """Should return empty working_dir when no active profile is set."""
        mock_profile_repo.get_active_profile = AsyncMock(return_value=None)

        response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert data["working_dir"] == ""
        assert data["max_concurrent"] == 5
        assert data["active_profile"] == ""
        assert data["active_profile_info"] is None

    def test_returns_config_with_active_profile(
        self,
        mock_profile_repo: MagicMock,
        mock_settings_repo: MagicMock,
        client: TestClient,
    ) -> None:
        """Should return full config when active profile exists.

        Uses 'developer' agent config for display driver/model.
        """
        mock_profile_repo.get_active_profile = AsyncMock(
            return_value=Profile(
                name="test",
                tracker="github",
                working_dir="/tmp/test-repo",
                agents={
                    "developer": AgentConfig(
                        driver="api:openrouter",
                        model="claude-3-5-sonnet",
                    ),
                },
            )
        )

        response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert data["working_dir"] == "/tmp/test-repo"
        assert data["max_concurrent"] == 5
        assert data["active_profile"] == "test"
        assert data["active_profile_info"] == {
            "name": "test",
            "driver": "api:openrouter",
            "model": "claude-3-5-sonnet",
        }

    def test_returns_max_concurrent_from_server_settings(
        self,
        mock_profile_repo: MagicMock,
        mock_settings_repo: MagicMock,
        client: TestClient,
    ) -> None:
        """Should return max_concurrent from server settings."""
        # Override max_concurrent in server settings
        mock_settings_repo.get_server_settings = AsyncMock(
            return_value=ServerSettings(
                log_retention_days=30,
                log_retention_max_events=100000,
                trace_retention_days=7,
                checkpoint_retention_days=0,
                checkpoint_path="~/.amelia/checkpoints.db",
                websocket_idle_timeout_seconds=300.0,
                workflow_start_timeout_seconds=30.0,
                max_concurrent=10,  # Different value
                stream_tool_results=False,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        )

        response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert data["max_concurrent"] == 10
