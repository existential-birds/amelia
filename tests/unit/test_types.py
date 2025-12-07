"""Tests for core types."""

from amelia.core.types import ExecutionMode, Profile, RetryConfig


def test_execution_mode_literal_values():
    """ExecutionMode should accept 'structured' and 'agentic'."""
    mode1: ExecutionMode = "structured"
    mode2: ExecutionMode = "agentic"
    assert mode1 == "structured"
    assert mode2 == "agentic"


def test_profile_execution_mode_default():
    """Profile execution_mode should default to 'structured'."""
    profile = Profile(name="test", driver="cli:claude")
    assert profile.execution_mode == "structured"


def test_profile_execution_mode_agentic():
    """Profile should accept execution_mode='agentic'."""
    profile = Profile(name="test", driver="cli:claude", execution_mode="agentic")
    assert profile.execution_mode == "agentic"


def test_profile_working_dir_default():
    """Profile working_dir should default to None."""
    profile = Profile(name="test", driver="cli:claude")
    assert profile.working_dir is None


def test_profile_working_dir_custom():
    """Profile should accept custom working_dir."""
    profile = Profile(name="test", driver="cli:claude", working_dir="/custom/path")
    assert profile.working_dir == "/custom/path"


class TestProfileRetryConfig:
    """Test Profile.retry field."""

    def test_profile_has_default_retry_config(self):
        """Profile has default RetryConfig."""
        profile = Profile(name="test", driver="cli:claude")
        assert profile.retry.max_retries == 3
        assert profile.retry.base_delay == 1.0
        assert profile.retry.max_delay == 60.0

    def test_profile_accepts_custom_retry_config(self):
        """Profile accepts custom RetryConfig."""
        custom_retry = RetryConfig(max_retries=5, base_delay=2.0, max_delay=120.0)
        profile = Profile(name="test", driver="cli:claude", retry=custom_retry)
        assert profile.retry.max_retries == 5
        assert profile.retry.base_delay == 2.0
        assert profile.retry.max_delay == 120.0
