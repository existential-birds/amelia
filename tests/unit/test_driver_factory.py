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

    @pytest.mark.parametrize(
        "driver_key,expected_type,model,expected_model",
        [
            ("cli:claude", ClaudeCliDriver, None, None),
            ("cli", ClaudeCliDriver, None, None),
            ("api:openrouter", ApiDriver, "openrouter:anthropic/claude-3.5-sonnet", "openrouter:anthropic/claude-3.5-sonnet"),
            ("api:openai", ApiDriver, "openai:gpt-4o", "openai:gpt-4o"),
            ("api", ApiDriver, None, None),
        ],
    )
    def test_get_driver(self, driver_key, expected_type, model, expected_model) -> None:
        """Factory should return correct driver type for various driver keys."""
        driver = DriverFactory.get_driver(driver_key, model=model)
        assert isinstance(driver, expected_type)
        if expected_model is not None:
            assert driver.model_name == expected_model

    @pytest.mark.parametrize(
        "driver_key,error_match",
        [
            ("invalid:driver", "Unknown driver key"),
        ],
    )
    def test_invalid_driver_raises(self, driver_key, error_match) -> None:
        """Factory should raise ValueError for unknown drivers."""
        with pytest.raises(ValueError, match=error_match):
            DriverFactory.get_driver(driver_key)
