"""Tests for tracker factory configuration."""

from unittest.mock import MagicMock, patch

from amelia.core.types import Profile
from amelia.trackers.factory import create_tracker


def test_tracker_factory_creates_noop_tracker():
    """Factory creates NoopTracker for noop tracker type."""
    profile = Profile(
        name="test",
        driver="cli:claude",
        model="sonnet",
        tracker="noop",
        strategy="single",
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
            driver="cli:claude",
            model="sonnet",
            tracker="github",
            strategy="single",
        )
        tracker = create_tracker(profile)
        assert tracker is not None
        assert hasattr(tracker, "get_issue")


def test_tracker_factory_creates_none_tracker():
    """Factory creates NoopTracker for 'none' tracker type (alias for noop)."""
    profile = Profile(
        name="test",
        driver="cli:claude",
        model="sonnet",
        tracker="none",
        strategy="single",
    )
    tracker = create_tracker(profile)
    assert tracker is not None
    assert hasattr(tracker, "get_issue")
