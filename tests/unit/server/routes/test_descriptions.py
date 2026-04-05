"""Tests for descriptions condense endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.core.types import AgentConfig, Profile, TrackerType
from amelia.server.database import ProfileRepository
from amelia.server.dependencies import get_profile_repository
from amelia.server.routes.descriptions import router


@pytest.fixture
def mock_profile_repo() -> AsyncMock:
    return AsyncMock(spec=ProfileRepository)


@pytest.fixture
def app(mock_profile_repo: AsyncMock) -> FastAPI:
    application = FastAPI()
    application.include_router(router, prefix="/api")
    application.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def github_profile() -> Profile:
    return Profile(
        name="test",
        tracker=TrackerType.GITHUB,
        repo_root="/tmp/repo",
        agents={
            "architect": AgentConfig(driver="api", model="openai/gpt-4o"),
            "developer": AgentConfig(driver="api", model="openai/gpt-4o-mini"),
        },
    )


@pytest.fixture
def noop_profile() -> Profile:
    return Profile(
        name="noop-test",
        tracker=TrackerType.NOOP,
        repo_root="/tmp/repo",
        agents={
            "architect": AgentConfig(driver="api", model="openai/gpt-4o"),
        },
    )


def _mock_driver_and_condenser(condensed_text: str = "Condensed text here") -> MagicMock:
    """Create a mock driver for patching get_driver."""
    driver = MagicMock()
    driver.generate = AsyncMock(return_value=(condensed_text, MagicMock()))
    return driver


class TestCondenseDescription:
    def test_returns_condensed_text_for_github_profile(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
        github_profile: Profile,
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile

        with patch(
            "amelia.server.routes.descriptions.condense_description",
            new=AsyncMock(return_value=("Core task: fix the login bug", None)),
        ), patch(
            "amelia.server.routes.descriptions.get_driver",
            return_value=_mock_driver_and_condenser(),
        ):
            response = client.post(
                "/api/descriptions/condense",
                json={"description": "Long issue body with lots of text", "profile": "test"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["condensed"] == "Core task: fix the login bug"

    def test_returns_422_for_empty_description(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
        github_profile: Profile,
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile
        response = client.post(
            "/api/descriptions/condense",
            json={"description": "", "profile": "test"},
        )
        assert response.status_code == 422

    def test_returns_404_for_unknown_profile(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
    ) -> None:
        mock_profile_repo.get_profile.return_value = None
        response = client.post(
            "/api/descriptions/condense",
            json={"description": "Some text", "profile": "nonexistent"},
        )
        assert response.status_code == 404

    def test_returns_400_for_non_github_profile(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
        noop_profile: Profile,
    ) -> None:
        mock_profile_repo.get_profile.return_value = noop_profile
        response = client.post(
            "/api/descriptions/condense",
            json={"description": "Some text", "profile": "noop-test"},
        )
        assert response.status_code == 400
        assert "github" in response.json()["detail"].lower()

    def test_falls_back_to_active_profile_when_no_profile_given(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
        github_profile: Profile,
    ) -> None:
        mock_profile_repo.get_active_profile.return_value = github_profile

        with patch(
            "amelia.server.routes.descriptions.condense_description",
            new=AsyncMock(return_value=("Condensed from active profile", None)),
        ), patch(
            "amelia.server.routes.descriptions.get_driver",
            return_value=_mock_driver_and_condenser(),
        ):
            response = client.post(
                "/api/descriptions/condense",
                json={"description": "Long issue body"},
            )

        assert response.status_code == 200
        assert response.json()["condensed"] == "Condensed from active profile"

    def test_returns_400_when_no_active_profile(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
    ) -> None:
        mock_profile_repo.get_active_profile.return_value = None
        response = client.post(
            "/api/descriptions/condense",
            json={"description": "Long issue body"},
        )
        assert response.status_code == 400
        assert "active profile" in response.json()["detail"].lower()

    def test_returns_500_on_llm_failure(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
        github_profile: Profile,
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile

        with patch(
            "amelia.server.routes.descriptions.condense_description",
            new=AsyncMock(side_effect=RuntimeError("LLM unreachable")),
        ), patch(
            "amelia.server.routes.descriptions.get_driver",
            return_value=_mock_driver_and_condenser(),
        ):
            response = client.post(
                "/api/descriptions/condense",
                json={"description": "Some text", "profile": "test"},
            )

        assert response.status_code == 500
        assert "condense" in response.json()["detail"].lower()

    def test_uses_custom_agent_type_when_provided(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
        github_profile: Profile,
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile
        mock_driver = _mock_driver_and_condenser("Result")

        with patch(
            "amelia.server.routes.descriptions.condense_description",
            new=AsyncMock(return_value=("Result", None)),
        ) as mock_condense, patch(
            "amelia.server.routes.descriptions.get_driver",
            return_value=mock_driver,
        ) as mock_get_driver:
            response = client.post(
                "/api/descriptions/condense",
                json={"description": "Some text", "profile": "test", "agent_type": "developer"},
            )

        assert response.status_code == 200
        # Verify get_driver was called with developer agent's config
        mock_get_driver.assert_called_once_with("api", model="openai/gpt-4o-mini", cwd="/tmp/repo")
        mock_condense.assert_called_once()
