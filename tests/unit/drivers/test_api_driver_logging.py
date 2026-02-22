"""Tests for API driver terminal logging via log_claude_result."""

from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import pytest

from amelia.drivers.api.deepagents import ApiDriver
from amelia.drivers.base import AgenticMessage


async def _async_iter(items: list) -> AsyncIterator:
    """Helper to create an async iterator from a list."""
    for item in items:
        yield item


@pytest.fixture
def driver() -> ApiDriver:
    """Create a fresh ApiDriver for testing."""
    return ApiDriver(model="test-model", cwd="/tmp", provider="openrouter")


async def _collect_messages(gen: AsyncIterator[AgenticMessage]) -> list[AgenticMessage]:
    """Collect all messages from an async generator."""
    return [msg async for msg in gen]


class TestApiDriverLogging:
    """Tests that log_claude_result is called appropriately during execute_agentic."""

    @patch("amelia.drivers.api.deepagents.log_claude_result")
    @patch("amelia.drivers.api.deepagents._create_chat_model")
    @patch("amelia.drivers.api.deepagents.create_deep_agent")
    async def test_thinking_calls_log_claude_result(
        self,
        mock_create_agent: MagicMock,
        mock_create_model: MagicMock,
        mock_log: MagicMock,
        driver: ApiDriver,
    ) -> None:
        """log_claude_result is called with result_type='assistant' for THINKING messages."""
        from langchain_core.messages import AIMessage

        # Thinking message followed by a result
        thinking_msg = AIMessage(content=[{"type": "text", "text": "I am thinking..."}])
        thinking_msg.tool_calls = []
        result_msg = AIMessage(content="Done!")
        result_msg.tool_calls = []

        mock_agent = MagicMock()
        mock_agent.astream = MagicMock(
            return_value=_async_iter([
                {"messages": [thinking_msg]},
                {"messages": [result_msg]},
            ])
        )
        mock_create_agent.return_value = mock_agent
        mock_create_model.return_value = MagicMock()

        await _collect_messages(
            driver.execute_agentic(prompt="test", cwd="/tmp")
        )

        # Should have been called for the thinking content
        thinking_calls = [
            call for call in mock_log.call_args_list
            if call.kwargs.get("result_type") == "assistant"
        ]
        assert len(thinking_calls) >= 1
        assert thinking_calls[0].kwargs.get("content") == "I am thinking..."

    @patch("amelia.drivers.api.deepagents.log_claude_result")
    @patch("amelia.drivers.api.deepagents._create_chat_model")
    @patch("amelia.drivers.api.deepagents.create_deep_agent")
    async def test_tool_call_calls_log_claude_result(
        self,
        mock_create_agent: MagicMock,
        mock_create_model: MagicMock,
        mock_log: MagicMock,
        driver: ApiDriver,
    ) -> None:
        """log_claude_result is called with result_type='tool_use' for TOOL_CALL messages."""
        from langchain_core.messages import AIMessage

        tool_msg = AIMessage(content="")
        tool_msg.tool_calls = [{"name": "read_file", "args": {"path": "foo.py"}, "id": "tc_1"}]
        result_msg = AIMessage(content="Done!")
        result_msg.tool_calls = []

        mock_agent = MagicMock()
        mock_agent.astream = MagicMock(
            return_value=_async_iter([
                {"messages": [tool_msg]},
                {"messages": [result_msg]},
            ])
        )
        mock_create_agent.return_value = mock_agent
        mock_create_model.return_value = MagicMock()

        await _collect_messages(
            driver.execute_agentic(prompt="test", cwd="/tmp")
        )

        tool_calls = [
            call for call in mock_log.call_args_list
            if call.kwargs.get("result_type") == "tool_use"
        ]
        assert len(tool_calls) >= 1
        assert tool_calls[0].kwargs.get("tool_name") == "read_file"

    @patch("amelia.drivers.api.deepagents.log_claude_result")
    @patch("amelia.drivers.api.deepagents._create_chat_model")
    @patch("amelia.drivers.api.deepagents.create_deep_agent")
    async def test_result_calls_log_claude_result(
        self,
        mock_create_agent: MagicMock,
        mock_create_model: MagicMock,
        mock_log: MagicMock,
        driver: ApiDriver,
    ) -> None:
        """log_claude_result is called with result_type='result' for the final RESULT."""
        from langchain_core.messages import AIMessage

        result_msg = AIMessage(content="Final answer here!")
        result_msg.tool_calls = []

        mock_agent = MagicMock()
        mock_agent.astream = MagicMock(
            return_value=_async_iter([
                {"messages": [result_msg]},
            ])
        )
        mock_create_agent.return_value = mock_agent
        mock_create_model.return_value = MagicMock()

        await _collect_messages(
            driver.execute_agentic(prompt="test", cwd="/tmp")
        )

        result_calls = [
            call for call in mock_log.call_args_list
            if call.kwargs.get("result_type") == "result"
        ]
        assert len(result_calls) == 1
        assert result_calls[0].kwargs.get("result_text") == "Final answer here!"
