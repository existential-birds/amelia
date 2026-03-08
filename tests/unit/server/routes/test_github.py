"""Tests for GitHub issues endpoint."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.core.types import Profile, TrackerType
from amelia.server.routes.github import router


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    application.include_router(router, prefix="/api")
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def github_profile() -> Profile:
    return Profile(name="test", tracker=TrackerType.GITHUB, repo_root="/tmp/repo")


@pytest.fixture
def noop_profile() -> Profile:
    return Profile(name="test", tracker=TrackerType.NOOP, repo_root="/tmp/repo")


@pytest.fixture
def mock_gh_output() -> str:
    return json.dumps([
        {
            "number": 42,
            "title": "Fix login bug",
            "labels": [{"name": "bug", "color": "d73a4a"}],
            "assignees": [{"login": "alice"}],
            "createdAt": "2026-03-01T10:00:00Z",
            "state": "OPEN",
        },
        {
            "number": 17,
            "title": "Add dark mode",
            "labels": [],
            "assignees": [],
            "createdAt": "2026-02-15T08:00:00Z",
            "state": "OPEN",
        },
    ])


class TestListGitHubIssues:
    def test_returns_issues_for_github_profile(
        self, client: TestClient, github_profile: Profile, mock_gh_output: str
    ) -> None:
        with (
            patch(
                "amelia.server.routes.github._get_profile",
                new_callable=AsyncMock,
                return_value=github_profile,
            ),
            patch("amelia.server.routes.github.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=0, stdout=mock_gh_output, stderr=""
            )
            response = client.get("/api/github/issues?profile=test")

        assert response.status_code == 200
        data = response.json()
        assert len(data["issues"]) == 2
        assert data["issues"][0]["number"] == 42
        assert data["issues"][0]["title"] == "Fix login bug"
        assert data["issues"][0]["labels"] == [{"name": "bug", "color": "d73a4a"}]
        assert data["issues"][0]["assignee"] == "alice"
        assert data["issues"][1]["assignee"] is None

    def test_returns_400_for_non_github_profile(
        self, client: TestClient, noop_profile: Profile
    ) -> None:
        with patch(
            "amelia.server.routes.github._get_profile",
            new_callable=AsyncMock,
            return_value=noop_profile,
        ):
            response = client.get("/api/github/issues?profile=test")

        assert response.status_code == 400
        assert "github" in response.json()["detail"].lower()

    def test_returns_404_for_unknown_profile(self, client: TestClient) -> None:
        with patch(
            "amelia.server.routes.github._get_profile",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.get("/api/github/issues?profile=nonexistent")

        assert response.status_code == 404

    def test_passes_search_to_gh_cli(
        self, client: TestClient, github_profile: Profile
    ) -> None:
        with (
            patch(
                "amelia.server.routes.github._get_profile",
                new_callable=AsyncMock,
                return_value=github_profile,
            ),
            patch("amelia.server.routes.github.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=0, stdout="[]", stderr=""
            )
            client.get("/api/github/issues?profile=test&search=login")

        cmd = mock_run.call_args[0][0]
        assert "--search" in cmd
        assert "login" in cmd

    def test_returns_500_on_gh_cli_failure(
        self, client: TestClient, github_profile: Profile
    ) -> None:
        with (
            patch(
                "amelia.server.routes.github._get_profile",
                new_callable=AsyncMock,
                return_value=github_profile,
            ),
            patch("amelia.server.routes.github.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="auth required"
            )
            response = client.get("/api/github/issues?profile=test")

        assert response.status_code == 500

    def test_profile_param_required(self, client: TestClient) -> None:
        response = client.get("/api/github/issues")
        assert response.status_code == 422
