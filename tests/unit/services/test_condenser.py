"""Unit tests for condenser service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
from amelia.services.condenser import condense_description


@pytest.fixture
def mock_driver() -> MagicMock:
    driver = MagicMock()
    driver.generate = AsyncMock(return_value=("Condensed text", "session-abc"))
    return driver


class TestCondenseDescription:
    async def test_condense_description_returns_text(self, mock_driver: MagicMock) -> None:
        text, session_id = await condense_description("Long description text", mock_driver)
        assert text == "Condensed text"

    async def test_condense_description_uses_default_prompt(
        self, mock_driver: MagicMock
    ) -> None:
        await condense_description("Long description text", mock_driver)
        mock_driver.generate.assert_called_once()
        call_kwargs = mock_driver.generate.call_args
        expected_prompt = PROMPT_DEFAULTS["condenser.system"].content
        assert call_kwargs.kwargs.get("system_prompt") == expected_prompt or (
            len(call_kwargs.args) > 1 and call_kwargs.args[1] == expected_prompt
        )

    async def test_condense_description_uses_custom_prompt(
        self, mock_driver: MagicMock
    ) -> None:
        await condense_description(
            "Long description text", mock_driver, system_prompt="Custom prompt"
        )
        mock_driver.generate.assert_called_once()
        call_kwargs = mock_driver.generate.call_args
        assert (
            call_kwargs.kwargs.get("system_prompt") == "Custom prompt"
            or (len(call_kwargs.args) > 1 and call_kwargs.args[1] == "Custom prompt")
        )

    async def test_condense_description_returns_session_id(self, mock_driver: MagicMock) -> None:
        text, session_id = await condense_description("Long description text", mock_driver)
        assert session_id == "session-abc"

    async def test_condense_description_returns_none_session_when_driver_returns_none(
        self,
    ) -> None:
        driver = MagicMock()
        driver.generate = AsyncMock(return_value=("Condensed", None))
        text, session_id = await condense_description("Long description text", driver)
        assert text == "Condensed"
        assert session_id is None
