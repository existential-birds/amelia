# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Integration tests for OpenRouter agentic execution.

These tests require a valid OPENROUTER_API_KEY environment variable.
They make real API calls to OpenRouter's free models, so no costs are incurred.

Note: Free models may be rate-limited or occasionally fail. These tests are marked
as integration tests and excluded from the default test run. Run explicitly with:
    pytest -m integration
"""
import os
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from amelia.drivers.api.deepagents import ApiDriver

from .conftest import OPENROUTER_FREE_MODEL


# Maximum retries for flaky free model API calls
MAX_RETRIES = 3


async def _execute_with_retry(
    driver: ApiDriver,
    prompt: str,
) -> list[BaseMessage]:
    """Execute agentic call with retry logic for flaky free models."""
    for attempt in range(MAX_RETRIES):
        messages: list[BaseMessage] = []
        async for message in driver.execute_agentic(prompt):
            messages.append(message)

        # Success if we got a ToolMessage (model used tools as expected)
        if any(isinstance(m, ToolMessage) for m in messages):
            return messages
        # If no tool use, retry
        if attempt < MAX_RETRIES - 1:
            continue

    # Return last attempt's messages for assertion
    return messages


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)
class TestOpenRouterAgenticIntegration:
    """Integration tests requiring real OpenRouter API.

    These tests use free models which may be rate-limited or occasionally skip
    tool calls. Retry logic is used to improve reliability.
    """

    async def test_simple_shell_command(self, tmp_path: Path) -> None:
        """Should execute a simple shell command via OpenRouter."""
        driver = ApiDriver(model=OPENROUTER_FREE_MODEL, cwd=str(tmp_path))

        messages = await _execute_with_retry(
            driver=driver,
            prompt="Run 'echo hello' and tell me the output",
        )

        # Should have AIMessage and ToolMessage
        has_ai_message = any(isinstance(m, AIMessage) for m in messages)
        has_tool_message = any(isinstance(m, ToolMessage) for m in messages)
        assert has_ai_message, f"Expected AIMessage, got: {[type(m).__name__ for m in messages]}"
        assert has_tool_message, f"Expected ToolMessage, got: {[type(m).__name__ for m in messages]}"

    async def test_file_write(self, tmp_path: Path) -> None:
        """Should write a file via OpenRouter."""
        driver = ApiDriver(model=OPENROUTER_FREE_MODEL, cwd=str(tmp_path))

        messages = await _execute_with_retry(
            driver=driver,
            prompt="Create a file called 'hello.txt' with the content 'Hello from OpenRouter!'",
        )

        # Verify file was created
        hello_file = tmp_path / "hello.txt"
        assert hello_file.exists(), "File should have been created"
        assert "Hello" in hello_file.read_text()

        # Should have AIMessage and ToolMessage
        has_ai_message = any(isinstance(m, AIMessage) for m in messages)
        has_tool_message = any(isinstance(m, ToolMessage) for m in messages)
        assert has_ai_message
        assert has_tool_message
