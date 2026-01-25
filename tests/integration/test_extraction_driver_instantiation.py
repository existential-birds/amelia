"""Integration tests for extract_structured with real driver instantiation.

These tests verify that extract_structured() works correctly with the real
driver factory, ensuring that parameters like `cwd` are properly passed through
the entire chain: extract_structured() -> get_driver() -> ClaudeCliDriver.__init__().

The bug this tests for: ClaudeCliDriver.__init__() not accepting `cwd` parameter
while extract_structured() passes `cwd="."` to get_driver(). Unit tests that mock
get_driver() cannot catch this type of integration bug.
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from amelia.core.extraction import extract_structured


class SampleExtractionSchema(BaseModel):
    """Sample schema for extraction tests."""

    goal: str
    priority: int


@pytest.mark.integration
class TestExtractStructuredWithRealDriver:
    """Test extract_structured with real driver instantiation.

    These tests do NOT mock get_driver() - they let the real factory create
    the real driver instances. Only the external boundary (claude_agent_sdk.query)
    is mocked.
    """

    @pytest.fixture(autouse=True)
    def mock_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Set API key env var to allow ApiDriver construction if needed."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-for-integration-tests")

    async def test_extract_structured_with_cli_claude_driver_accepts_cwd(
        self,
    ) -> None:
        """extract_structured should work with cli driver without TypeError.

        This tests the full chain:
        - extract_structured() calls get_driver(driver_key="cli", cwd=".")
        - get_driver() passes cwd to ClaudeCliDriver(**kwargs)
        - ClaudeCliDriver.__init__() must accept the cwd parameter

        If ClaudeCliDriver.__init__() doesn't accept cwd, this test fails with:
        TypeError: ClaudeCliDriver.__init__() got an unexpected keyword argument 'cwd'

        We mock at the external boundary (claude_agent_sdk.query) to avoid making
        actual CLI calls, but the driver instantiation is real.
        """

        async def mock_query(**kwargs: Any) -> Any:
            """Mock claude_agent_sdk.query to return a valid result."""
            from claude_agent_sdk.types import ResultMessage

            # Yield a ResultMessage with structured output matching our schema
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="test-session",
                result="",
                structured_output={"goal": "Test goal from CLI", "priority": 1},
            )

        # Patch at the external boundary - the SDK's query function
        # This is the lowest level we can mock while still testing real instantiation
        with patch("amelia.drivers.cli.claude.query", side_effect=mock_query):
            # This call exercises the full chain:
            # extract_structured -> get_driver -> ClaudeCliDriver(model=..., cwd=".")
            result = await extract_structured(
                prompt="Extract from this text",
                schema=SampleExtractionSchema,
                model="sonnet",
                driver_type="cli",
            )

        # Verify the extraction worked
        assert result.goal == "Test goal from CLI"
        assert result.priority == 1

    async def test_extract_structured_with_api_driver_works(self) -> None:
        """extract_structured should work with api driver.

        This provides coverage parity and confirms the test pattern works
        for both driver types.
        """
        # Mock the deep agent's ainvoke method to return structured response
        mock_result = {
            "messages": [],
            "structured_response": SampleExtractionSchema(
                goal="Test goal from API", priority=2
            ),
        }

        # Mock at the agent ainvoke level - this is the external boundary for ApiDriver
        with patch(
            "amelia.drivers.api.deepagents.create_deep_agent",
        ) as mock_create_agent:
            mock_agent = AsyncMock()
            mock_agent.ainvoke = AsyncMock(return_value=mock_result)
            mock_create_agent.return_value = mock_agent

            result = await extract_structured(
                prompt="Extract from this text",
                schema=SampleExtractionSchema,
                model="anthropic/claude-sonnet-4",
                driver_type="api",
            )

        assert result.goal == "Test goal from API"
        assert result.priority == 2

    async def test_cli_driver_receives_cwd_parameter(self) -> None:
        """Verify ClaudeCliDriver is instantiated with cwd parameter.

        This test explicitly verifies that the cwd parameter reaches the
        ClaudeCliDriver constructor and is stored correctly.
        """

        async def mock_query(**kwargs: Any) -> Any:
            from claude_agent_sdk.types import ResultMessage

            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="test-session",
                result="",
                structured_output={"goal": "Verify cwd", "priority": 3},
            )

        captured_driver = None

        # We need to capture the driver instance while still using the real factory
        # Approach: patch the ClaudeCliDriver class to capture the instance
        from amelia.drivers.cli.claude import ClaudeCliDriver

        original_init = ClaudeCliDriver.__init__

        def capturing_init(
            self: Any,
            model: str = "sonnet",
            skip_permissions: bool = False,
            cwd: str | None = None,
        ) -> None:
            nonlocal captured_driver
            original_init(self, model=model, skip_permissions=skip_permissions, cwd=cwd)
            captured_driver = self

        with (
            patch("amelia.drivers.cli.claude.query", side_effect=mock_query),
            patch.object(ClaudeCliDriver, "__init__", capturing_init),
        ):
            await extract_structured(
                prompt="Test cwd passing",
                schema=SampleExtractionSchema,
                model="sonnet",
                driver_type="cli",
            )

        # Verify the driver was instantiated with cwd="."
        assert captured_driver is not None, "ClaudeCliDriver was not instantiated"
        assert captured_driver.cwd == ".", f"Expected cwd='.', got cwd={captured_driver.cwd!r}"
