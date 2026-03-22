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
from amelia.pipelines.pr_auto_fix.orchestrator import PRAutoFixOrchestrator
from amelia.server.database import WorkflowRepository
from amelia.server.dependencies import get_profile_repository, get_repository
from amelia.server.events.bus import EventBus
from amelia.server.routes.github import router
from amelia.services.github_pr import GitHubPRService


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def app(mock_profile_repo: MagicMock, event_bus: EventBus) -> FastAPI:
    application = FastAPI()
    application.include_router(router, prefix="/api")
    application.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo
    mock_workflow_repo = MagicMock(spec=WorkflowRepository)
    mock_workflow_repo.create = AsyncMock()
    mock_workflow_repo.update = AsyncMock()
    application.dependency_overrides[get_repository] = lambda: mock_workflow_repo
    application.state.event_bus = event_bus
    application.state.pr_autofix_orchestrator = PRAutoFixOrchestrator(
        event_bus=event_bus,
        github_pr_service=GitHubPRService("."),
        workflow_repo=mock_workflow_repo,
    )
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
        mock_profile_repo: MagicMock,
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

    def test_returns_400_for_non_github_profile(
        self,
        client: TestClient,
        mock_profile_repo: MagicMock,
    ) -> None:
        noop_profile = Profile(name="noop", tracker=TrackerType.NOOP, repo_root="/tmp/repo")
        mock_profile_repo.get_profile.return_value = noop_profile
        response = client.get("/api/github/prs?profile=noop")
        assert response.status_code == 400


class TestGetPRComments:
    def test_returns_comments_for_pr(
        self,
        client: TestClient,
        mock_profile_repo: MagicMock,
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


class TestPRAutoFixConfig:
    def test_returns_enabled_when_pr_autofix_set(
        self,
        client: TestClient,
        mock_profile_repo: MagicMock,
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
        mock_profile_repo: MagicMock,
        github_profile_no_autofix: Profile,
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile_no_autofix
        response = client.get("/api/github/prs/config?profile=no_autofix")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["config"] is None


@pytest.mark.parametrize(
    "path,method",
    [
        pytest.param("/api/github/prs?profile=unknown", "get", id="list-prs"),
        pytest.param("/api/github/prs/42/comments?profile=unknown", "get", id="pr-comments"),
        pytest.param("/api/github/prs/config?profile=unknown", "get", id="pr-config"),
        pytest.param("/api/github/prs/42/auto-fix?profile=unknown", "post", id="trigger-autofix"),
    ],
)
def test_returns_404_for_unknown_profile(
    client: TestClient,
    mock_profile_repo: MagicMock,
    path: str,
    method: str,
) -> None:
    """All PR endpoints return 404 when profile is not found."""
    mock_profile_repo.get_profile.return_value = None
    response = getattr(client, method)(path)
    assert response.status_code == 404


class TestTriggerPRAutoFix:
    @staticmethod
    def _make_pr_summary(**overrides) -> PRSummary:
        defaults = dict(
            number=42,
            title="Fix bug",
            head_branch="fix/bug",
            author="alice",
            updated_at="2026-03-01T10:00:00Z",
        )
        return PRSummary(**(defaults | overrides))

    @staticmethod
    def _trigger_autofix_with_mocks(client, app, profile_repo, profile, *, pr_summary=None, body=None):
        profile_repo.get_profile.return_value = profile
        if pr_summary is None:
            pr_summary = TestTriggerPRAutoFix._make_pr_summary()

        mock_orch = MagicMock()
        mock_orch.get_workflow_id.return_value = UUID("12345678-1234-5678-1234-567812345678")
        mock_orch.trigger_fix_cycle = AsyncMock()
        app.state.pr_autofix_orchestrator = mock_orch

        with (
            patch("amelia.server.routes.github.GitHubPRService") as MockService,
            patch("amelia.server.routes.github._get_repo_name", new_callable=AsyncMock, return_value="owner/repo"),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_pr_summary.return_value = pr_summary
            MockService.return_value = mock_svc

            response = client.post("/api/github/prs/42/auto-fix?profile=test", json=body)
        return response, mock_orch

    def test_returns_202_with_workflow_id(
        self,
        client: TestClient,
        app: FastAPI,
        mock_profile_repo: MagicMock,
        github_profile: Profile,
    ) -> None:
        response, _ = self._trigger_autofix_with_mocks(client, app, mock_profile_repo, github_profile)

        assert response.status_code == 202
        data = response.json()
        assert data["workflow_id"] == str(UUID("12345678-1234-5678-1234-567812345678"))
        assert "message" in data

    def test_returns_400_when_pr_autofix_none(
        self,
        client: TestClient,
        mock_profile_repo: MagicMock,
        github_profile_no_autofix: Profile,
    ) -> None:
        mock_profile_repo.get_profile.return_value = github_profile_no_autofix
        response = client.post("/api/github/prs/42/auto-fix?profile=no_autofix")

        assert response.status_code == 400
        assert "pr_autofix" in response.json()["detail"].lower()

    def test_aggressiveness_override(
        self,
        client: TestClient,
        app: FastAPI,
        mock_profile_repo: MagicMock,
        github_profile: Profile,
    ) -> None:
        response, mock_orch = self._trigger_autofix_with_mocks(
            client, app, mock_profile_repo, github_profile, body={"aggressiveness": "thorough"},
        )

        assert response.status_code == 202
        # Verify the config override was passed to trigger_fix_cycle
        call_kwargs = mock_orch.trigger_fix_cycle.call_args.kwargs
        assert call_kwargs["config"].aggressiveness == AggressivenessLevel.THOROUGH

    def test_fetches_head_branch_before_triggering(
        self,
        client: TestClient,
        app: FastAPI,
        mock_profile_repo: MagicMock,
        github_profile: Profile,
    ) -> None:
        pr_summary = self._make_pr_summary(head_branch="feat/my-branch")
        _, mock_orch = self._trigger_autofix_with_mocks(
            client, app, mock_profile_repo, github_profile, pr_summary=pr_summary,
        )

        # Verify head_branch was fetched from PR summary and passed to orchestrator
        call_kwargs = mock_orch.trigger_fix_cycle.call_args.kwargs
        assert call_kwargs["head_branch"] == "feat/my-branch"

    def test_forwards_pr_title_to_orchestrator(
        self,
        client: TestClient,
        app: FastAPI,
        mock_profile_repo: MagicMock,
        github_profile: Profile,
    ) -> None:
        pr_summary = self._make_pr_summary(title="Fix login bug")
        _, mock_orch = self._trigger_autofix_with_mocks(
            client, app, mock_profile_repo, github_profile, pr_summary=pr_summary,
        )

        call_kwargs = mock_orch.trigger_fix_cycle.call_args.kwargs
        assert call_kwargs["pr_title"] == "Fix login bug"
