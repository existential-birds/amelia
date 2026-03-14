"""Tests for PR comment poller service."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import (
    PRAutoFixConfig,
    PRSummary,
    Profile,
)
from amelia.server.models.events import EventType, _WARNING_TYPES


# ---------------------------------------------------------------------------
# Shared fixtures (reused by Task 2 tests)
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_profile_repo() -> AsyncMock:
    """Mock ProfileRepository with list_profiles."""
    repo = AsyncMock()
    repo.list_profiles = AsyncMock(return_value=[])
    return repo


@pytest.fixture()
def mock_settings_repo() -> AsyncMock:
    """Mock SettingsRepository with get_server_settings."""
    repo = AsyncMock()
    settings = MagicMock()
    settings.pr_polling_enabled = True
    repo.get_server_settings = AsyncMock(return_value=settings)
    return repo


@pytest.fixture()
def mock_orchestrator() -> AsyncMock:
    """Mock PRAutoFixOrchestrator with trigger_fix_cycle."""
    orch = AsyncMock()
    orch.trigger_fix_cycle = AsyncMock()
    return orch


@pytest.fixture()
def mock_event_bus() -> MagicMock:
    """Mock EventBus with emit."""
    bus = MagicMock()
    bus.emit = MagicMock()
    return bus


@pytest.fixture()
def sample_profile() -> Profile:
    """Profile with pr_autofix enabled."""
    return Profile(
        name="test-profile",
        repo_root="/tmp/test-repo",
        pr_autofix=PRAutoFixConfig(poll_label="amelia"),
    )


@pytest.fixture()
def sample_profile_no_autofix() -> Profile:
    """Profile with pr_autofix disabled."""
    return Profile(
        name="no-autofix",
        repo_root="/tmp/test-repo",
    )


# ---------------------------------------------------------------------------
# Task 1: Config extensions
# ---------------------------------------------------------------------------


class TestPRAutoFixConfigPollLabel:
    """Tests for poll_label field on PRAutoFixConfig."""

    def test_default_poll_label(self) -> None:
        config = PRAutoFixConfig()
        assert config.poll_label == "amelia"

    def test_custom_poll_label(self) -> None:
        config = PRAutoFixConfig(poll_label="custom-label")
        assert config.poll_label == "custom-label"


class TestEventTypePollRateLimited:
    """Tests for PR_POLL_RATE_LIMITED event type."""

    def test_event_type_exists(self) -> None:
        assert EventType.PR_POLL_RATE_LIMITED == "pr_poll_rate_limited"

    def test_event_type_in_warning_types(self) -> None:
        assert EventType.PR_POLL_RATE_LIMITED in _WARNING_TYPES


class TestListLabeledPRs:
    """Tests for GitHubPRService.list_labeled_prs."""

    async def test_list_labeled_prs_returns_pr_summaries(self) -> None:
        from amelia.services.github_pr import GitHubPRService

        service = GitHubPRService("/tmp/test-repo")
        pr_data = [
            {
                "number": 42,
                "title": "Fix stuff",
                "headRefName": "fix/stuff",
                "author": {"login": "alice"},
                "updatedAt": "2026-03-14T10:00:00Z",
            },
        ]
        with patch.object(service, "_run_gh", new_callable=AsyncMock) as mock_gh:
            mock_gh.return_value = json.dumps(pr_data)
            result = await service.list_labeled_prs("amelia")

        assert len(result) == 1
        assert isinstance(result[0], PRSummary)
        assert result[0].number == 42
        assert result[0].head_branch == "fix/stuff"
        mock_gh.assert_called_once_with(
            "pr", "list",
            "--json", "number,title,headRefName,author,updatedAt",
            "--state", "open",
            "--label", "amelia",
            "--limit", "100",
        )

    async def test_list_labeled_prs_empty_result(self) -> None:
        from amelia.services.github_pr import GitHubPRService

        service = GitHubPRService("/tmp/test-repo")
        with patch.object(service, "_run_gh", new_callable=AsyncMock) as mock_gh:
            mock_gh.return_value = json.dumps([])
            result = await service.list_labeled_prs("amelia")

        assert result == []
