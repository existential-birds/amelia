"""Tests for ApiDriver provider validation and OpenRouter integration."""
import os
from unittest.mock import patch

import pytest
from pydantic_ai.models.openrouter import OpenRouterModel

from amelia.drivers.api.openai import ApiDriver


class TestProviderValidation:
    """Test provider validation in ApiDriver."""

    def test_accepts_openai_model(self):
        """Should accept openai: prefixed models."""
        driver = ApiDriver(model="openai:gpt-4o")
        assert driver.model_name == "openai:gpt-4o"
        assert driver._provider == "openai"

    def test_accepts_openrouter_model(self):
        """Should accept openrouter: prefixed models."""
        driver = ApiDriver(model="openrouter:anthropic/claude-3.5-sonnet")
        assert driver.model_name == "openrouter:anthropic/claude-3.5-sonnet"
        assert driver._provider == "openrouter"

    def test_rejects_unsupported_provider(self):
        """Should reject unsupported providers."""
        with pytest.raises(ValueError, match="Unsupported provider"):
            ApiDriver(model="gemini:pro")


class TestApiKeyValidation:
    """Test API key validation per provider."""

    def test_openai_requires_openai_api_key(self, monkeypatch):
        """OpenAI provider should require OPENAI_API_KEY."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        driver = ApiDriver(model="openai:gpt-4o")
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            driver._validate_api_key()

    def test_openrouter_requires_openrouter_api_key(self, monkeypatch):
        """OpenRouter provider should require OPENROUTER_API_KEY."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        driver = ApiDriver(model="openrouter:anthropic/claude-3.5-sonnet")
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            driver._validate_api_key()


class TestApiDriverInit:
    """Test ApiDriver initialization."""

    def test_uses_provided_model(self):
        """Should use the provided model name."""
        driver = ApiDriver(model="openrouter:anthropic/claude-sonnet-4-20250514")
        assert driver.model_name == "openrouter:anthropic/claude-sonnet-4-20250514"

    def test_defaults_to_openrouter_claude_sonnet(self):
        """Should default to OpenRouter Claude Sonnet when no model provided."""
        driver = ApiDriver()
        assert driver.model_name == ApiDriver.DEFAULT_MODEL
        assert driver._provider == "openrouter"


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
        driver = ApiDriver(model="openrouter:google/gemini-pro")
        model = driver._build_model()
        assert isinstance(model, OpenRouterModel)
        # Model name should have prefix stripped for the actual model
        assert model.model_name == "google/gemini-pro"

    @requires_openrouter_key
    def test_openrouter_model_uses_api_key(self):
        """Should configure OpenRouter provider with API key."""
        driver = ApiDriver(model="openrouter:meta-llama/llama-3-70b")

        # Mock OpenRouterProvider to capture constructor args
        with patch("amelia.drivers.api.openai.OpenRouterProvider") as mock_provider_class:
            driver._build_model()

            # Verify OpenRouterProvider was constructed with API key
            mock_provider_class.assert_called_once()
            call_kwargs = mock_provider_class.call_args.kwargs
            assert "api_key" in call_kwargs
            # TODO: pydantic-ai OpenRouterProvider doesn't yet support app_url/app_title
            # Once supported, we should pass OPENROUTER_APP_URL and OPENROUTER_APP_TITLE
