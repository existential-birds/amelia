# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for execute_agentic accepting list[AgentMessage] instead of string prompt."""

from unittest.mock import AsyncMock, patch

import pytest

from amelia.core.state import AgentMessage
from amelia.drivers.cli.claude import ClaudeCliDriver


class TestClaudeCliDriverAgenticMessages:
    """Tests for execute_agentic accepting list[AgentMessage]."""

    async def test_execute_agentic_accepts_messages_list(self, mock_subprocess_process_factory):
        """execute_agentic should accept list[AgentMessage] instead of string prompt."""
        driver = ClaudeCliDriver()
        messages = [
            AgentMessage(role="user", content="Implement feature X"),
            AgentMessage(role="assistant", content="I'll help with that."),
            AgentMessage(role="user", content="Make sure to add tests"),
        ]

        stream_lines = [
            b'{"type":"assistant","message":{"content":[{"type":"text","text":"Working..."}]}}\n',
            b'{"type":"result","session_id":"sess_001","subtype":"success"}\n',
            b""
        ]
        mock_process = mock_subprocess_process_factory(stdout_lines=stream_lines, return_code=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_exec:
            events = []
            async for event in driver.execute_agentic(messages, "/tmp"):
                events.append(event)

            # Verify the subprocess was called
            mock_exec.assert_called_once()

            # Verify prompt was properly constructed from messages (excluding system)
            assert mock_process.stdin.write.call_count == 1
            written_prompt = mock_process.stdin.write.call_args[0][0].decode()
            assert "USER: Implement feature X" in written_prompt
            assert "ASSISTANT: I'll help with that." in written_prompt
            assert "USER: Make sure to add tests" in written_prompt

            assert len(events) == 2
            assert events[0].type == "assistant"

    async def test_execute_agentic_with_explicit_system_prompt(self, mock_subprocess_process_factory):
        """execute_agentic should use explicit system_prompt parameter."""
        driver = ClaudeCliDriver()
        messages = [
            AgentMessage(role="user", content="Implement feature X"),
        ]

        stream_lines = [
            b'{"type":"assistant","message":{"content":[{"type":"text","text":"Working..."}]}}\n',
            b'{"type":"result","session_id":"sess_001","subtype":"success"}\n',
            b""
        ]
        mock_process = mock_subprocess_process_factory(stdout_lines=stream_lines, return_code=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_exec:
            events = []
            async for event in driver.execute_agentic(
                messages,
                "/tmp",
                system_prompt="You are a senior engineer."
            ):
                events.append(event)

            # Verify the system prompt was passed to CLI
            args = mock_exec.call_args[0]
            assert "--append-system-prompt" in args
            sys_idx = args.index("--append-system-prompt")
            assert args[sys_idx + 1] == "You are a senior engineer."

    async def test_execute_agentic_preserves_session_id(self, mock_subprocess_process_factory):
        """execute_agentic should still support session_id parameter."""
        driver = ClaudeCliDriver()
        messages = [AgentMessage(role="user", content="Continue from previous session")]

        stream_lines = [
            b'{"type":"assistant","message":{"content":[{"type":"text","text":"Resumed..."}]}}\n',
            b'{"type":"result","session_id":"sess_002","subtype":"success"}\n',
            b""
        ]
        mock_process = mock_subprocess_process_factory(stdout_lines=stream_lines, return_code=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_exec:
            events = []
            async for event in driver.execute_agentic(messages, "/tmp", session_id="sess_001"):
                events.append(event)

            args = mock_exec.call_args[0]
            assert "--resume" in args
            resume_idx = args.index("--resume")
            assert args[resume_idx + 1] == "sess_001"


class TestApiDriverAgenticMessages:
    """Tests for ApiDriver execute_agentic with messages."""

    async def test_execute_agentic_still_raises_not_implemented(self):
        """ApiDriver should still raise NotImplementedError for execute_agentic."""
        from amelia.drivers.api.openai import ApiDriver

        driver = ApiDriver()
        messages = [AgentMessage(role="user", content="Do something")]

        with pytest.raises(NotImplementedError, match="Agentic execution is not supported"):
            async for _ in driver.execute_agentic(messages, "/tmp"):
                pass
