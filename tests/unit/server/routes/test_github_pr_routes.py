"""Tests for GitHub PR API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.core.types import (
    AggressivenessLevel,
    PRAutoFixConfig,
    Profile,
    PRReviewComment,
    PRSummary,
    TrackerType,
)
from amelia.server.database import ProfileRepository, WorkflowRepository
from amelia.server.dependencies import get_profile_repository, get_repository
from amelia.server.events.bus import EventBus
from amelia.server.routes.github import router


@pytest.fixture
def mock_profile_repo() -> AsyncMock:
    return AsyncMock(spec=ProfileRepository)


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def app(mock_profile_repo: AsyncMock, event_bus: EventBus) -> FastAPI:
    application = FastAPI()
    application.include_router(router, prefix="/api")
    application.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo
    mock_workflow_repo = MagicMock(spec=WorkflowRepository)
    mock_workflow_repo.create = AsyncMock()
    mock_workflow_repo.update = AsyncMock()
    application.dependency_overrides[get_repository] = lambda: mock_workflow_repo
    application.state.event_bus = event_bus
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
        pr_autofix=PRAutoFixConfig(),
    )


@pytest.fixture
def github_profile_no_autofix() -> Profile:
    return Profile(
        name="no_autofix",
        tracker=TrackerType.GITHUB,
        repo_root="/tmp/repo",
        pr_autofix=None,
    )


@pytest.fixture
def mock_pr_summaries() -> list[PRSummary]:
    return [
        PRSummary(
            number=42,
            title="Fix login bug",
            head_branch="fix/login-bug",
            author="alice",
            updated_at="2026-03-01T10:00:00Z",
        ),
        PRSummary(
            number=17,
            title="Add dark mode",
            head_branch="feat/dark-mode",
            author="bob",
            updated_at="2026-02-15T08:00:00Z",
        ),
    ]


@pytest.fixture
def mock_pr_comments() -> list[PRReviewComment]:
    return [
        PRReviewComment(
            id=101,
            body="Please use snake_case here",
            author="reviewer1",
            created_at="2026-03-01T12:00:00Z",
            path="src/main.py",
            line=42,
            pr_number=42,
        ),
    ]


class TestListPRs:
    def test_returns_prs_for_github_profile(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
        github_profile: Profile,
        mock_pr_summaries: list[PRSummary],
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile
        with patch(
            "amelia.server.routes.github.GitHubPRService",
        ) as MockService:
            mock_svc = AsyncMock()
            mock_svc.list_open_prs.return_value = mock_pr_summaries
            MockService.return_value = mock_svc

            response = client.get("/api/github/prs?profile=test")

        assert response.status_code == 200
        data = response.json()
        assert len(data["prs"]) == 2
        assert data["prs"][0]["number"] == 42
        assert data["prs"][0]["head_branch"] == "fix/login-bug"

    def test_returns_404_for_unknown_profile(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
    ) -> None:
        mock_profile_repo.get_profile.return_value = None
        response = client.get("/api/github/prs?profile=unknown")
        assert response.status_code == 404

    def test_returns_400_for_non_github_profile(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
    ) -> None:
        noop_profile = Profile(name="noop", tracker=TrackerType.NOOP, repo_root="/tmp/repo")
        mock_profile_repo.get_profile.return_value = noop_profile
        response = client.get("/api/github/prs?profile=noop")
        assert response.status_code == 400


class TestGetPRComments:
    def test_returns_comments_for_pr(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
        github_profile: Profile,
        mock_pr_comments: list[PRReviewComment],
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile
        with patch(
            "amelia.server.routes.github.GitHubPRService",
        ) as MockService:
            mock_svc = AsyncMock()
            mock_svc.fetch_review_comments.return_value = mock_pr_comments
            MockService.return_value = mock_svc

            response = client.get("/api/github/prs/42/comments?profile=test")

        assert response.status_code == 200
        data = response.json()
        assert len(data["comments"]) == 1
        assert data["comments"][0]["body"] == "Please use snake_case here"

    def test_returns_404_for_unknown_profile(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
    ) -> None:
        mock_profile_repo.get_profile.return_value = None
        response = client.get("/api/github/prs/42/comments?profile=unknown")
        assert response.status_code == 404


class TestPRAutoFixConfig:
    def test_returns_enabled_when_pr_autofix_set(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
        github_profile: Profile,
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile
        response = client.get("/api/github/prs/config?profile=test")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["config"] is not None
        assert data["config"]["aggressiveness"] == "standard"

    def test_returns_disabled_when_pr_autofix_none(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
        github_profile_no_autofix: Profile,
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile_no_autofix
        response = client.get("/api/github/prs/config?profile=no_autofix")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["config"] is None

    def test_returns_404_for_unknown_profile(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
    ) -> None:
        mock_profile_repo.get_profile.return_value = None
        response = client.get("/api/github/prs/config?profile=unknown")
        assert response.status_code == 404


class TestTriggerPRAutoFix:
    def test_returns_202_with_workflow_id(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
        github_profile: Profile,
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile
        mock_pr_summary = PRSummary(
            number=42,
            title="Fix bug",
            head_branch="fix/bug",
            author="alice",
            updated_at="2026-03-01T10:00:00Z",
        )
        with (
            patch("amelia.server.routes.github.GitHubPRService") as MockService,
            patch("amelia.server.routes.github.PRAutoFixOrchestrator") as MockOrch,
            patch("amelia.server.routes.github._get_repo_name", new_callable=AsyncMock, return_value="owner/repo"),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_pr_summary.return_value = mock_pr_summary
            MockService.return_value = mock_svc

            mock_orch = MagicMock()
            test_uuid = UUID("12345678-1234-5678-1234-567812345678")
            mock_orch._get_workflow_id.return_value = test_uuid
            mock_orch.trigger_fix_cycle = AsyncMock()
            MockOrch.return_value = mock_orch

            response = client.post("/api/github/prs/42/auto-fix?profile=test")

        assert response.status_code == 202
        data = response.json()
        assert data["workflow_id"] == str(test_uuid)
        assert "message" in data

    def test_returns_400_when_pr_autofix_none(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
        github_profile_no_autofix: Profile,
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile_no_autofix
        response = client.post("/api/github/prs/42/auto-fix?profile=no_autofix")

        assert response.status_code == 400
        assert "pr_autofix" in response.json()["detail"].lower()

    def test_returns_404_for_unknown_profile(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
    ) -> None:
        mock_profile_repo.get_profile.return_value = None
        response = client.post("/api/github/prs/42/auto-fix?profile=unknown")
        assert response.status_code == 404

    def test_aggressiveness_override(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
        github_profile: Profile,
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile
        mock_pr_summary = PRSummary(
            number=42,
            title="Fix bug",
            head_branch="fix/bug",
            author="alice",
            updated_at="2026-03-01T10:00:00Z",
        )
        with (
            patch("amelia.server.routes.github.GitHubPRService") as MockService,
            patch("amelia.server.routes.github.PRAutoFixOrchestrator") as MockOrch,
            patch("amelia.server.routes.github._get_repo_name", new_callable=AsyncMock, return_value="owner/repo"),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_pr_summary.return_value = mock_pr_summary
            MockService.return_value = mock_svc

            mock_orch = MagicMock()
            mock_orch._get_workflow_id.return_value = UUID("12345678-1234-5678-1234-567812345678")
            mock_orch.trigger_fix_cycle = AsyncMock()
            MockOrch.return_value = mock_orch

            response = client.post(
                "/api/github/prs/42/auto-fix?profile=test",
                json={"aggressiveness": "thorough"},
            )

        assert response.status_code == 202
        # Verify the config override was passed to trigger_fix_cycle
        call_kwargs = mock_orch.trigger_fix_cycle.call_args.kwargs
        assert call_kwargs["config"].aggressiveness == AggressivenessLevel.THOROUGH

    def test_fetches_head_branch_before_triggering(
        self,
        client: TestClient,
        mock_profile_repo: AsyncMock,
        github_profile: Profile,
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile
        mock_pr_summary = PRSummary(
            number=42,
            title="Fix bug",
            head_branch="feat/my-branch",
            author="alice",
            updated_at="2026-03-01T10:00:00Z",
        )
        with (
            patch("amelia.server.routes.github.GitHubPRService") as MockService,
            patch("amelia.server.routes.github.PRAutoFixOrchestrator") as MockOrch,
            patch("amelia.server.routes.github._get_repo_name", new_callable=AsyncMock, return_value="owner/repo"),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_pr_summary.return_value = mock_pr_summary
            MockService.return_value = mock_svc

            mock_orch = MagicMock()
            mock_orch._get_workflow_id.return_value = UUID("12345678-1234-5678-1234-567812345678")
            mock_orch.trigger_fix_cycle = AsyncMock()
            MockOrch.return_value = mock_orch

            client.post("/api/github/prs/42/auto-fix?profile=test")

        # Verify head_branch was fetched from PR summary and passed to orchestrator
        call_kwargs = mock_orch.trigger_fix_cycle.call_args.kwargs
        assert call_kwargs["head_branch"] == "feat/my-branch"
