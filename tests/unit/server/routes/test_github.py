"""Tests for GitHub issues endpoint."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.core.types import Profile, TrackerType
from amelia.server.database import ProfileRepository
from amelia.server.dependencies import get_profile_repository
from amelia.server.routes.github import router


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


def _make_mock_process(returncode: int = 0, stdout: str = "", stderr: str = "") -> AsyncMock:
    """Create a mock async subprocess with the given outputs."""
    mock_proc = AsyncMock()
    mock_proc.returncode = returncode
    mock_proc.communicate.return_value = (stdout.encode(), stderr.encode())
    return mock_proc


class TestListGitHubIssues:
    def test_returns_issues_for_github_profile(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
        github_profile: Profile,
        mock_gh_output: str,
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile
        with patch(
            "amelia.server.routes.github.asyncio.create_subprocess_exec",
            return_value=_make_mock_process(returncode=0, stdout=mock_gh_output),
        ):
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
        self, client: TestClient, mock_profile_repo: AsyncMock, noop_profile: Profile
    ) -> None:
        mock_profile_repo.get_profile.return_value = noop_profile
        response = client.get("/api/github/issues?profile=test")

        assert response.status_code == 400
        assert "github" in response.json()["detail"].lower()

    def test_returns_404_for_unknown_profile(
        self, client: TestClient, mock_profile_repo: AsyncMock
    ) -> None:
        mock_profile_repo.get_profile.return_value = None
        response = client.get("/api/github/issues?profile=nonexistent")

        assert response.status_code == 404

    def test_passes_search_to_gh_cli(
        self, client: TestClient, mock_profile_repo: AsyncMock, github_profile: Profile
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile
        with patch(
            "amelia.server.routes.github.asyncio.create_subprocess_exec",
            return_value=_make_mock_process(returncode=0, stdout="[]"),
        ) as mock_exec:
            client.get("/api/github/issues?profile=test&search=login")

        args = mock_exec.call_args[0]
        assert "--search" in args
        assert "login" in args

    def test_returns_500_on_gh_cli_failure(
        self, client: TestClient, mock_profile_repo: AsyncMock, github_profile: Profile
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile
        with patch(
            "amelia.server.routes.github.asyncio.create_subprocess_exec",
            return_value=_make_mock_process(returncode=1, stderr="auth required"),
        ):
            response = client.get("/api/github/issues?profile=test")

        assert response.status_code == 500

    def test_profile_param_required(self, client: TestClient) -> None:
        response = client.get("/api/github/issues")
        assert response.status_code == 422
