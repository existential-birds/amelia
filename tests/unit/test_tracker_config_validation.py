# tests/unit/test_tracker_config_validation.py
"""Tests for tracker configuration validation."""

from unittest.mock import MagicMock, patch

import pytest

from amelia.core.exceptions import ConfigurationError
from amelia.trackers.github import GithubTracker
from amelia.trackers.jira import JiraTracker
from amelia.trackers.noop import NoopTracker


class TestJiraTrackerConfigValidation:
    """Test JiraTracker configuration validation."""

    @pytest.mark.parametrize(
        "missing_var,present_vars",
        [
            (
                "JIRA_BASE_URL",
                {"JIRA_EMAIL": "test@example.com", "JIRA_API_TOKEN": "token123"},
            ),
            (
                "JIRA_EMAIL",
                {"JIRA_BASE_URL": "https://example.atlassian.net", "JIRA_API_TOKEN": "token123"},
            ),
            (
                "JIRA_API_TOKEN",
                {"JIRA_BASE_URL": "https://example.atlassian.net", "JIRA_EMAIL": "test@example.com"},
            ),
        ],
        ids=["missing_url", "missing_email", "missing_token"]
    )
    def test_missing_jira_env_var_raises_config_error(
        self, monkeypatch, missing_var, present_vars
    ):
        """Missing JIRA environment variables should raise ConfigurationError."""
        monkeypatch.delenv(missing_var, raising=False)
        for key, value in present_vars.items():
            monkeypatch.setenv(key, value)

        with pytest.raises(ConfigurationError, match=missing_var):
            JiraTracker()

    def test_all_jira_vars_present_succeeds(self, monkeypatch):
        """With all env vars set, JiraTracker should initialize."""
        monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "token123")

        tracker = JiraTracker()
        assert tracker is not None


class TestGithubTrackerConfigValidation:
    """Test GithubTracker configuration validation."""

    def test_gh_cli_not_installed_raises_config_error(self):
        """Missing gh CLI should raise ConfigurationError."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("gh not found")

            with pytest.raises(ConfigurationError, match="gh.*not found"):
                GithubTracker()

    def test_gh_cli_not_authenticated_raises_config_error(self):
        """Unauthenticated gh CLI should raise ConfigurationError."""
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "You are not logged into any GitHub hosts"
            mock_run.return_value = mock_result

            with pytest.raises(ConfigurationError, match="not authenticated"):
                GithubTracker()

    def test_gh_cli_authenticated_succeeds(self):
        """Authenticated gh CLI should allow initialization."""
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "Logged in to github.com as user"
            mock_run.return_value = mock_result

            tracker = GithubTracker()
            assert tracker is not None


class TestGithubTrackerGetIssue:
    """Test GithubTracker issue fetching behavior."""

    def test_get_issue_passes_cwd_to_subprocess(self):
        """GithubTracker.get_issue should pass cwd to subprocess.run.

        This ensures gh CLI runs in the correct directory to determine
        which repository to query (based on git remote).
        """
        with patch("subprocess.run") as mock_run:
            # First call is auth validation in __init__
            mock_auth_result = MagicMock()
            mock_auth_result.returncode = 0
            mock_auth_result.stdout = "Logged in to github.com as user"

            # Second call is the actual issue fetch
            mock_issue_result = MagicMock()
            mock_issue_result.returncode = 0
            mock_issue_result.stdout = '{"title": "Test Issue", "body": "Description", "state": "open"}'

            mock_run.side_effect = [mock_auth_result, mock_issue_result]

            tracker = GithubTracker()
            issue = tracker.get_issue("123", cwd="/some/worktree/path")

            # Verify subprocess.run was called with cwd parameter
            issue_fetch_call = mock_run.call_args_list[1]
            assert issue_fetch_call.kwargs.get("cwd") == "/some/worktree/path"
            assert issue.id == "123"
            assert issue.title == "Test Issue"


class TestNoopTracker:
    """Test NoopTracker behavior."""

    def test_get_issue_returns_placeholder(self):
        """NoopTracker should return placeholder issue for any ID."""
        tracker = NoopTracker()
        issue = tracker.get_issue("ANY-123")
        assert issue.id == "ANY-123"
        assert issue.title == "Placeholder Issue"
        assert issue.description == "Tracker not configured"

    def test_get_issue_accepts_cwd_parameter(self):
        """NoopTracker should accept cwd parameter (ignored)."""
        tracker = NoopTracker()
        issue = tracker.get_issue("ANY-123", cwd="/some/path")
        assert issue.id == "ANY-123"
