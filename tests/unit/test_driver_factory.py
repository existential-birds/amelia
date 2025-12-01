"""Tests for DriverFactory."""

import pytest

from amelia.drivers.api.openai import ApiDriver
from amelia.drivers.cli.agentic import ClaudeAgenticCliDriver
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.drivers.factory import DriverFactory


class TestDriverFactory:
    """Tests for DriverFactory."""

    def test_get_cli_claude_driver(self):
        driver = DriverFactory.get_driver("cli:claude")
        assert isinstance(driver, ClaudeCliDriver)

    def test_get_cli_claude_agentic_driver(self):
        driver = DriverFactory.get_driver("cli:claude:agentic")
        assert isinstance(driver, ClaudeAgenticCliDriver)

    def test_get_api_openai_driver(self):
        driver = DriverFactory.get_driver("api:openai")
        assert isinstance(driver, ApiDriver)

    def test_unknown_driver_raises(self):
        with pytest.raises(ValueError, match="Unknown driver key"):
            DriverFactory.get_driver("invalid:driver")
