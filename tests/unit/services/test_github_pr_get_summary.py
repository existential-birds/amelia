"""Tests for GitHubPRService.get_pr_summary."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from amelia.core.types import PRSummary
from amelia.services.github_pr import GitHubPRService


@pytest.fixture
def service() -> GitHubPRService:
    return GitHubPRService(repo_root="/tmp/test-repo")


class TestGetPRSummary:
    async def test_returns_pr_summary_for_valid_pr(self, service: GitHubPRService) -> None:
        """get_pr_summary returns PRSummary with correct fields."""
        mock_output = json.dumps({
            "number": 42,
            "title": "Fix login bug",
            "headRefName": "fix/login-bug",
            "author": {"login": "alice"},
            "updatedAt": "2026-03-01T10:00:00Z",
        })
        with patch.object(service, "_run_gh", new_callable=AsyncMock, return_value=mock_output):
            result = await service.get_pr_summary(42)

        assert isinstance(result, PRSummary)
        assert result.number == 42
        assert result.title == "Fix login bug"
        assert result.head_branch == "fix/login-bug"
        assert result.author == "alice"

    async def test_calls_gh_with_correct_args(self, service: GitHubPRService) -> None:
        """get_pr_summary calls gh pr view with the right JSON fields."""
        mock_output = json.dumps({
            "number": 7,
            "title": "Test",
            "headRefName": "test-branch",
            "author": {"login": "bob"},
            "updatedAt": "2026-03-01T10:00:00Z",
        })
        with patch.object(service, "_run_gh", new_callable=AsyncMock, return_value=mock_output) as mock_run:
            await service.get_pr_summary(7)

        mock_run.assert_awaited_once_with(
            "pr", "view", "7",
            "--json", "number,title,headRefName,author,updatedAt",
        )

    async def test_raises_value_error_on_failure(self, service: GitHubPRService) -> None:
        """get_pr_summary raises ValueError when gh CLI fails."""
        with patch.object(
            service, "_run_gh", new_callable=AsyncMock,
            side_effect=ValueError("gh command failed: no pull requests found"),
        ), pytest.raises(ValueError, match="no pull requests found"):
            await service.get_pr_summary(999)
