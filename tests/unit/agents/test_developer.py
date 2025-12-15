# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for Developer agent streaming."""

from collections.abc import Callable
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from amelia.agents.developer import Developer
from amelia.core.state import ExecutionState
from amelia.core.types import StreamEvent, StreamEventType
from amelia.drivers.cli.claude import ClaudeStreamEvent


@pytest.fixture
def mock_stream_emitter() -> AsyncMock:
    """Create a mock stream emitter."""
    return AsyncMock()


class TestDeveloperStreamEmitter:
    """Test Developer agent stream emitter functionality."""

    async def test_developer_emits_stream_events_during_agentic_execution(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
        mock_issue_factory: Callable[..., Any],
        mock_stream_emitter: AsyncMock,
        async_iterator_mock_factory: Callable[[list[Any]], Any],
    ) -> None:
        """Test that Developer emits stream events during agentic execution."""
        # Create issue for workflow_id fallback
        issue = mock_issue_factory(id="TEST-123", title="Test", description="Test")

        # Create driver and state with task and TaskDAG
        mock_driver, state = developer_test_context(task_desc="Test task")
        state.issue = issue
        state.plan.original_issue = "TEST-123"

        # Mock driver to return streaming events
        mock_events = [
            ClaudeStreamEvent(type="assistant", content="Thinking about the task..."),
            ClaudeStreamEvent(type="tool_use", tool_name="bash", tool_input={"command": "echo test"}),
            ClaudeStreamEvent(type="result"),
        ]

        mock_driver.execute_agentic.return_value = async_iterator_mock_factory(mock_events)

        # Create developer with emitter
        developer = Developer(
            driver=mock_driver,
            execution_mode="agentic",
            stream_emitter=mock_stream_emitter,
        )

        # Execute task
        await developer.execute_current_task(state, workflow_id="TEST-123")

        # Verify emitter was called
        assert mock_stream_emitter.called
        assert mock_stream_emitter.call_count >= 2  # At least assistant and tool_use events

        # Verify the emitted events have correct structure
        for call in mock_stream_emitter.call_args_list:
            event = call.args[0]
            assert isinstance(event, StreamEvent)
            assert event.agent == "developer"
            assert event.workflow_id == "TEST-123"  # Uses provided workflow_id
            assert isinstance(event.timestamp, datetime)
            assert event.type in [
                StreamEventType.CLAUDE_THINKING,
                StreamEventType.CLAUDE_TOOL_CALL,
                StreamEventType.CLAUDE_TOOL_RESULT,
            ]

    async def test_developer_does_not_emit_when_no_emitter_configured(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
        mock_issue_factory: Callable[..., Any],
        async_iterator_mock_factory: Callable[[list[Any]], Any],
    ) -> None:
        """Test that Developer does not crash when no emitter is configured."""
        issue = mock_issue_factory(id="TEST-456", title="Test", description="Test")

        # Create driver and state with task and TaskDAG
        mock_driver, state = developer_test_context(task_desc="Test task")
        state.issue = issue
        state.plan.original_issue = "TEST-456"

        mock_events = [
            ClaudeStreamEvent(type="assistant", content="Working..."),
            ClaudeStreamEvent(type="result"),
        ]

        mock_driver.execute_agentic.return_value = async_iterator_mock_factory(mock_events)

        # Create developer WITHOUT emitter
        developer = Developer(
            driver=mock_driver,
            execution_mode="agentic",
        )

        # Should not raise even without emitter
        result = await developer.execute_current_task(state, workflow_id="TEST-456")
        assert result["status"] == "completed"

    async def test_developer_converts_claude_events_to_stream_events(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
        mock_issue_factory: Callable[..., Any],
        mock_stream_emitter: AsyncMock,
        async_iterator_mock_factory: Callable[[list[Any]], Any],
    ) -> None:
        """Test that Developer converts ClaudeStreamEvents to StreamEvents correctly."""
        issue = mock_issue_factory(id="TEST-789", title="Test", description="Test")

        # Create driver and state with task and TaskDAG
        mock_driver, state = developer_test_context(task_desc="Test task")
        state.issue = issue
        state.plan.original_issue = "TEST-789"

        # Test each event type conversion
        mock_events = [
            ClaudeStreamEvent(type="assistant", content="Analyzing code..."),
            ClaudeStreamEvent(
                type="tool_use",
                tool_name="bash",
                tool_input={"command": "pytest"}
            ),
            ClaudeStreamEvent(type="result"),
        ]

        mock_driver.execute_agentic.return_value = async_iterator_mock_factory(mock_events)

        developer = Developer(
            driver=mock_driver,
            execution_mode="agentic",
            stream_emitter=mock_stream_emitter,
        )

        await developer.execute_current_task(state, workflow_id="TEST-789")

        # Verify conversions
        emitted_events = [call.args[0] for call in mock_stream_emitter.call_args_list]

        # Find assistant event
        thinking_events = [e for e in emitted_events if e.type == StreamEventType.CLAUDE_THINKING]
        assert len(thinking_events) == 1
        assert thinking_events[0].content == "Analyzing code..."

        # Find tool_use event
        tool_events = [e for e in emitted_events if e.type == StreamEventType.CLAUDE_TOOL_CALL]
        assert len(tool_events) == 1
        assert tool_events[0].tool_name == "bash"
        assert tool_events[0].tool_input == {"command": "pytest"}

        # Find result event
        result_events = [e for e in emitted_events if e.type == StreamEventType.CLAUDE_TOOL_RESULT]
        assert len(result_events) == 1
