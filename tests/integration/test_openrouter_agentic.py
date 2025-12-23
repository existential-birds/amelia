# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Integration tests for OpenRouter agentic execution.

These tests require a valid OPENROUTER_API_KEY environment variable.
They make real API calls and incur costs, so they're skipped by default.
"""
import os

import pytest

from amelia.core.state import AgentMessage
from amelia.drivers.api.openai import ApiDriver


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)
class TestOpenRouterAgenticIntegration:
    """Integration tests requiring real OpenRouter API."""

    async def test_simple_shell_command(self, tmp_path):
        """Should execute a simple shell command via OpenRouter."""
        driver = ApiDriver(model="anthropic/claude-3.5-sonnet")

        events = []
        async for event in driver.execute_agentic(
            messages=[AgentMessage(role="user", content="Run 'echo hello' and tell me the output")],
            cwd=str(tmp_path),
            instructions="You are a helpful assistant. Use tools to complete tasks.",
        ):
            events.append(event)

        # Should have tool_use and result events
        event_types = [e.type for e in events]
        assert "tool_use" in event_types
        assert "result" in event_types

    async def test_file_write(self, tmp_path):
        """Should write a file via OpenRouter."""
        driver = ApiDriver(model="anthropic/claude-3.5-sonnet")

        events = []
        async for event in driver.execute_agentic(
            messages=[
                AgentMessage(
                    role="user",
                    content="Create a file called 'hello.txt' with the content 'Hello from OpenRouter!'"
                )
            ],
            cwd=str(tmp_path),
            instructions="You are a helpful assistant. Use tools to complete tasks.",
        ):
            events.append(event)

        # Verify file was created
        hello_file = tmp_path / "hello.txt"
        assert hello_file.exists(), "File should have been created"
        assert "Hello" in hello_file.read_text()

        # Should have tool_use and result events
        event_types = [e.type for e in events]
        assert "tool_use" in event_types
        assert "result" in event_types
