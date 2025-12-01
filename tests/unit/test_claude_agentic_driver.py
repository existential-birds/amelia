"""Tests for ClaudeAgenticCliDriver."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.drivers.cli.agentic import ClaudeAgenticCliDriver


class TestClaudeAgenticCliDriver:
    """Tests for ClaudeAgenticCliDriver."""

    @pytest.fixture
    def agentic_driver(self):
        return ClaudeAgenticCliDriver()

    @pytest.fixture
    def agentic_stream_lines(self):
        """Stream output including tool execution."""
        return [
            b'{"type":"assistant","message":{"content":[{"type":"text","text":"Let me read the file"}]}}\n',
            b'{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"/test.py"}}]}}\n',
            b'{"type":"assistant","message":{"content":[{"type":"text","text":"The file contains..."}]}}\n',
            b'{"type":"result","session_id":"agentic_sess_001","subtype":"success"}\n',
            b''
        ]

    @pytest.mark.asyncio
    async def test_execute_agentic_uses_skip_permissions(self, agentic_driver, agentic_stream_lines):
        """Test that execute_agentic uses --dangerously-skip-permissions."""
        mock_process = AsyncMock()
        mock_process.stdin = MagicMock()
        mock_process.stdin.drain = AsyncMock()
        mock_process.stdout.readline = AsyncMock(side_effect=agentic_stream_lines)
        mock_process.stderr.read = AsyncMock(return_value=b"")
        mock_process.returncode = 0
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_exec:
            events = []
            async for event in agentic_driver.execute_agentic(
                prompt="Read the test file",
                cwd="/workspace"
            ):
                events.append(event)

            args = mock_exec.call_args[0]
            assert "--dangerously-skip-permissions" in args

    @pytest.mark.asyncio
    async def test_execute_agentic_tracks_tool_calls(self, agentic_driver, agentic_stream_lines):
        """Test that tool calls are tracked in history."""
        mock_process = AsyncMock()
        mock_process.stdin = MagicMock()
        mock_process.stdin.drain = AsyncMock()
        mock_process.stdout.readline = AsyncMock(side_effect=agentic_stream_lines)
        mock_process.stderr.read = AsyncMock(return_value=b"")
        mock_process.returncode = 0
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            async for _ in agentic_driver.execute_agentic(
                prompt="Read the test file",
                cwd="/workspace"
            ):
                pass

            assert len(agentic_driver.tool_call_history) == 1
            assert agentic_driver.tool_call_history[0].tool_name == "Read"
