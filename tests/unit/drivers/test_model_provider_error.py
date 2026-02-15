"""Tests for model provider error detection and wrapping in ApiDriver."""
import os
from collections.abc import AsyncIterator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.exceptions import ModelProviderError
from amelia.drivers.api.deepagents import _extract_provider_info, _is_model_provider_error


# ---------------------------------------------------------------------------
# Pure helper function tests
# ---------------------------------------------------------------------------


class TestModelProviderErrorRepr:
    """Tests for ModelProviderError __repr__ method."""

    def test_repr_includes_all_fields(self) -> None:
        """__repr__ should include message, provider_name, and original_message."""
        exc = ModelProviderError(
            "Provider error",
            provider_name="minimax",
            original_message="invalid json",
        )
        result = repr(exc)
        assert result == (
            "ModelProviderError('Provider error', "
            "provider_name='minimax', "
            "original_message='invalid json')"
        )

    def test_repr_with_none_fields(self) -> None:
        """__repr__ should handle None values for optional fields."""
        exc = ModelProviderError("Provider error")
        result = repr(exc)
        assert result == (
            "ModelProviderError('Provider error', "
            "provider_name=None, "
            "original_message=None)"
        )


class TestIsModelProviderError:
    """Tests for _is_model_provider_error helper."""

    def test_is_model_provider_error_with_dict_args(self) -> None:
        """ValueError with a dict arg (langchain_openai pattern) should be detected."""
        exc = ValueError(
            {"error": {"message": "bad json"}, "provider": "minimax"}
        )
        assert _is_model_provider_error(exc) is True

    def test_is_model_provider_error_with_string_pattern(self) -> None:
        """ValueError containing a known provider error pattern should be detected."""
        exc = ValueError("midstream error occurred")
        assert _is_model_provider_error(exc) is True

    def test_is_model_provider_error_with_custom_env_pattern(self) -> None:
        """Custom patterns via AMELIA_PROVIDER_ERROR_PATTERNS should be detected."""
        with patch.dict(os.environ, {"AMELIA_PROVIDER_ERROR_PATTERNS": "custom error,another pattern"}):
            exc = ValueError("A custom error occurred")
            assert _is_model_provider_error(exc) is True

            # Original default patterns should NOT match when env var overrides
            exc_default = ValueError("midstream error occurred")
            assert _is_model_provider_error(exc_default) is False

    def test_is_not_model_provider_error_validation(self) -> None:
        """Amelia validation ValueErrors should NOT be detected as provider errors."""
        exc = ValueError("Prompt cannot be empty")
        assert _is_model_provider_error(exc) is False


class TestExtractProviderInfo:
    """Tests for _extract_provider_info helper."""

    def test_extract_provider_info_from_dict(self) -> None:
        """Should extract provider name and message from dict ValueError."""
        exc = ValueError(
            {"error": {"message": "invalid function arguments json string"}, "provider": "minimax"}
        )
        provider_name, message = _extract_provider_info(exc)
        assert provider_name == "minimax"
        assert "invalid function arguments json string" in message

    def test_extract_provider_info_from_string(self) -> None:
        """String ValueError should return None provider and str(exc) as message."""
        exc = ValueError("midstream error occurred")
        provider_name, message = _extract_provider_info(exc)
        assert provider_name is None
        assert message == str(exc)


# ---------------------------------------------------------------------------
# ApiDriver integration tests (mocked at external boundary)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_deepagents() -> Generator[MagicMock, None, None]:
    """Set up mocks for ApiDriver with provider error testing."""
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), \
         patch("amelia.drivers.api.deepagents.create_deep_agent") as mock_create, \
         patch("amelia.drivers.api.deepagents.init_chat_model"), \
         patch("amelia.drivers.api.deepagents.LocalSandbox"):
        yield mock_create


class TestExecuteAgenticProviderErrorWrapping:
    """Tests that execute_agentic wraps model provider ValueErrors."""

    async def test_execute_agentic_wraps_model_provider_error(
        self, mock_deepagents: MagicMock
    ) -> None:
        """execute_agentic should wrap dict-based ValueError as ModelProviderError."""
        from amelia.drivers.api.deepagents import ApiDriver

        async def failing_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            if False:
                yield
            raise ValueError(
                {"error": {"message": "invalid function arguments json string"}, "provider": "minimax"}
            )

        mock_agent = MagicMock()
        mock_agent.astream = failing_stream
        mock_deepagents.return_value = mock_agent

        driver = ApiDriver(model="test/model", provider="openrouter")

        with pytest.raises(ModelProviderError) as exc_info:
            async for _ in driver.execute_agentic(prompt="test", cwd="/tmp"):
                pass

        assert "minimax" in str(exc_info.value)

    async def test_execute_agentic_passes_through_validation_error(
        self, mock_deepagents: MagicMock
    ) -> None:
        """execute_agentic should NOT wrap Amelia validation ValueErrors."""
        from amelia.drivers.api.deepagents import ApiDriver

        async def failing_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            if False:
                yield
            raise ValueError("Prompt cannot be empty")

        mock_agent = MagicMock()
        mock_agent.astream = failing_stream
        mock_deepagents.return_value = mock_agent

        driver = ApiDriver(model="test/model", provider="openrouter")

        with pytest.raises(ValueError, match="Prompt cannot be empty") as exc_info:
            async for _ in driver.execute_agentic(prompt="test", cwd="/tmp"):
                pass

        assert not isinstance(exc_info.value, ModelProviderError)


class TestGenerateProviderErrorWrapping:
    """Tests that generate wraps model provider ValueErrors."""

    async def test_generate_wraps_model_provider_error(
        self, mock_deepagents: MagicMock
    ) -> None:
        """generate should wrap dict-based ValueError as ModelProviderError."""
        from amelia.drivers.api.deepagents import ApiDriver

        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(
            side_effect=ValueError(
                {"error": {"message": "invalid function arguments json string"}, "provider": "minimax"}
            )
        )
        mock_deepagents.return_value = mock_agent

        driver = ApiDriver(model="test/model", provider="openrouter")

        with pytest.raises(ModelProviderError) as exc_info:
            await driver.generate(prompt="test")

        assert "minimax" in str(exc_info.value)
