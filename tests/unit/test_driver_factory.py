# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for DriverFactory."""

import pytest

from amelia.drivers.api.deepagents import ApiDriver
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
