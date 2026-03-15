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

# --- Shared constants ---

_DEFAULT_TIMESTAMP = datetime(2024, 1, 1, 12, 0, 0)

_REQUIRED_AGENTS = (
    "architect", "developer", "reviewer",
    "task_reviewer", "evaluator", "brainstormer", "plan_validator",
)


def _full_agents_json(
    driver: str = "claude", model: str = "opus", **overrides: dict,
) -> dict[str, dict[str, str]]:
    """Build a complete agents JSON dict for API requests."""
    base = {name: {"driver": driver, "model": model} for name in _REQUIRED_AGENTS}
    base.update(overrides)
    return base


def _make_server_settings(**overrides) -> ServerSettings:
    """Build ServerSettings with defaults."""
    defaults = dict(
        log_retention_days=30,
        checkpoint_retention_days=0,
        websocket_idle_timeout_seconds=300.0,
        workflow_start_timeout_seconds=60.0,
        max_concurrent=5,
        created_at=_DEFAULT_TIMESTAMP,
        updated_at=_DEFAULT_TIMESTAMP,
    )
    defaults.update(overrides)
    return ServerSettings(**defaults)


def make_test_profile(
    name: str = "test-profile",
    tracker: TrackerType = TrackerType.NOOP,
    repo_root: str = "/path/to/repo",
    driver: DriverType = DriverType.CLAUDE,
    model: str = "opus",
    **extra_profile_kwargs,
) -> Profile:
    """Create a Profile for testing with agents dict."""
    agent_config = AgentConfig(driver=driver, model=model)
    agents = {a: agent_config for a in _REQUIRED_AGENTS}
    return Profile(
        name=name, tracker=tracker, repo_root=repo_root, agents=agents,
        **extra_profile_kwargs,
    )


# --- Fixtures ---

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
            pr_polling_enabled=False,
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
            pr_polling_enabled=False,
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


# --- Settings tests ---

