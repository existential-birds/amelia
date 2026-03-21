"""Tests for config routes."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.core.types import AgentConfig, Profile
from amelia.server.dependencies import get_profile_repository, get_settings_repository
from amelia.server.routes.config import router

from .conftest import _make_server_settings


class TestGetConfig:
    """Tests for GET /api/config endpoint."""

    @pytest.fixture
    def mock_settings_repo(self) -> MagicMock:
        """Create a mock settings repository."""
        repo = MagicMock()
        repo.get_server_settings = AsyncMock(return_value=_make_server_settings())
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

    def test_returns_empty_repo_root_when_no_active_profile(
        self,
        mock_profile_repo: MagicMock,
        mock_settings_repo: MagicMock,
        client: TestClient,
    ) -> None:
        """Should return empty repo_root when no active profile is set."""
        mock_profile_repo.get_active_profile = AsyncMock(return_value=None)

        response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert data["repo_root"] == ""
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
                repo_root="/tmp/test-repo",
                agents={
                    "developer": AgentConfig(
                        driver="api",
                        model="claude-3-5-sonnet",
                    ),
                },
            )
        )

        response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert data["repo_root"] == "/tmp/test-repo"
        assert data["max_concurrent"] == 5
        assert data["active_profile"] == "test"
        assert data["active_profile_info"] == {
            "name": "test",
            "driver": "api",
            "model": "claude-3-5-sonnet",
        }

    def test_returns_max_concurrent_from_server_settings(
        self,
        mock_profile_repo: MagicMock,
        mock_settings_repo: MagicMock,
        client: TestClient,
    ) -> None:
        """Should return max_concurrent from server settings."""
        mock_settings_repo.get_server_settings = AsyncMock(
            return_value=_make_server_settings(max_concurrent=10)
        )

        response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert data["max_concurrent"] == 10
