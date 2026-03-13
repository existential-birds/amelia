"""Integration tests for OpenRouter agentic execution.

These tests require a valid OPENROUTER_API_KEY environment variable.
They make real API calls to OpenRouter's free models, so no costs are incurred.

Note: Free models may be rate-limited or occasionally fail. These tests are marked
as integration tests and excluded from the default test run. Run explicitly with:
    pytest -m integration
"""
import asyncio
import os
from pathlib import Path

import pytest

from amelia.core.exceptions import ModelProviderError
from amelia.drivers.api.deepagents import ApiDriver
from amelia.drivers.base import AgenticMessage, AgenticMessageType

from .conftest import OPENROUTER_FREE_MODEL


# Maximum retries for flaky free model API calls
MAX_RETRIES = 5


async def _execute_with_retry(
    driver: ApiDriver,
    prompt: str,
    cwd: str | None = None,
) -> list[AgenticMessage]:
    """Execute agentic call with retry logic for flaky free models."""
    effective_cwd = cwd or driver.cwd or "."
    messages: list[AgenticMessage] = []
    for attempt in range(MAX_RETRIES):
        messages = []
        try:
            async for message in driver.execute_agentic(prompt, cwd=effective_cwd):
                messages.append(message)
        except (ModelProviderError, RuntimeError) as exc:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(min(2 ** (attempt + 2), 30))
                continue
            # Free models are frequently rate-limited or quota-exceeded; skip rather than fail
            exc_str = str(exc).lower()
            if "429" in str(exc) or "402" in str(exc) or "rate" in exc_str or "limit" in exc_str:
                pytest.skip(f"OpenRouter free model unavailable after {MAX_RETRIES} retries: {exc}")
            raise

        # Success if we got a tool call (model used tools as expected)
        if any(m.type == AgenticMessageType.TOOL_CALL for m in messages):
            return messages
        # If no tool use, retry
        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(1)
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

        # Should have TOOL_CALL and RESULT messages
        has_tool_call = any(m.type == AgenticMessageType.TOOL_CALL for m in messages)
        has_result = any(m.type == AgenticMessageType.RESULT for m in messages)
        assert has_tool_call, f"Expected TOOL_CALL, got: {[m.type for m in messages]}"
        assert has_result, f"Expected RESULT, got: {[m.type for m in messages]}"

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

        # Should have TOOL_CALL and RESULT messages
        has_tool_call = any(m.type == AgenticMessageType.TOOL_CALL for m in messages)
        has_result = any(m.type == AgenticMessageType.RESULT for m in messages)
        assert has_tool_call
        assert has_result
