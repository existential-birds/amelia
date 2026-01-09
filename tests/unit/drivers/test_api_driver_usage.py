"""Tests for ApiDriver token usage tracking."""
import asyncio
import os
from collections.abc import AsyncIterator, Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.ai import UsageMetadata


class TestApiDriverGetUsage:
    """Tests for ApiDriver.get_usage() method."""

    def test_get_usage_returns_none_before_execution(self) -> None:
        """get_usage() should return None before any execution."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            from amelia.drivers.api.deepagents import ApiDriver

            driver = ApiDriver(model="openrouter:test/model")

            result = driver.get_usage()

            assert result is None


class TestApiDriverUsageAccumulation:
    """Tests for ApiDriver usage accumulation during execute_agentic."""

    @pytest.fixture
    def mock_deepagents_for_usage(self) -> Generator[MagicMock, None, None]:
        """Set up mock for DeepAgents with usage metadata."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), \
             patch("amelia.drivers.api.deepagents.create_deep_agent") as mock_create, \
             patch("amelia.drivers.api.deepagents.init_chat_model"), \
             patch("amelia.drivers.api.deepagents.LocalSandbox"):

            yield mock_create

    async def test_accumulates_usage_from_ai_messages(
        self, mock_deepagents_for_usage: MagicMock
    ) -> None:
        """execute_agentic should accumulate usage from AIMessage.usage_metadata."""
        from amelia.drivers.api.deepagents import ApiDriver

        # Create AIMessages with usage_metadata using proper UsageMetadata type
        msg1 = AIMessage(content="First response")
        msg1.usage_metadata = UsageMetadata(
            input_tokens=100, output_tokens=50, total_tokens=150
        )

        msg2 = AIMessage(content="Second response")
        msg2.usage_metadata = UsageMetadata(
            input_tokens=200, output_tokens=100, total_tokens=300
        )

        # Set up mock agent to yield chunks with these messages
        stream_chunks = [
            {"messages": [HumanMessage(content="test"), msg1]},
            {"messages": [HumanMessage(content="test"), msg1, msg2]},
        ]

        async def mock_astream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            for chunk in stream_chunks:
                yield chunk

        mock_agent = MagicMock()
        mock_agent.astream = mock_astream
        mock_deepagents_for_usage.return_value = mock_agent

        driver = ApiDriver(model="openrouter:test/model")

        # Consume the generator
        messages = []
        async for msg in driver.execute_agentic("test prompt", "/tmp"):
            messages.append(msg)

        # Verify accumulated usage
        usage = driver.get_usage()
        assert usage is not None
        assert usage.input_tokens == 300  # 100 + 200
        assert usage.output_tokens == 150  # 50 + 100
        assert usage.model == "openrouter:test/model"
        assert usage.num_turns == 2

    async def test_extracts_cost_from_openrouter_metadata(
        self, mock_deepagents_for_usage: MagicMock
    ) -> None:
        """execute_agentic should extract cost from OpenRouter response_metadata."""
        from amelia.drivers.api.deepagents import ApiDriver

        # Create AIMessage with OpenRouter cost in response_metadata
        msg = AIMessage(content="Response")
        msg.usage_metadata = UsageMetadata(
            input_tokens=100, output_tokens=50, total_tokens=150
        )
        msg.response_metadata = {"token_usage": {"cost": 0.0025}}

        stream_chunks = [{"messages": [msg]}]

        async def mock_astream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            for chunk in stream_chunks:
                yield chunk

        mock_agent = MagicMock()
        mock_agent.astream = mock_astream
        mock_deepagents_for_usage.return_value = mock_agent

        driver = ApiDriver(model="openrouter:test/model")

        async for _ in driver.execute_agentic("test", "/tmp"):
            pass

        usage = driver.get_usage()
        assert usage is not None
        assert usage.cost_usd == 0.0025

    async def test_accumulates_cost_from_multiple_messages(
        self, mock_deepagents_for_usage: MagicMock
    ) -> None:
        """Cost should accumulate from multiple AIMessages with response_metadata."""
        from amelia.drivers.api.deepagents import ApiDriver

        msg1 = AIMessage(content="First")
        msg1.usage_metadata = UsageMetadata(
            input_tokens=100, output_tokens=50, total_tokens=150
        )
        msg1.response_metadata = {"token_usage": {"cost": 0.001}}

        msg2 = AIMessage(content="Second")
        msg2.usage_metadata = UsageMetadata(
            input_tokens=100, output_tokens=50, total_tokens=150
        )
        msg2.response_metadata = {"token_usage": {"cost": 0.002}}

        stream_chunks = [
            {"messages": [msg1]},
            {"messages": [msg1, msg2]},
        ]

        async def mock_astream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            for chunk in stream_chunks:
                yield chunk

        mock_agent = MagicMock()
        mock_agent.astream = mock_astream
        mock_deepagents_for_usage.return_value = mock_agent

        driver = ApiDriver(model="openrouter:test/model")

        async for _ in driver.execute_agentic("test", "/tmp"):
            pass

        usage = driver.get_usage()
        assert usage is not None
        assert usage.cost_usd == 0.003  # 0.001 + 0.002

    async def test_tracks_duration_ms(
        self, mock_deepagents_for_usage: MagicMock
    ) -> None:
        """execute_agentic should track execution duration in milliseconds."""
        from amelia.drivers.api.deepagents import ApiDriver

        msg = AIMessage(content="Done")
        msg.usage_metadata = UsageMetadata(
            input_tokens=10, output_tokens=5, total_tokens=15
        )

        async def mock_astream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            await asyncio.sleep(0.1)  # 100ms delay
            yield {"messages": [msg]}

        mock_agent = MagicMock()
        mock_agent.astream = mock_astream
        mock_deepagents_for_usage.return_value = mock_agent

        driver = ApiDriver(model="openrouter:test/model")

        async for _ in driver.execute_agentic("test", "/tmp"):
            pass

        usage = driver.get_usage()
        assert usage is not None
        assert usage.duration_ms is not None
        assert usage.duration_ms >= 100  # At least 100ms

    async def test_resets_usage_on_new_execution(
        self, mock_deepagents_for_usage: MagicMock
    ) -> None:
        """Each execute_agentic call should reset and start fresh usage tracking."""
        from amelia.drivers.api.deepagents import ApiDriver

        msg1 = AIMessage(content="First run")
        msg1.usage_metadata = UsageMetadata(
            input_tokens=100, output_tokens=50, total_tokens=150
        )

        msg2 = AIMessage(content="Second run")
        msg2.usage_metadata = UsageMetadata(
            input_tokens=200, output_tokens=100, total_tokens=300
        )

        call_count = 0

        async def mock_astream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield {"messages": [msg1]}
            else:
                yield {"messages": [msg2]}

        mock_agent = MagicMock()
        mock_agent.astream = mock_astream
        mock_deepagents_for_usage.return_value = mock_agent

        driver = ApiDriver(model="openrouter:test/model")

        # First execution
        async for _ in driver.execute_agentic("first", "/tmp"):
            pass
        usage1 = driver.get_usage()
        assert usage1 is not None

        # Second execution
        async for _ in driver.execute_agentic("second", "/tmp"):
            pass
        usage2 = driver.get_usage()
        assert usage2 is not None

        # Usage should be from second run only, not accumulated
        assert usage1.input_tokens == 100
        assert usage2.input_tokens == 200
