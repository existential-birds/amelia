import pytest

from amelia.drivers.api.openai import ApiDriver


@pytest.mark.parametrize(
    "model,should_succeed",
    [
        pytest.param("openai:gpt-4o", True, id="openai_gpt4o"),
        pytest.param("openai:gpt-4o-mini", True, id="openai_gpt4o_mini"),
        pytest.param("anthropic:claude-3", False, id="anthropic_rejected"),
        pytest.param("gemini:pro", False, id="gemini_rejected"),
    ],
)
def test_api_driver_provider_validation(model, should_succeed):
    """Verifies ApiDriver's provider validation - only OpenAI providers allowed."""
    if should_succeed:
        driver = ApiDriver(model=model)
        assert driver is not None
    else:
        with pytest.raises(ValueError, match="Unsupported provider"):
            ApiDriver(model=model)
