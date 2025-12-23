# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for driver interface compliance."""
import inspect

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from amelia.core.state import AgentMessage
from amelia.drivers.api.openai import ApiDriver
from amelia.drivers.cli.claude import ClaudeCliDriver


class TestInterfaceCompliance:
    """Test both drivers implement execute_agentic correctly."""

    def test_api_driver_accepts_required_parameters(self, monkeypatch):
        """ApiDriver.execute_agentic should accept all interface parameters."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        driver = ApiDriver(model="openai:gpt-4o")

        # Verify the method signature includes all required parameters
        sig = inspect.signature(driver.execute_agentic)
        assert "messages" in sig.parameters, "execute_agentic must accept 'messages' parameter"
        assert "cwd" in sig.parameters, "execute_agentic must accept 'cwd' parameter"
        assert "session_id" in sig.parameters, "execute_agentic must accept 'session_id' parameter"
        assert "instructions" in sig.parameters, "execute_agentic must accept 'instructions' parameter"

    def test_claude_driver_accepts_required_parameters(self):
        """ClaudeCliDriver.execute_agentic should accept all interface parameters."""
        driver = ClaudeCliDriver()

        # Verify the method signature includes all required parameters
        sig = inspect.signature(driver.execute_agentic)
        assert "messages" in sig.parameters, "execute_agentic must accept 'messages' parameter"
        assert "cwd" in sig.parameters, "execute_agentic must accept 'cwd' parameter"
        assert "session_id" in sig.parameters, "execute_agentic must accept 'session_id' parameter"
        assert "instructions" in sig.parameters, "execute_agentic must accept 'instructions' parameter"

    def test_claude_driver_does_not_use_system_prompt_parameter(self):
        """ClaudeCliDriver.execute_agentic should NOT have system_prompt parameter."""
        driver = ClaudeCliDriver()

        # Verify the old system_prompt parameter is removed
        sig = inspect.signature(driver.execute_agentic)
        assert "system_prompt" not in sig.parameters, \
            "execute_agentic must NOT have 'system_prompt' parameter - use 'instructions' instead"

    async def test_api_driver_uses_instructions_not_system_messages(self, monkeypatch, tmp_path):
        """ApiDriver should use instructions parameter, not extract from system messages."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        driver = ApiDriver(model="openai:gpt-4o")

        with patch("amelia.drivers.api.openai.Agent") as mock_agent_class:
            mock_run = AsyncMock()
            mock_run.result = MagicMock(output="Done")
            mock_run.__aenter__ = AsyncMock(return_value=mock_run)
            mock_run.__aexit__ = AsyncMock(return_value=None)
            mock_run.__aiter__ = lambda self: iter([])

            mock_agent = MagicMock()
            mock_agent.iter = MagicMock(return_value=mock_run)
            mock_agent_class.return_value = mock_agent

            # Execute with instructions parameter
            async for _ in driver.execute_agentic(
                messages=[AgentMessage(role="user", content="test")],
                cwd=str(tmp_path),
                instructions="Be helpful",
            ):
                pass

            # Verify instructions was passed to agent.iter
            mock_agent.iter.assert_called_once()
            call_kwargs = mock_agent.iter.call_args.kwargs
            assert call_kwargs.get("instructions") == "Be helpful"
