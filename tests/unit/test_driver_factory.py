"""Tests for DriverFactory."""

import pytest

from amelia.drivers.api.deepagents import ApiDriver
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.drivers.factory import DriverFactory, cleanup_driver_session


class TestDriverFactory:
    """Tests for DriverFactory."""

    @pytest.mark.parametrize(
        "driver_key,expected_type,model,expected_model",
        [
            ("cli", ClaudeCliDriver, None, None),
            ("cli", ClaudeCliDriver, None, None),
            ("api", ApiDriver, "anthropic/claude-sonnet-4-20250514", "anthropic/claude-sonnet-4-20250514"),
            ("api", ApiDriver, None, None),
        ],
    )
    def test_get_driver(self, driver_key, expected_type, model, expected_model):
        """Factory should return correct driver type for various driver keys."""
        driver = DriverFactory.get_driver(driver_key, model=model)
        assert isinstance(driver, expected_type)
        if expected_model is not None:
            assert driver.model == expected_model

    @pytest.mark.parametrize(
        "driver_key,error_match",
        [
            ("invalid:driver", "Unknown driver key"),
            ("api:openai", "Unknown driver key"),
        ],
    )
    def test_invalid_driver_raises(self, driver_key, error_match):
        """Factory should raise ValueError for unknown or unsupported drivers."""
        with pytest.raises(ValueError, match=error_match):
            DriverFactory.get_driver(driver_key)


class TestDriverInterfaceProtocol:
    """Test DriverInterface protocol includes execute_agentic."""

    def test_claude_cli_driver_implements_protocol(self) -> None:
        """ClaudeCliDriver should implement DriverInterface including execute_agentic."""
        driver = ClaudeCliDriver()
        # Should have execute_agentic that returns AsyncIterator[AgenticMessage]
        assert hasattr(driver, "execute_agentic")
        assert hasattr(driver, "generate")

    def test_api_driver_implements_protocol(self) -> None:
        """ApiDriver should implement DriverInterface including execute_agentic."""
        driver = ApiDriver(cwd="/tmp")
        assert hasattr(driver, "execute_agentic")
        assert hasattr(driver, "generate")


class TestDriverFactoryProviderPassing:
    """Tests for factory passing provider to ApiDriver."""

    def test_api_openrouter_passes_provider(self) -> None:
        """Factory should pass provider='openrouter' to ApiDriver for api."""
        driver = DriverFactory.get_driver("api")
        assert isinstance(driver, ApiDriver)
        assert driver.provider == "openrouter"

    def test_api_shorthand_passes_provider(self) -> None:
        """Factory should pass provider='openrouter' to ApiDriver for 'api' shorthand."""
        driver = DriverFactory.get_driver("api")
        assert isinstance(driver, ApiDriver)
        assert driver.provider == "openrouter"


class TestDriverCleanupSession:
    """Test cleanup_session protocol method."""

    def test_claude_cli_driver_cleanup_returns_false(self) -> None:
        """ClaudeCliDriver cleanup_session should return False (no state to clean)."""
        driver = ClaudeCliDriver()
        result = driver.cleanup_session("any-session-id")
        assert result is False

    def test_api_driver_cleanup_removes_session(self) -> None:
        """ApiDriver cleanup_session should remove session from cache."""
        # Directly add a session to the class-level cache
        test_session_id = "test-cleanup-session-123"
        from langgraph.checkpoint.memory import MemorySaver

        try:
            ApiDriver._sessions[test_session_id] = MemorySaver()

            driver = ApiDriver(cwd="/tmp")
            result = driver.cleanup_session(test_session_id)

            assert result is True
            assert test_session_id not in ApiDriver._sessions
        finally:
            ApiDriver._sessions.pop(test_session_id, None)

    def test_api_driver_cleanup_returns_false_for_unknown(self) -> None:
        """ApiDriver cleanup_session should return False for unknown session."""
        driver = ApiDriver(cwd="/tmp")
        result = driver.cleanup_session("nonexistent-session-id")
        assert result is False


class TestCleanupDriverSession:
    """Test factory-level cleanup_driver_session function."""

    def test_cleanup_api_driver_session(self) -> None:
        """Should clean up ApiDriver session via factory function."""
        from langgraph.checkpoint.memory import MemorySaver

        test_session_id = "factory-cleanup-test-123"
        try:
            ApiDriver._sessions[test_session_id] = MemorySaver()

            result = cleanup_driver_session("api", test_session_id)

            assert result is True
            assert test_session_id not in ApiDriver._sessions
        finally:
            ApiDriver._sessions.pop(test_session_id, None)

    def test_cleanup_cli_driver_session_returns_false(self) -> None:
        """Should return False for CLI driver (no state)."""
        result = cleanup_driver_session("cli", "any-session")
        assert result is False

    def test_cleanup_unknown_driver_raises(self) -> None:
        """Should raise ValueError for unknown driver."""
        with pytest.raises(ValueError, match="Unknown driver key"):
            cleanup_driver_session("invalid:driver", "any-session")