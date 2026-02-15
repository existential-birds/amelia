"""Tests for model provider error detection and wrapping in drivers."""
import os
from collections.abc import AsyncIterator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from claude_agent_sdk._errors import ProcessError

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
        from amelia.drivers.api.deepagents import _get_provider_error_patterns

        with patch.dict(os.environ, {"AMELIA_PROVIDER_ERROR_PATTERNS": "custom error,another pattern"}):
            # Clear the LRU cache so the function re-reads the environment variable
            _get_provider_error_patterns.cache_clear()

            exc = ValueError("A custom error occurred")
            assert _is_model_provider_error(exc) is True

            # Original default patterns should NOT match when env var overrides
            exc_default = ValueError("midstream error occurred")
            assert _is_model_provider_error(exc_default) is False

        # Clear cache again to restore default patterns for other tests
        _get_provider_error_patterns.cache_clear()

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


# ---------------------------------------------------------------------------
# CLI driver ProcessError wrapping tests
# ---------------------------------------------------------------------------


class TestCliDriverProcessErrorWrapping:
    """Tests that ClaudeCliDriver wraps ProcessError as ModelProviderError."""

    async def test_execute_agentic_wraps_process_error(self) -> None:
        """execute_agentic should wrap ProcessError as ModelProviderError."""
        with patch("amelia.drivers.cli.claude.ClaudeSDKClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(
                side_effect=ProcessError("Command failed with exit code 1")
            )
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            from amelia.drivers.cli.claude import ClaudeCliDriver

            driver = ClaudeCliDriver(model="sonnet", cwd="/tmp")

            with pytest.raises(ModelProviderError) as exc_info:
                async for _ in driver.execute_agentic(prompt="test", cwd="/tmp"):
                    pass

            assert exc_info.value.provider_name == "claude-cli"
            assert "exit code 1" in str(exc_info.value.original_message)

    async def test_execute_agentic_captures_stderr_via_callback(self) -> None:
        """execute_agentic should capture real stderr via callback and include it in error."""
        with patch("amelia.drivers.cli.claude.ClaudeSDKClient") as mock_client_cls:

            def fake_init(options: Any) -> AsyncMock:
                """Simulate SDK calling stderr callback before raising."""
                mock = AsyncMock()

                async def aenter(*_: Any) -> AsyncMock:
                    # Simulate the SDK firing stderr callback before process exit
                    if options.stderr:
                        options.stderr("Error: ANTHROPIC_API_KEY not set")
                        options.stderr("Please set your API key")
                    raise ProcessError(
                        "Command failed",
                        exit_code=1,
                        stderr="Check stderr output for details",
                    )

                mock.__aenter__ = aenter
                mock.__aexit__ = AsyncMock(return_value=False)
                return mock

            mock_client_cls.side_effect = fake_init

            from amelia.drivers.cli.claude import ClaudeCliDriver

            driver = ClaudeCliDriver(model="sonnet", cwd="/tmp")

            with pytest.raises(ModelProviderError) as exc_info:
                async for _ in driver.execute_agentic(prompt="test", cwd="/tmp"):
                    pass

            # Real stderr captured via callback, not the SDK placeholder
            assert "ANTHROPIC_API_KEY not set" in str(exc_info.value)
            assert "Please set your API key" in str(exc_info.value)
            assert "Check stderr output for details" not in str(exc_info.value)
            assert "exit code 1" in str(exc_info.value)

    async def test_generate_wraps_process_error(self) -> None:
        """generate should wrap ProcessError as ModelProviderError."""
        with patch("amelia.drivers.cli.claude.query") as mock_query:

            async def failing_query(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
                if False:
                    yield
                raise ProcessError("Command failed with exit code 1")

            mock_query.side_effect = failing_query

            from amelia.drivers.cli.claude import ClaudeCliDriver

            driver = ClaudeCliDriver(model="sonnet", cwd="/tmp")

            with pytest.raises(ModelProviderError) as exc_info:
                await driver.generate(prompt="test")

            assert exc_info.value.provider_name == "claude-cli"
            assert "exit code 1" in str(exc_info.value.original_message)
