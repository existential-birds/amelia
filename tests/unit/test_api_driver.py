# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for DeepAgents-based ApiDriver."""
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from amelia.drivers.api.deepagents import ApiDriver


class ResponseSchema(BaseModel):
    """Test schema for structured output."""

    message: str


class TestApiDriverInit:
    """Test ApiDriver initialization."""

    def test_uses_provided_model(self) -> None:
        """Should use the provided model name."""
        driver = ApiDriver(model="openrouter:anthropic/claude-sonnet-4-20250514")
        assert driver.model == "openrouter:anthropic/claude-sonnet-4-20250514"

    def test_defaults_to_claude_sonnet(self) -> None:
        """Should default to Claude Sonnet when no model provided."""
        driver = ApiDriver()
        assert driver.model == ApiDriver.DEFAULT_MODEL

    def test_stores_cwd(self) -> None:
        """Should store the cwd parameter."""
        driver = ApiDriver(cwd="/some/path")
        assert driver.cwd == "/some/path"


class TestGenerate:
    """Test generate() method."""

    @pytest.fixture
    def driver(self) -> ApiDriver:
        """Create ApiDriver instance for tests."""
        return ApiDriver(model="openrouter:test/model", cwd="/test/path")

    async def test_rejects_empty_prompt(self, driver: ApiDriver) -> None:
        """Should reject empty or whitespace-only prompts."""
        with pytest.raises(ValueError, match="Prompt cannot be empty"):
            await driver.generate("")

        with pytest.raises(ValueError, match="Prompt cannot be empty"):
            await driver.generate("   \n\t  ")

    async def test_returns_text_without_schema(
        self, driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Should return plain text when no schema provided."""
        mock_deepagents.agent_result["messages"] = [
            HumanMessage(content="test prompt"),
            AIMessage(content="Test response from model"),
        ]

        result, session_id = await driver.generate(
            prompt="test prompt",
            system_prompt="You are a helpful assistant",
        )

        assert result == "Test response from model"
        assert session_id is None

        # Verify create_deep_agent was called correctly
        mock_deepagents.create_deep_agent.assert_called_once()
        call_kwargs = mock_deepagents.create_deep_agent.call_args.kwargs
        assert call_kwargs["system_prompt"] == "You are a helpful assistant"

    async def test_parses_schema_when_provided(
        self, driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Should parse response as schema when schema provided."""
        mock_deepagents.agent_result["messages"] = [
            AIMessage(content='{"message": "parsed response"}'),
        ]

        result, session_id = await driver.generate(
            prompt="test prompt",
            schema=ResponseSchema,
        )

        assert isinstance(result, ResponseSchema)
        assert result.message == "parsed response"
        assert session_id is None

    async def test_raises_on_schema_parse_failure(
        self, driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Should raise ValueError when schema parsing fails."""
        mock_deepagents.agent_result["messages"] = [
            AIMessage(content="not valid json"),
        ]

        with pytest.raises(ValueError, match="Failed to parse response"):
            await driver.generate(prompt="test", schema=ResponseSchema)

    async def test_handles_list_content_blocks(
        self, driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Should handle AIMessage with list of content blocks."""
        mock_deepagents.agent_result["messages"] = [
            AIMessage(content=[{"text": "Hello "}, {"text": "World"}]),
        ]

        result, _ = await driver.generate(prompt="test")

        assert result == "Hello World"

    async def test_raises_on_empty_response(
        self, driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Should raise RuntimeError when no messages returned."""
        mock_deepagents.agent_result["messages"] = []

        with pytest.raises(RuntimeError, match="No response messages"):
            await driver.generate(prompt="test")

    async def test_uses_none_system_prompt_as_empty_string(
        self, driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Should use empty string when system_prompt is None."""
        mock_deepagents.agent_result["messages"] = [
            AIMessage(content="response"),
        ]

        await driver.generate(prompt="test", system_prompt=None)

        call_kwargs = mock_deepagents.create_deep_agent.call_args.kwargs
        assert call_kwargs["system_prompt"] == ""


class TestExecuteAgentic:
    """Test execute_agentic() method."""

    async def test_rejects_missing_cwd(self) -> None:
        """Should reject when cwd is not set."""
        driver = ApiDriver(model="test", cwd=None)

        with pytest.raises(ValueError, match="cwd must be set"):
            async for _ in driver.execute_agentic(prompt="test"):
                pass

    async def test_rejects_empty_prompt(self) -> None:
        """Should reject empty prompts."""
        driver = ApiDriver(model="test", cwd="/some/path")

        with pytest.raises(ValueError, match="Prompt cannot be empty"):
            async for _ in driver.execute_agentic(prompt=""):
                pass

    async def test_yields_messages_from_stream(
        self, mock_deepagents: MagicMock
    ) -> None:
        """Should yield BaseMessage objects from the stream."""
        driver = ApiDriver(model="test", cwd="/test/path")

        # Set up streaming messages
        messages_stream = [
            {"messages": [HumanMessage(content="input")]},
            {"messages": [HumanMessage(content="input"), AIMessage(content="thinking...")]},
            {"messages": [HumanMessage(content="input"), AIMessage(content="done")]},
        ]
        mock_deepagents.stream_chunks = messages_stream

        collected: list[Any] = []
        async for msg in driver.execute_agentic(prompt="test"):
            collected.append(msg)

        # Should yield the last message from each chunk
        assert len(collected) == 3
        assert isinstance(collected[0], HumanMessage)
        assert isinstance(collected[1], AIMessage)
        assert collected[1].content == "thinking..."
        assert isinstance(collected[2], AIMessage)
        assert collected[2].content == "done"
