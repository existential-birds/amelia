"""Tests for ApiDriver OpenRouter integration."""
from pydantic_ai.models.openrouter import OpenRouterModel

from amelia.drivers.api.openai import OPENROUTER_APP_TITLE, OPENROUTER_APP_URL, ApiDriver


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

    def test_accepts_any_openrouter_model(self):
        """Should accept any OpenRouter model identifier."""
        driver = ApiDriver(model="openai/gpt-4o")
        assert driver.model_name == "openai/gpt-4o"


class TestBuildModel:
    """Test _build_model method."""

    def test_returns_openrouter_model(self):
        """Should return OpenRouterModel for any model."""
        driver = ApiDriver(model="anthropic/claude-3.5-sonnet")
        model = driver._build_model()
        assert isinstance(model, OpenRouterModel)

    def test_model_name_passed_correctly(self):
        """Should pass model name to OpenRouterModel."""
        driver = ApiDriver(model="google/gemini-pro")
        model = driver._build_model()
        assert isinstance(model, OpenRouterModel)
        assert model.model_name == "google/gemini-pro"

    def test_openrouter_model_has_app_attribution(self):
        """Should configure OpenRouter provider with app URL and title."""
        driver = ApiDriver(model="meta-llama/llama-3-70b")
        model = driver._build_model()

        assert isinstance(model, OpenRouterModel)
        # Verify the constants are set correctly
        assert OPENROUTER_APP_URL == "https://github.com/existential-birds/amelia"
        assert OPENROUTER_APP_TITLE == "Amelia"
