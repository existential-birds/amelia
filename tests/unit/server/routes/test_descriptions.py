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


def _make_mock_driver(condensed_text: str = "Condensed text here") -> MagicMock:
    """Create a mock driver whose generate method returns a condensed string."""
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
        mock_driver = _make_mock_driver("Core task: fix the login bug")

        with patch(
            "amelia.server.routes.descriptions.get_driver",
            return_value=mock_driver,
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
        mock_driver = _make_mock_driver("Condensed from active profile")

        with patch(
            "amelia.server.routes.descriptions.get_driver",
            return_value=mock_driver,
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
        mock_driver = MagicMock()
        mock_driver.generate = AsyncMock(side_effect=RuntimeError("LLM unreachable"))

        with patch(
            "amelia.server.routes.descriptions.get_driver",
            return_value=mock_driver,
        ):
            response = client.post(
                "/api/descriptions/condense",
                json={"description": "Some text", "profile": "test"},
            )

        assert response.status_code == 500
        assert "condense" in response.json()["detail"].lower()
