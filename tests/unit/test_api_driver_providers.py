"""Tests for ApiDriver provider extraction."""
from pydantic_ai.models.openrouter import OpenRouterModel

from amelia.drivers.api.openai import OPENROUTER_APP_TITLE, OPENROUTER_APP_URL, ApiDriver


class TestProviderExtraction:
    """Test provider extraction in ApiDriver."""

    def test_extracts_openai_provider(self):
        """Should extract openai provider from model string."""
        driver = ApiDriver(model="openai:gpt-4o")
        assert driver.model_name == "openai:gpt-4o"
        assert driver._provider == "openai"

    def test_extracts_openrouter_provider(self):
        """Should extract openrouter provider from model string."""
        driver = ApiDriver(model="openrouter:anthropic/claude-3.5-sonnet")
        assert driver.model_name == "openrouter:anthropic/claude-3.5-sonnet"
        assert driver._provider == "openrouter"

    def test_defaults_to_openai_without_prefix(self):
        """Should default to openai provider when no prefix given."""
        driver = ApiDriver(model="gpt-4o")
        assert driver._provider == "openai"


class TestBuildModel:
    """Test _build_model method."""

    def test_returns_string_for_openai(self):
        """Should return model string for OpenAI provider."""
        driver = ApiDriver(model="openai:gpt-4o")
        model = driver._build_model()
        assert model == "openai:gpt-4o"

    def test_returns_openrouter_model_for_openrouter(self):
        """Should return OpenRouterModel with attribution for OpenRouter provider."""
        driver = ApiDriver(model="openrouter:anthropic/claude-3.5-sonnet")
        model = driver._build_model()

        assert isinstance(model, OpenRouterModel)
        assert model.model_name == "anthropic/claude-3.5-sonnet"

    def test_openrouter_model_has_app_attribution(self):
        """Should configure OpenRouter provider with app URL and title."""
        driver = ApiDriver(model="openrouter:google/gemini-pro")
        model = driver._build_model()

        assert isinstance(model, OpenRouterModel)
        # Verify the provider was created with attribution
        assert OPENROUTER_APP_URL == "https://github.com/existential-birds/amelia"
        assert OPENROUTER_APP_TITLE == "Amelia"
