# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for streaming types."""

from datetime import UTC, datetime
from typing import Any

from amelia.core.types import StreamEvent, StreamEventType


class TestStreamEventType:
    """Test StreamEventType enum."""

    def test_all_values(self) -> None:
        """StreamEventType should have exactly 4 values."""
        expected = {
            "claude_thinking",
            "claude_tool_call",
            "claude_tool_result",
            "agent_output",
        }
        actual = {e.value for e in StreamEventType}
        assert actual == expected


class TestStreamEvent:
    """Test StreamEvent Pydantic model."""

    def test_valid_event_all_fields(self) -> None:
        """StreamEvent should validate with all fields provided."""
        now = datetime.now(UTC)
        event = StreamEvent(
            type=StreamEventType.CLAUDE_TOOL_CALL,
            content="Calling read_file tool",
            timestamp=now,
            agent="developer",
            workflow_id="workflow-123",
            tool_name="read_file",
            tool_input={"path": "/tmp/test.py"},
        )
        assert event.type == StreamEventType.CLAUDE_TOOL_CALL
        assert event.content == "Calling read_file tool"
        assert event.timestamp == now
        assert event.agent == "developer"
        assert event.workflow_id == "workflow-123"
        assert event.tool_name == "read_file"
        assert event.tool_input == {"path": "/tmp/test.py"}

    def test_valid_event_minimal_fields(self) -> None:
        """StreamEvent should validate with only required fields."""
        now = datetime.now(UTC)
        event = StreamEvent(
            type=StreamEventType.CLAUDE_THINKING,
            timestamp=now,
            agent="architect",
            workflow_id="workflow-456",
        )
        assert event.type == StreamEventType.CLAUDE_THINKING
        assert event.content is None
        assert event.timestamp == now
        assert event.agent == "architect"
        assert event.workflow_id == "workflow-456"
        assert event.tool_name is None
        assert event.tool_input is None

    def test_agent_output_event(self) -> None:
        """StreamEvent should work for AGENT_OUTPUT type."""
        now = datetime.now(UTC)
        event = StreamEvent(
            type=StreamEventType.AGENT_OUTPUT,
            content="Plan generated successfully",
            timestamp=now,
            agent="architect",
            workflow_id="workflow-789",
        )
        assert event.type == StreamEventType.AGENT_OUTPUT
        assert event.content == "Plan generated successfully"
        assert event.agent == "architect"

    def test_tool_result_event(self) -> None:
        """StreamEvent should work for CLAUDE_TOOL_RESULT type."""
        now = datetime.now(UTC)
        event = StreamEvent(
            type=StreamEventType.CLAUDE_TOOL_RESULT,
            content="File contents: ...",
            timestamp=now,
            agent="reviewer",
            workflow_id="workflow-abc",
            tool_name="read_file",
        )
        assert event.type == StreamEventType.CLAUDE_TOOL_RESULT
        assert event.content == "File contents: ..."
        assert event.tool_name == "read_file"

    def test_tool_input_accepts_dict(self) -> None:
        """StreamEvent tool_input should accept dict with Any values."""
        now = datetime.now(UTC)
        tool_input: dict[str, Any] = {
            "path": "/tmp/test.py",
            "count": 42,
            "flags": ["verbose", "debug"],
            "config": {"key": "value"},
        }
        event = StreamEvent(
            type=StreamEventType.CLAUDE_TOOL_CALL,
            timestamp=now,
            agent="developer",
            workflow_id="workflow-123",
            tool_input=tool_input,
        )
        assert event.tool_input == tool_input
        assert isinstance(event.tool_input, dict)
