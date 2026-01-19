"""Tests for config routes."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.dependencies import get_config
from amelia.server.routes.config import _load_settings, router


class TestGetConfig:
    """Tests for GET /api/config endpoint."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create a mock config with default values."""
        config = MagicMock()
        config.working_dir = Path("/tmp")
        config.max_concurrent = 5
        return config

    @pytest.fixture
    def client(self, mock_config: MagicMock) -> TestClient:
        """Create a test client with mock config dependency."""
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_config] = lambda: mock_config
        return TestClient(app)

    def test_returns_config_with_working_dir(
        self, mock_config: MagicMock, client: TestClient
    ) -> None:
        """Should return working_dir when set."""
        mock_config.working_dir = Path("/tmp/test-repo")

        response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert data["working_dir"] == "/tmp/test-repo"
        assert data["max_concurrent"] == 5

    def test_returns_working_dir_as_cwd_by_default(
        self, mock_config: MagicMock, client: TestClient
    ) -> None:
        """Should return current working directory when using default config."""
        mock_config.working_dir = Path.cwd()

        response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert data["working_dir"] == str(Path.cwd())
        assert data["max_concurrent"] == 5

    def test_returns_active_profile_from_settings(self, client: TestClient) -> None:
        """Should return active_profile from settings.amelia.yaml."""
        with patch("amelia.server.routes.config._load_settings") as mock_load:
            mock_load.return_value = {"active_profile": "test", "profiles": {}}
            response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert data["active_profile"] == "test"
        assert data["active_profile_info"] is None

    def test_returns_active_profile_info_when_profile_exists(
        self, client: TestClient
    ) -> None:
        """Should return full profile info when profile exists."""
        with patch("amelia.server.routes.config._load_settings") as mock_load:
            mock_load.return_value = {
                "active_profile": "test",
                "profiles": {
                    "test": {
                        "driver": "api:openrouter",
                        "model": "claude-3-5-sonnet",
                    }
                },
            }
            response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert data["active_profile"] == "test"
        assert data["active_profile_info"] == {
            "name": "test",
            "driver": "api:openrouter",
            "model": "claude-3-5-sonnet",
        }


class TestLoadSettings:
    """Tests for _load_settings helper function."""

    def test_returns_settings_from_yaml(self) -> None:
        """Should return settings dict from YAML file."""
        with patch("amelia.server.routes.config.Path") as mock_path:
            mock_file = MagicMock()
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_path.return_value.open.return_value = mock_file
            mock_path.return_value.exists.return_value = True

            with patch("amelia.server.routes.config.yaml.safe_load") as mock_yaml:
                mock_yaml.return_value = {
                    "active_profile": "production",
                    "profiles": {"production": {"driver": "cli:claude", "model": "sonnet"}},
                }
                result = _load_settings()

        assert result["active_profile"] == "production"
        assert "profiles" in result

    def test_returns_empty_dict_when_file_not_found(self) -> None:
        """Should return empty dict when settings file does not exist."""
        with patch("amelia.server.routes.config.Path") as mock_path:
            mock_path.return_value.open.side_effect = FileNotFoundError()

            result = _load_settings()

        assert result == {}

    def test_returns_empty_dict_when_yaml_error(self) -> None:
        """Should return empty dict on YAML parse error."""
        import yaml

        with patch("amelia.server.routes.config.Path") as mock_path:
            mock_file = MagicMock()
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_path.return_value.open.return_value = mock_file

            with patch("amelia.server.routes.config.yaml.safe_load") as mock_yaml:
                mock_yaml.side_effect = yaml.YAMLError("Parse error")
                result = _load_settings()

        assert result == {}
