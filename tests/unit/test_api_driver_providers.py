"""Tests for ApiDriver OpenRouter integration."""
import os
from unittest.mock import patch

import pytest
from pydantic_ai.models.openrouter import OpenRouterModel

from amelia.drivers.api.openai import ApiDriver


class TestApiDriverInit:
    """Test ApiDriver initialization."""

    def test_uses_provided_model(self):
        """Should use the provided model name."""
        driver = ApiDriver(model="anthropic/claude-sonnet-4-20250514")
        assert driver.model_name == "anthropic/claude-sonnet-4-20250514"

    def test_defaults_to_claude_sonnet(self):
        """Should default to Claude Sonnet when no model provided."""
        driver = ApiDriver()
        assert driver.model_name == ApiDriver.DEFAULT_MODEL


# Skip tests that require API key when not available (e.g., in CI)
requires_openrouter_key = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set - skipping tests that hit the API",
)


class TestBuildModel:
    """Test _build_model method."""

    @requires_openrouter_key
    def test_model_name_passed_correctly(self):
        """Should pass model name to OpenRouterModel."""
        driver = ApiDriver(model="google/gemini-pro")
        model = driver._build_model()
        assert isinstance(model, OpenRouterModel)
        assert model.model_name == "google/gemini-pro"

    @requires_openrouter_key
    def test_openrouter_model_uses_api_key(self):
        """Should configure OpenRouter provider with API key."""
        driver = ApiDriver(model="meta-llama/llama-3-70b")

        # Mock OpenRouterProvider to capture constructor args
        with patch("amelia.drivers.api.openai.OpenRouterProvider") as mock_provider_class:
            driver._build_model()

            # Verify OpenRouterProvider was constructed with API key
            mock_provider_class.assert_called_once()
            call_kwargs = mock_provider_class.call_args.kwargs
            assert "api_key" in call_kwargs
            # TODO: pydantic-ai OpenRouterProvider doesn't yet support app_url/app_title
            # Once supported, we should pass OPENROUTER_APP_URL and OPENROUTER_APP_TITLE
