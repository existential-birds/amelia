# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for DriverFactory."""

import pytest

from amelia.drivers.api.openai import ApiDriver
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.drivers.factory import DriverFactory


class TestDriverFactory:
    """Tests for DriverFactory."""

    def test_get_cli_claude_driver(self):
        driver = DriverFactory.get_driver("cli:claude")
        assert isinstance(driver, ClaudeCliDriver)

    def test_get_api_openai_driver(self):
        driver = DriverFactory.get_driver("api:openai")
        assert isinstance(driver, ApiDriver)

    def test_get_api_openrouter_driver(self):
        """Factory should return ApiDriver for api:openrouter."""
        driver = DriverFactory.get_driver("api:openrouter", model="openrouter:anthropic/claude-3.5-sonnet")
        assert isinstance(driver, ApiDriver)

    def test_unknown_driver_raises(self):
        with pytest.raises(ValueError, match="Unknown driver key"):
            DriverFactory.get_driver("invalid:driver")
