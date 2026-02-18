"""Tests for transient connection error handling in the deepagents API driver."""

import os
from collections.abc import AsyncIterator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import openai
import pytest

from amelia.core.exceptions import ModelProviderError


@pytest.fixture
def mock_deepagents() -> Generator[MagicMock, None, None]:
    """Set up mocks for ApiDriver with transient error testing."""
    with (
        patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}),
        patch("amelia.drivers.api.deepagents.create_deep_agent") as mock_create,
        patch("amelia.drivers.api.deepagents.init_chat_model"),
        patch("amelia.drivers.api.deepagents.LocalSandbox"),
    ):
        yield mock_create


_DUMMY_REQUEST = httpx.Request("POST", "https://api.example.com")

TRANSIENT_ERRORS: list[tuple[str, Exception]] = [
    ("ConnectError", httpx.ConnectError("Connection refused")),
    ("ReadError", httpx.ReadError("Connection reset by peer")),
    ("WriteError", httpx.WriteError("Broken pipe")),
    ("PoolTimeout", httpx.PoolTimeout("Timed out waiting for connection")),
    ("TimeoutException", httpx.TimeoutException("Request timed out")),
    (
        "APIConnectionError",
        openai.APIConnectionError(message="Connection failed", request=_DUMMY_REQUEST),
    ),
    (
        "APITimeoutError",
        openai.APITimeoutError(request=_DUMMY_REQUEST),
    ),
]


class TestGenerateTransientErrors:
    """Tests that generate wraps httpx transient errors as ModelProviderError."""

    @pytest.mark.parametrize("label,error", TRANSIENT_ERRORS, ids=[t[0] for t in TRANSIENT_ERRORS])
    async def test_generate_wraps_transient_error(
        self, mock_deepagents: MagicMock, label: str, error: Exception
    ) -> None:
        """generate should wrap httpx transport errors as ModelProviderError."""
        from amelia.drivers.api.deepagents import ApiDriver

        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(side_effect=error)
        mock_deepagents.return_value = mock_agent

        driver = ApiDriver(model="test/model", provider="openrouter")

        with pytest.raises(ModelProviderError) as exc_info:
            await driver.generate(prompt="test")

        assert exc_info.value.provider_name == "openai-compatible"
        assert exc_info.value.original_message == str(error)
        assert exc_info.value.__cause__ is error


class TestExecuteAgenticTransientErrors:
    """Tests that execute_agentic wraps httpx transient errors as ModelProviderError."""

    @pytest.mark.parametrize("label,error", TRANSIENT_ERRORS, ids=[t[0] for t in TRANSIENT_ERRORS])
    async def test_execute_agentic_wraps_transient_error(
        self, mock_deepagents: MagicMock, label: str, error: Exception
    ) -> None:
        """execute_agentic should wrap httpx transport errors as ModelProviderError."""
        from amelia.drivers.api.deepagents import ApiDriver

        async def failing_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            if False:
                yield
            raise error

        mock_agent = MagicMock()
        mock_agent.astream = failing_stream
        mock_deepagents.return_value = mock_agent

        driver = ApiDriver(model="test/model", provider="openrouter")

        with pytest.raises(ModelProviderError) as exc_info:
            async for _ in driver.execute_agentic(prompt="test", cwd="/tmp"):
                pass

        assert exc_info.value.provider_name == "openai-compatible"
        assert exc_info.value.original_message == str(error)
        assert exc_info.value.__cause__ is error