class TestSettingsRoutes:
    """Tests for /api/settings endpoints."""

    def test_get_server_settings(self, client: TestClient, mock_repo: MagicMock) -> None:
        """GET /api/settings returns current settings."""
        mock_repo.get_server_settings.return_value = _make_server_settings()

        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["log_retention_days"] == 30
        assert data["max_concurrent"] == 5

    def test_update_server_settings(self, client: TestClient, mock_repo: MagicMock) -> None:
        """PUT /api/settings updates settings."""
        mock_repo.update_server_settings.return_value = _make_server_settings(
            log_retention_days=60, max_concurrent=10,
        )

        response = client.put(
            "/api/settings",
            json={"log_retention_days": 60, "max_concurrent": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["log_retention_days"] == 60
        assert data["max_concurrent"] == 10


# --- Profile tests ---

class TestProfileRoutes:
    """Tests for /api/profiles endpoints."""

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
        assert data[0]["is_active"] is True
        assert "agents" in data[0]
        assert data[1]["id"] == "prod"
        assert data[1]["is_active"] is False
        assert data[1]["agents"]["developer"]["driver"] == "api"

    def test_list_profiles_empty(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """GET /api/profiles returns empty list when no profiles."""
        mock_profile_repo.list_profiles.return_value = []

        response = profile_client.get("/api/profiles")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_profile(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """POST /api/profiles creates new profile."""
        mock_profile_repo.create_profile.return_value = make_test_profile(name="new-profile")

        response = profile_client.post(
            "/api/profiles",
            json={
                "id": "new-profile",
                "repo_root": "/path/to/repo",
                "agents": _full_agents_json(reviewer={"driver": "claude", "model": "haiku"}),
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "new-profile"
        assert "agents" in data

    def test_create_profile_with_all_fields(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """POST /api/profiles creates profile with all optional fields."""
        mock_profile_repo.create_profile.return_value = Profile(
            name="full-profile",
            tracker=TrackerType.JIRA,
            repo_root="/custom/path",
            plan_output_dir="custom/plans",
            plan_path_pattern="custom/{date}.md",
            agents={"developer": AgentConfig(driver=DriverType.API, model="gpt-4")},
        )

        response = profile_client.post(
            "/api/profiles",
            json={
                "id": "full-profile",
                "tracker": "jira",
                "repo_root": "/custom/path",
                "plan_output_dir": "custom/plans",
                "plan_path_pattern": "custom/{date}.md",
                "agents": _full_agents_json(driver="api", model="gpt-4"),
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
            name="dev", tracker=TrackerType.GITHUB,
        )

        response = profile_client.put("/api/profiles/dev", json={"tracker": "github"})
        assert response.status_code == 200
        assert response.json()["tracker"] == "github"

    def test_update_profile_with_agents(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """PUT /api/profiles/{id} updates agents configuration."""
        mock_profile_repo.update_profile.return_value = Profile(
            name="dev", tracker=TrackerType.NOOP, repo_root="/new/path",
            agents={"developer": AgentConfig(driver=DriverType.API, model="gpt-4")},
        )

        response = profile_client.put(
            "/api/profiles/dev",
            json={"tracker": "jira", "agents": _full_agents_json(driver="api", model="gpt-4")},
        )
        assert response.status_code == 200
        assert response.json()["agents"]["developer"]["driver"] == "api"

    def test_update_profile_not_found(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """PUT /api/profiles/{id} returns 404 for missing profile."""
        mock_profile_repo.update_profile.side_effect = ValueError("Profile nonexistent not found")

        response = profile_client.put("/api/profiles/nonexistent", json={"tracker": "github"})
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.parametrize(
        ("delete_rv", "expected_status"),
        [(True, 204), (False, 404)],
        ids=["success", "not-found"],
    )
    def test_delete_profile(
        self, profile_client: TestClient, mock_profile_repo: MagicMock,
        delete_rv: bool, expected_status: int,
    ) -> None:
        """DELETE /api/profiles/{id} returns correct status."""
        mock_profile_repo.delete_profile.return_value = delete_rv
        name = "dev" if delete_rv else "nonexistent"

        response = profile_client.delete(f"/api/profiles/{name}")
        assert response.status_code == expected_status
        if expected_status == 404:
            assert response.json()["detail"] == "Profile not found"

    def test_activate_profile(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """POST /api/profiles/{id}/activate sets profile as active."""
        mock_profile_repo.get_profile.return_value = make_test_profile(name="dev")

        response = profile_client.post("/api/profiles/dev/activate")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "dev"
        assert data["is_active"] is True
        mock_profile_repo.set_active.assert_called_once_with("dev")

    def test_activate_profile_not_found(self, profile_client: TestClient, mock_profile_repo: MagicMock) -> None:
        """POST /api/profiles/{id}/activate returns 404 for missing profile."""
        mock_profile_repo.set_active.side_effect = ValueError("Profile nonexistent not found")

        response = profile_client.post("/api/profiles/nonexistent/activate")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.parametrize(
        ("method", "url", "json_body", "error_substr"),
        [
            ("post", "/api/profiles", {
                "id": "bad", "repo_root": "/path/to/repo",
                "agents": {"architect": {"driver": "claude", "model": "opus"},
                           "developer": {"driver": "claude", "model": "opus"},
                           "reviewer": {"driver": "claude", "model": "opus"}},
            }, "Missing required agents"),
            ("put", "/api/profiles/dev", {
                "agents": {"developer": {"driver": "api", "model": "gpt-4"}},
            }, "Missing required agents"),
            ("post", "/api/profiles", {
                "id": "bad", "repo_root": "relative/path",
                "agents": _full_agents_json(),
            }, "repo_root must be an absolute path"),
            ("put", "/api/profiles/dev", {
                "repo_root": "./relative",
            }, "repo_root must be an absolute path"),
        ],
        ids=[
            "create-missing-agents",
            "update-missing-agents",
            "create-relative-repo-root",
            "update-relative-repo-root",
        ],
    )
    def test_validation_returns_422(
        self, profile_client: TestClient, mock_profile_repo: MagicMock,
        method: str, url: str, json_body: dict, error_substr: str,
    ) -> None:
        """Validation errors return 422 with correct message."""
        response = getattr(profile_client, method)(url, json=json_body)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any(error_substr in str(e) for e in detail)

    def test_create_profile_extra_agents_accepted(
        self, profile_client: TestClient, mock_profile_repo: MagicMock,
    ) -> None:
        """POST /api/profiles with extra agents is accepted."""
        mock_profile_repo.create_profile.return_value = make_test_profile(name="extra-profile")

        agents = _full_agents_json()
        agents["custom_agent"] = {"driver": "claude", "model": "opus"}
        response = profile_client.post(
            "/api/profiles",
            json={"id": "extra-profile", "repo_root": "/path/to/repo", "agents": agents},
        )
        assert response.status_code == 201

    def test_update_profile_pr_autofix_explicit_null_clears_config(
        self, profile_client: TestClient, mock_profile_repo: MagicMock
    ) -> None:
        """PUT with pr_autofix=null passes None to repository (clears config)."""
        mock_profile_repo.update_profile.return_value = make_test_profile(name="dev")

        response = profile_client.put(
            "/api/profiles/dev",
            json={"pr_autofix": None},
        )
        assert response.status_code == 200

        # Verify the repository received pr_autofix: None in update_dict
        call_args = mock_profile_repo.update_profile.call_args
        update_dict = call_args[0][1]  # second positional arg
        assert "pr_autofix" in update_dict
        assert update_dict["pr_autofix"] is None

    def test_update_profile_pr_autofix_omitted_preserves_existing(
        self, profile_client: TestClient, mock_profile_repo: MagicMock
    ) -> None:
        """PUT without pr_autofix field does NOT include it in update_dict (preserves existing)."""
        mock_profile_repo.update_profile.return_value = make_test_profile(name="dev")

        response = profile_client.put(
            "/api/profiles/dev",
            json={"tracker": "github"},
        )
        assert response.status_code == 200

        # Verify the repository did NOT receive pr_autofix key
        call_args = mock_profile_repo.update_profile.call_args
        update_dict = call_args[0][1]
        assert "pr_autofix" not in update_dict

    def test_update_profile_pr_autofix_with_config_passes_dict(
        self, profile_client: TestClient, mock_profile_repo: MagicMock
    ) -> None:
        """PUT with pr_autofix config passes serialized dict to repository."""
        mock_profile_repo.update_profile.return_value = make_test_profile(name="dev")

        response = profile_client.put(
            "/api/profiles/dev",
            json={"pr_autofix": {"aggressiveness": "standard"}},
        )
        assert response.status_code == 200

        # Verify the repository received the serialized config dict
        call_args = mock_profile_repo.update_profile.call_args
        update_dict = call_args[0][1]
        assert "pr_autofix" in update_dict
        assert isinstance(update_dict["pr_autofix"], dict)
        assert update_dict["pr_autofix"]["aggressiveness"] == "standard"
