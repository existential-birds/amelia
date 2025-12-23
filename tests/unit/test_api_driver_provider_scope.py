# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for ApiDriver provider scope - verifies provider extraction from model strings."""
import pytest

from amelia.drivers.api.openai import ApiDriver


@pytest.mark.parametrize(
    "model,expected_provider",
    [
        pytest.param("openai:gpt-4o", "openai", id="openai_gpt4o"),
        pytest.param("openai:gpt-4o-mini", "openai", id="openai_gpt4o_mini"),
        pytest.param("openrouter:anthropic/claude-3.5-sonnet", "openrouter", id="openrouter_claude"),
        pytest.param("openrouter:openai/gpt-4o", "openrouter", id="openrouter_openai"),
        pytest.param("anthropic:claude-3", "anthropic", id="anthropic_claude"),
        pytest.param("gemini:pro", "gemini", id="gemini_pro"),
        pytest.param("gpt-4o", "openai", id="no_prefix_defaults_to_openai"),
    ],
)
def test_api_driver_provider_extraction(model: str, expected_provider: str) -> None:
    """Verifies ApiDriver correctly extracts provider from model string.

    Provider validation is delegated to pydantic-ai at runtime (when Agent() is created).
    ApiDriver.__init__ only extracts the provider name for reference.
    """
    driver = ApiDriver(model=model)
    assert driver._provider == expected_provider
    assert driver.model_name == model
