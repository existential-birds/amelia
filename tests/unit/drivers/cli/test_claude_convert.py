# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for convert_to_stream_event() helper in ClaudeCliDriver."""

from datetime import UTC, datetime

import pytest

from amelia.core.types import StreamEvent, StreamEventType
from amelia.drivers.cli.claude import ClaudeStreamEvent, convert_to_stream_event


class TestConvertToStreamEvent:
    """Tests for convert_to_stream_event() function."""

    @pytest.mark.parametrize("input_type,expected_stream_type,content,tool_name,tool_input,agent,workflow_id", [
        ("assistant", StreamEventType.CLAUDE_THINKING, "Let me analyze this...", None, None, "developer", "wf-123"),
        ("tool_use", StreamEventType.CLAUDE_TOOL_CALL, None, "write_file", {"file_path": "/tmp/test.py", "content": "# test"}, "architect", "wf-456"),
        ("result", StreamEventType.CLAUDE_TOOL_RESULT, None, None, None, "reviewer", "wf-789"),
    ])
    def test_convert_to_stream_event(
        self,
        input_type,
        expected_stream_type,
        content,
        tool_name,
        tool_input,
        agent,
        workflow_id
    ):
        """Test conversion of different ClaudeStreamEvent types to StreamEvent."""
        event = ClaudeStreamEvent(
            type=input_type,
            content=content,
            tool_name=tool_name,
            tool_input=tool_input
        )

        result = convert_to_stream_event(
            event=event,
            agent=agent,
            workflow_id=workflow_id
        )

        assert result is not None
        assert isinstance(result, StreamEvent)
        assert result.type == expected_stream_type
        assert result.content == content
        assert result.agent == agent
        assert result.workflow_id == workflow_id
        assert result.tool_name == tool_name
        assert result.tool_input == tool_input
        assert isinstance(result.timestamp, datetime)
        assert result.timestamp.tzinfo == UTC

    def test_error_event_returns_none(self):
        """Error event should return None (skipped)."""
        event = ClaudeStreamEvent(type="error", content="Something went wrong")

        result = convert_to_stream_event(
            event=event,
            agent="developer",
            workflow_id="wf-123"
        )

        assert result is None

    def test_system_event_returns_none(self):
        """System event should return None (skipped)."""
        event = ClaudeStreamEvent(type="system", content="System message")

        result = convert_to_stream_event(
            event=event,
            agent="developer",
            workflow_id="wf-123"
        )

        assert result is None

    def test_timestamp_generated_correctly(self):
        """Timestamp should be generated correctly within reasonable range."""
        event = ClaudeStreamEvent(
            type="tool_use",
            tool_name="run_shell_command",
            tool_input={"command": "pytest"}
        )

        before = datetime.now(UTC)
        result = convert_to_stream_event(
            event=event,
            agent="developer",
            workflow_id="wf-complete-123"
        )
        after = datetime.now(UTC)

        assert result is not None
        # Verify timestamp is within reasonable range
        assert before <= result.timestamp <= after
        assert result.timestamp.tzinfo == UTC

    @pytest.mark.parametrize("agent", ["developer", "architect", "reviewer"])
    def test_different_agents(self, agent):
        """Should work with different agent names."""
        event = ClaudeStreamEvent(type="assistant", content="Testing")

        result = convert_to_stream_event(
            event=event,
            agent=agent,
            workflow_id="wf-123"
        )
        assert result is not None
        assert result.agent == agent

    @pytest.mark.parametrize("workflow_id", ["wf-1", "workflow-abc-123", "uuid-style-id"])
    def test_different_workflow_ids(self, workflow_id):
        """Should preserve different workflow IDs."""
        event = ClaudeStreamEvent(type="assistant", content="Testing")

        result = convert_to_stream_event(
            event=event,
            agent="developer",
            workflow_id=workflow_id
        )
        assert result is not None
        assert result.workflow_id == workflow_id
