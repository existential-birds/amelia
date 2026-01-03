"""Tests for DriverFactory."""

import inspect

import pytest

from amelia.drivers.api.deepagents import ApiDriver
from amelia.drivers.base import DriverInterface
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.drivers.factory import DriverFactory


class TestDriverFactory:
    """Tests for DriverFactory."""

    @pytest.mark.parametrize(
        "driver_key,expected_type,model,expected_model",
        [
            ("cli:claude", ClaudeCliDriver, None, None),
            ("cli", ClaudeCliDriver, None, None),
            ("api:openrouter", ApiDriver, "openrouter:anthropic/claude-sonnet-4-20250514", "openrouter:anthropic/claude-sonnet-4-20250514"),
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

    def test_protocol_has_execute_agentic_method(self) -> None:
        """DriverInterface should define execute_agentic method."""
        assert hasattr(DriverInterface, "execute_agentic")
        method = DriverInterface.execute_agentic
        sig = inspect.signature(method)
        # Should have prompt, cwd, session_id, instructions, schema params
        assert "prompt" in sig.parameters
        assert "cwd" in sig.parameters

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
