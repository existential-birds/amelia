# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for ApiDriver model handling - verifies models are correctly passed to OpenRouter."""
import pytest
from pydantic_ai.models.openrouter import OpenRouterModel

from amelia.drivers.api.openai import ApiDriver


@pytest.mark.parametrize(
    "model",
    [
        pytest.param("anthropic/claude-sonnet-4-20250514", id="anthropic_claude"),
        pytest.param("openai/gpt-4o", id="openai_gpt4o"),
        pytest.param("openai/gpt-4o-mini", id="openai_gpt4o_mini"),
        pytest.param("google/gemini-pro", id="google_gemini"),
        pytest.param("meta-llama/llama-3-70b-instruct", id="meta_llama"),
        pytest.param("x-ai/grok-code-fast-1", id="xai_grok"),
    ],
)
def test_api_driver_accepts_openrouter_models(model: str) -> None:
    """Verifies ApiDriver accepts any OpenRouter model identifier.

    All models are routed through OpenRouter - validation happens at runtime
    when the model is actually used.
    """
    driver = ApiDriver(model=model)
    assert driver.model_name == model

    # Verify it builds an OpenRouterModel
    built_model = driver._build_model()
    assert isinstance(built_model, OpenRouterModel)
    assert built_model.model_name == model
