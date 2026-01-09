"""Integration tests for API driver token usage tracking.

These tests verify that ApiDriver correctly accumulates token usage
by mocking at the HTTP boundary (the LangChain model's invoke calls).
"""
import os
from collections.abc import AsyncIterator, Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.ai import UsageMetadata

from amelia.drivers.api.deepagents import ApiDriver


class TestApiDriverTokenTrackingIntegration:
    """Integration tests for end-to-end token tracking in ApiDriver."""

    @pytest.fixture
    def mock_http_boundary(self) -> Generator[dict[str, MagicMock], None, None]:
        """Mock at the HTTP boundary - the LangChain model layer."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), \
             patch("amelia.drivers.api.deepagents.init_chat_model") as mock_init, \
             patch("amelia.drivers.api.deepagents.create_deep_agent") as mock_create:

            # Create mock chat model
            mock_chat_model = MagicMock()
            mock_init.return_value = mock_chat_model

            yield {
                "init_chat_model": mock_init,
                "create_deep_agent": mock_create,
                "chat_model": mock_chat_model,
            }

    async def test_full_execution_accumulates_usage(
        self, mock_http_boundary: dict[str, MagicMock]
    ) -> None:
        """Full agentic execution should accumulate usage from all turns."""
        # Simulate a multi-turn conversation with tool use
        turn1 = AIMessage(content=[{"type": "text", "text": "Let me check..."}])
        turn1.usage_metadata = UsageMetadata(
            input_tokens=500, output_tokens=100, total_tokens=600
        )
        turn1.response_metadata = {"token_usage": {"cost": 0.001}}
        turn1.tool_calls = [{"name": "read_file", "args": {"path": "test.py"}, "id": "tc1"}]

        turn2 = AIMessage(content="Here's what I found: the file contains tests.")
        turn2.usage_metadata = UsageMetadata(
            input_tokens=800, output_tokens=200, total_tokens=1000
        )
        turn2.response_metadata = {"token_usage": {"cost": 0.002}}
        turn2.tool_calls = []

        chunks = [
            {"messages": [HumanMessage(content="Read test.py"), turn1]},
            {"messages": [HumanMessage(content="Read test.py"), turn1, turn2]},
        ]

        async def mock_astream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            for chunk in chunks:
                yield chunk

        mock_agent = MagicMock()
        mock_agent.astream = mock_astream
        mock_http_boundary["create_deep_agent"].return_value = mock_agent

        driver = ApiDriver(model="openrouter:anthropic/claude-3.5-sonnet")

        # Run full execution
        messages = []
        async for msg in driver.execute_agentic("Read test.py", "/tmp"):
            messages.append(msg)

        # Verify usage was accumulated correctly
        usage = driver.get_usage()

        assert usage is not None
        assert usage.input_tokens == 1300  # 500 + 800
        assert usage.output_tokens == 300  # 100 + 200
        assert usage.cost_usd == 0.003  # 0.001 + 0.002
        assert usage.num_turns == 2
        assert usage.model == "openrouter:anthropic/claude-3.5-sonnet"
        # duration_ms may be None for mocked execution, or 0+ if tracked
        assert usage.duration_ms is None or usage.duration_ms >= 0

    async def test_usage_includes_model_name(
        self, mock_http_boundary: dict[str, MagicMock]
    ) -> None:
        """Usage should include the model name from driver initialization."""
        msg = AIMessage(content="Done")
        msg.usage_metadata = UsageMetadata(
            input_tokens=10, output_tokens=5, total_tokens=15
        )

        async def mock_astream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            yield {"messages": [msg]}

        mock_agent = MagicMock()
        mock_agent.astream = mock_astream
        mock_http_boundary["create_deep_agent"].return_value = mock_agent

        driver = ApiDriver(model="openrouter:minimax/minimax-m2")

        async for _ in driver.execute_agentic("test", "/tmp"):
            pass

        usage = driver.get_usage()
        assert usage is not None
        assert usage.model == "openrouter:minimax/minimax-m2"

    async def test_generate_does_not_track_usage(
        self, mock_http_boundary: dict[str, MagicMock]
    ) -> None:
        """generate() should not affect get_usage() (only execute_agentic tracks)."""
        msg = AIMessage(content="Response")

        async def mock_ainvoke(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return {"messages": [msg]}

        mock_agent = MagicMock()
        mock_agent.ainvoke = mock_ainvoke
        mock_http_boundary["create_deep_agent"].return_value = mock_agent

        driver = ApiDriver(model="openrouter:test/model")

        # Call generate (not execute_agentic)
        await driver.generate("test prompt")

        # get_usage should still be None (only execute_agentic tracks)
        usage = driver.get_usage()
        assert usage is None
