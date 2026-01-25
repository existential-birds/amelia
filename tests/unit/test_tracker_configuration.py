"""Tests for tracker factory configuration."""

from unittest.mock import MagicMock, patch

from amelia.core.types import AgentConfig, Profile
from amelia.trackers.factory import create_tracker


def test_tracker_factory_creates_noop_tracker():
    """Factory creates NoopTracker for none tracker type."""
    profile = Profile(
        name="test",
        tracker="none",
        working_dir="/tmp/test",
        agents={
            "architect": AgentConfig(driver="cli", model="sonnet"),
            "developer": AgentConfig(driver="cli", model="sonnet"),
            "reviewer": AgentConfig(driver="cli", model="sonnet"),
        },
    )
    tracker = create_tracker(profile)
    assert tracker is not None
    assert hasattr(tracker, "get_issue")


def test_tracker_factory_creates_github_tracker():
    """Factory creates GithubTracker for github tracker type."""
    # Mock gh auth status to avoid requiring real GitHub authentication
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        profile = Profile(
            name="test",
            tracker="github",
            working_dir="/tmp/test",
            agents={
                "architect": AgentConfig(driver="cli", model="sonnet"),
                "developer": AgentConfig(driver="cli", model="sonnet"),
                "reviewer": AgentConfig(driver="cli", model="sonnet"),
            },
        )
        tracker = create_tracker(profile)
        assert tracker is not None
        assert hasattr(tracker, "get_issue")


def test_tracker_factory_creates_none_tracker():
    """Factory creates NoopTracker for 'none' tracker type (alias for noop)."""
    profile = Profile(
        name="test",
        tracker="none",
        working_dir="/tmp/test",
        agents={
            "architect": AgentConfig(driver="cli", model="sonnet"),
            "developer": AgentConfig(driver="cli", model="sonnet"),
            "reviewer": AgentConfig(driver="cli", model="sonnet"),
        },
    )
    tracker = create_tracker(profile)
    assert tracker is not None
    assert hasattr(tracker, "get_issue")
