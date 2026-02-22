# tests/unit/server/routes/test_settings_routes.py
"""Tests for settings API routes."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.core.types import AgentConfig, DriverType, Profile, TrackerType
from amelia.server.database import ServerSettings
from amelia.server.dependencies import get_profile_repository, get_settings_repository
from amelia.server.routes.settings import router


@pytest.fixture
def mock_repo() -> MagicMock:
    """Create mock settings repository."""
    repo = MagicMock()
    repo.get_server_settings = AsyncMock()
    repo.update_server_settings = AsyncMock()
    return repo


@pytest.fixture
def app(mock_repo: MagicMock) -> FastAPI:
    """Create test FastAPI app with settings router."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings_repository] = lambda: mock_repo
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestSettingsRoutes:
    """Tests for /api/settings endpoints."""

    def test_get_server_settings(self, client: TestClient, mock_repo: MagicMock) -> None:
        """GET /api/settings returns current settings."""
        mock_settings = ServerSettings(
            log_retention_days=30,
            checkpoint_retention_days=0,
            websocket_idle_timeout_seconds=300.0,
            workflow_start_timeout_seconds=60.0,
            max_concurrent=5,
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            updated_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        mock_repo.get_server_settings.return_value = mock_settings

        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["log_retention_days"] == 30
        assert data["max_concurrent"] == 5

    def test_update_server_settings(self, client: TestClient, mock_repo: MagicMock) -> None:
        """PUT /api/settings updates settings."""
        # Return updated settings
        mock_repo.update_server_settings.return_value = ServerSettings(
            log_retention_days=60,
            checkpoint_retention_days=0,
            websocket_idle_timeout_seconds=300.0,
            workflow_start_timeout_seconds=60.0,
            max_concurrent=10,
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            updated_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        response = client.put(
            "/api/settings",
            json={"log_retention_days": 60, "max_concurrent": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["log_retention_days"] == 60
        assert data["max_concurrent"] == 10


@pytest.fixture
def mock_profile_repo() -> MagicMock:
    """Create mock profile repository."""
    repo = MagicMock()
    repo.list_profiles = AsyncMock()
    repo.create_profile = AsyncMock()
    repo.get_profile = AsyncMock()
    repo.get_active_profile = AsyncMock(return_value=None)
    repo.update_profile = AsyncMock()
    repo.delete_profile = AsyncMock()
    repo.set_active = AsyncMock()
    return repo


@pytest.fixture
def profile_app(mock_repo: MagicMock, mock_profile_repo: MagicMock) -> FastAPI:
    """Create test FastAPI app with both settings and profile dependencies."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings_repository] = lambda: mock_repo
    app.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo
    return app


@pytest.fixture
def profile_client(profile_app: FastAPI) -> TestClient:
    """Create test client for profile endpoints."""
    return TestClient(profile_app)


def make_test_profile(
    name: str = "test-profile",
    tracker: TrackerType = TrackerType.NOOP,
    repo_root: str = "/path/to/repo",
    driver: DriverType = DriverType.CLAUDE,
    model: str = "opus",
) -> Profile:
    """Create a Profile for testing with agents dict.

    Args:
        name: Profile name.
        tracker: Tracker type.
        repo_root: Repository root directory.
        driver: Default driver for all agents.
        model: Default model for all agents.

    Returns:
        Profile with default agents configuration.
    """
    agent_config = AgentConfig(driver=driver, model=model)
    agents = {
        "architect": agent_config,
        "developer": agent_config,
        "reviewer": agent_config,
        "task_reviewer": agent_config,
        "evaluator": agent_config,
        "brainstormer": agent_config,
        "plan_validator": agent_config,
    }
    return Profile(
        name=name,
        tracker=tracker,
        repo_root=repo_root,
        agents=agents,
    )


class TestProfileRoutes:
    """Tests for /api/profiles endpoints.

    Note: With per-agent configuration, the API now returns agents dict
    instead of flat driver/model fields.
    """

    def test_list_profiles(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """GET /api/profiles returns all profiles with correct is_active."""
        dev_profile = make_test_profile(name="dev")
        prod_profile = make_test_profile(name="prod", driver=DriverType.API)
        mock_profile_repo.list_profiles.return_value = [dev_profile, prod_profile]
        mock_profile_repo.get_active_profile.return_value = dev_profile

        response = profile_client.get("/api/profiles")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == "dev"
        assert data[0]["is_active"] is True  # dev is active
        assert "agents" in data[0]
        assert data[1]["id"] == "prod"
        assert data[1]["is_active"] is False  # prod is not active
        # With agents dict, check agent configuration
        assert data[1]["agents"]["developer"]["driver"] == "api"

    def test_list_profiles_empty(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """GET /api/profiles returns empty list when no profiles."""
        mock_profile_repo.list_profiles.return_value = []

        response = profile_client.get("/api/profiles")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_profile(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """POST /api/profiles creates new profile."""
        mock_profile_repo.create_profile.return_value = make_test_profile(
            name="new-profile"
        )

        response = profile_client.post(
            "/api/profiles",
            json={
                "id": "new-profile",
                "repo_root": "/path/to/repo",
                "agents": {
                    "architect": {"driver": "claude", "model": "opus"},
                    "developer": {"driver": "claude", "model": "opus"},
                    "reviewer": {"driver": "claude", "model": "haiku"},
                    "task_reviewer": {"driver": "claude", "model": "opus"},
                    "evaluator": {"driver": "claude", "model": "opus"},
                    "brainstormer": {"driver": "claude", "model": "opus"},
                    "plan_validator": {"driver": "claude", "model": "opus"},
                },
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "new-profile"
        assert "agents" in data

    def test_create_profile_with_all_fields(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """POST /api/profiles creates profile with all optional fields."""
        tracker: TrackerType = TrackerType.JIRA
        driver: DriverType = DriverType.API
        mock_profile_repo.create_profile.return_value = Profile(
            name="full-profile",
            tracker=tracker,
            repo_root="/custom/path",
            plan_output_dir="custom/plans",
            plan_path_pattern="custom/{date}.md",
            agents={
                "developer": AgentConfig(driver=driver, model="gpt-4"),
            },
        )

        response = profile_client.post(
            "/api/profiles",
            json={
                "id": "full-profile",
                "tracker": "jira",
                "repo_root": "/custom/path",
                "plan_output_dir": "custom/plans",
                "plan_path_pattern": "custom/{date}.md",
                "agents": {
                    "architect": {"driver": "api", "model": "gpt-4"},
                    "developer": {"driver": "api", "model": "gpt-4"},
                    "reviewer": {"driver": "api", "model": "gpt-4"},
                    "task_reviewer": {"driver": "api", "model": "gpt-4"},
                    "evaluator": {"driver": "api", "model": "gpt-4"},
                    "brainstormer": {"driver": "api", "model": "gpt-4"},
                    "plan_validator": {"driver": "api", "model": "gpt-4"},
                },
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["tracker"] == "jira"
        assert data["plan_output_dir"] == "custom/plans"

    def test_get_profile(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """GET /api/profiles/{id} returns profile."""
        mock_profile_repo.get_profile.return_value = make_test_profile(name="dev")

        response = profile_client.get("/api/profiles/dev")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "dev"
        assert "agents" in data

    def test_get_profile_not_found(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """GET /api/profiles/{id} returns 404 for missing profile."""
        mock_profile_repo.get_profile.return_value = None

        response = profile_client.get("/api/profiles/nonexistent")
        assert response.status_code == 404
        assert response.json()["detail"] == "Profile not found"

    def test_update_profile(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """PUT /api/profiles/{id} updates profile."""
        mock_profile_repo.update_profile.return_value = make_test_profile(
            name="dev", tracker=TrackerType.GITHUB
        )

        response = profile_client.put(
            "/api/profiles/dev",
            json={"tracker": "github"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tracker"] == "github"

    def test_update_profile_with_agents(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """PUT /api/profiles/{id} updates agents configuration."""
        tracker: TrackerType = TrackerType.NOOP
        driver: DriverType = DriverType.API
        mock_profile_repo.update_profile.return_value = Profile(
            name="dev",
            tracker=tracker,
            repo_root="/new/path",
            agents={
                "developer": AgentConfig(driver=driver, model="gpt-4"),
            },
        )

        response = profile_client.put(
            "/api/profiles/dev",
            json={
                "tracker": "jira",
                "agents": {
                    "architect": {"driver": "api", "model": "gpt-4"},
                    "developer": {"driver": "api", "model": "gpt-4"},
                    "reviewer": {"driver": "api", "model": "gpt-4"},
                    "task_reviewer": {"driver": "api", "model": "gpt-4"},
                    "evaluator": {"driver": "api", "model": "gpt-4"},
                    "brainstormer": {"driver": "api", "model": "gpt-4"},
                    "plan_validator": {"driver": "api", "model": "gpt-4"},
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["agents"]["developer"]["driver"] == "api"

    def test_update_profile_not_found(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """PUT /api/profiles/{id} returns 404 for missing profile."""
        mock_profile_repo.update_profile.side_effect = ValueError(
            "Profile nonexistent not found"
        )

        response = profile_client.put(
            "/api/profiles/nonexistent",
            json={"tracker": "github"},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_profile(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """DELETE /api/profiles/{id} deletes profile."""
        mock_profile_repo.delete_profile.return_value = True

        response = profile_client.delete("/api/profiles/dev")
        assert response.status_code == 204

    def test_delete_profile_not_found(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """DELETE /api/profiles/{id} returns 404 for missing profile."""
        mock_profile_repo.delete_profile.return_value = False

        response = profile_client.delete("/api/profiles/nonexistent")
        assert response.status_code == 404
        assert response.json()["detail"] == "Profile not found"

    def test_activate_profile(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """POST /api/profiles/{id}/activate sets profile as active."""
        mock_profile_repo.get_profile.return_value = make_test_profile(name="dev")

        response = profile_client.post("/api/profiles/dev/activate")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "dev"
        assert data["is_active"] is True  # Verify is_active is True after activation
        mock_profile_repo.set_active.assert_called_once_with("dev")

    def test_activate_profile_not_found(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """POST /api/profiles/{id}/activate returns 404 for missing profile."""
        mock_profile_repo.set_active.side_effect = ValueError(
            "Profile nonexistent not found"
        )

        response = profile_client.post("/api/profiles/nonexistent/activate")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_profile_missing_agents_returns_422(
        self, profile_client: TestClient, mock_profile_repo: MagicMock
    ) -> None:
        """POST /api/profiles with missing agents returns 422."""
        response = profile_client.post(
            "/api/profiles",
            json={
                "id": "bad-profile",
                "repo_root": "/path/to/repo",
                "agents": {
                    "architect": {"driver": "claude", "model": "opus"},
                    "developer": {"driver": "claude", "model": "opus"},
                    "reviewer": {"driver": "claude", "model": "opus"},
                },
            },
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any("Missing required agents" in str(e) for e in detail)

    def test_update_profile_missing_agents_returns_422(
        self, profile_client: TestClient, mock_profile_repo: MagicMock
    ) -> None:
        """PUT /api/profiles/{id} with partial agents returns 422."""
        response = profile_client.put(
            "/api/profiles/dev",
            json={
                "agents": {
                    "developer": {"driver": "api", "model": "gpt-4"},
                },
            },
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any("Missing required agents" in str(e) for e in detail)

    def test_create_profile_relative_repo_root_returns_422(
        self, profile_client: TestClient, mock_profile_repo: MagicMock
    ) -> None:
        """POST /api/profiles with relative repo_root returns 422."""
        response = profile_client.post(
            "/api/profiles",
            json={
                "id": "bad-profile",
                "repo_root": "relative/path",
                "agents": {
                    "architect": {"driver": "claude", "model": "opus"},
                    "developer": {"driver": "claude", "model": "opus"},
                    "reviewer": {"driver": "claude", "model": "opus"},
                    "task_reviewer": {"driver": "claude", "model": "opus"},
                    "evaluator": {"driver": "claude", "model": "opus"},
                    "brainstormer": {"driver": "claude", "model": "opus"},
                    "plan_validator": {"driver": "claude", "model": "opus"},
                },
            },
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any("repo_root must be an absolute path" in str(e) for e in detail)

    def test_update_profile_relative_repo_root_returns_422(
        self, profile_client: TestClient, mock_profile_repo: MagicMock
    ) -> None:
        """PUT /api/profiles/{id} with relative repo_root returns 422."""
        response = profile_client.put(
            "/api/profiles/dev",
            json={"repo_root": "./relative"},
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any("repo_root must be an absolute path" in str(e) for e in detail)

    def test_create_profile_extra_agents_accepted(
        self, profile_client: TestClient, mock_profile_repo: MagicMock
    ) -> None:
        """POST /api/profiles with extra agents is accepted."""
        mock_profile_repo.create_profile.return_value = make_test_profile(
            name="extra-profile"
        )

        response = profile_client.post(
            "/api/profiles",
            json={
                "id": "extra-profile",
                "repo_root": "/path/to/repo",
                "agents": {
                    "architect": {"driver": "claude", "model": "opus"},
                    "developer": {"driver": "claude", "model": "opus"},
                    "reviewer": {"driver": "claude", "model": "opus"},
                    "task_reviewer": {"driver": "claude", "model": "opus"},
                    "evaluator": {"driver": "claude", "model": "opus"},
                    "brainstormer": {"driver": "claude", "model": "opus"},
                    "plan_validator": {"driver": "claude", "model": "opus"},
                    "custom_agent": {"driver": "claude", "model": "opus"},
                },
            },
        )
        assert response.status_code == 201
