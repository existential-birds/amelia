"""Integration tests verifying agents work correctly with multiple drivers.

This module tests that agents (Developer, Reviewer) produce consistent behavior
regardless of which driver implementation is used (cli:claude, api:openrouter).
These tests replace the low-value static import tests in test_agent_imports.py
by actually verifying the driver abstraction works at runtime.
"""

from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.agents.reviewer import ReviewResponse
from amelia.core.orchestrator import call_developer_node, call_reviewer_node
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from tests.integration.conftest import (
    make_agentic_messages,
    make_config,
    make_execution_state,
    make_profile,
)


@pytest.fixture(autouse=True)
def mock_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set API key env var to allow driver construction."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-for-integration-tests")


# Driver configurations for parametrized tests
DRIVER_CONFIGS = [
    pytest.param(
        "api:openrouter",
        "openrouter:anthropic/claude-sonnet-4",
        id="api-openrouter",
    ),
    pytest.param(
        "cli:claude",
        "sonnet",
        id="cli-claude",
    ),
]


@pytest.mark.integration
class TestDeveloperMultiDriver:
    """Test Developer agent works identically with different drivers."""

    @pytest.mark.parametrize("driver_key,model", DRIVER_CONFIGS)
    async def test_developer_collects_tool_calls_from_any_driver(
        self,
        tmp_path: Path,
        driver_key: str,
        model: str,
    ) -> None:
        """Developer should collect tool calls regardless of driver type.

        Both cli:claude and api:openrouter drivers yield AgenticMessage objects.
        The Developer agent processes these uniformly - this test verifies that
        the abstraction works correctly for both driver implementations.
        """
        profile = make_profile(
            driver=driver_key,
            model=model,
            working_dir=str(tmp_path),
        )
        state = make_execution_state(
            profile=profile,
            goal="Create a hello.txt file with 'Hello World'",
        )
        config = make_config(thread_id=f"test-{driver_key}", profile=profile)

        mock_messages = make_agentic_messages(
            final_text="I created hello.txt with the content 'Hello World'"
        )

        async def mock_execute_agentic(*_args: Any, **_kwargs: Any) -> Any:
            """Mock async generator yielding AgenticMessage objects."""
            for msg in mock_messages:
                yield msg

        # Patch at the driver interface level - both drivers use execute_agentic
        if driver_key.startswith("api:"):
            patch_target = "amelia.drivers.api.deepagents.ApiDriver.execute_agentic"
        else:
            patch_target = "amelia.drivers.cli.claude.ClaudeCliDriver.execute_agentic"

        with patch(patch_target, mock_execute_agentic):
            result = await call_developer_node(state, cast(RunnableConfig, config))

        # Verify Developer processed the AgenticMessages correctly
        assert result["agentic_status"] == "completed"
        assert len(result["tool_calls"]) >= 1
        assert result["tool_calls"][0].tool_name == "write_file"
        assert "hello.txt" in result["final_response"]

    @pytest.mark.parametrize("driver_key,model", DRIVER_CONFIGS)
    async def test_developer_handles_error_messages_from_any_driver(
        self,
        tmp_path: Path,
        driver_key: str,
        model: str,
    ) -> None:
        """Developer should handle error messages consistently across drivers."""
        profile = make_profile(
            driver=driver_key,
            model=model,
            working_dir=str(tmp_path),
        )
        state = make_execution_state(
            profile=profile,
            goal="Read a non-existent file",
        )
        config = make_config(thread_id=f"test-error-{driver_key}", profile=profile)

        error_messages = [
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="read_file",
                tool_input={"path": "/nonexistent.txt"},
                tool_call_id="tool-err-1",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="read_file",
                tool_output="Error: File not found",
                is_error=True,
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="I encountered an error: the file does not exist.",
                session_id="session-err",
            ),
        ]

        async def mock_execute_agentic(*_args: Any, **_kwargs: Any) -> Any:
            for msg in error_messages:
                yield msg

        if driver_key.startswith("api:"):
            patch_target = "amelia.drivers.api.deepagents.ApiDriver.execute_agentic"
        else:
            patch_target = "amelia.drivers.cli.claude.ClaudeCliDriver.execute_agentic"

        with patch(patch_target, mock_execute_agentic):
            result = await call_developer_node(state, cast(RunnableConfig, config))

        # Verify error was captured but execution completed
        assert result["agentic_status"] == "completed"
        assert any(tc.tool_name == "read_file" for tc in result["tool_calls"])


@pytest.mark.integration
class TestReviewerMultiDriver:
    """Test Reviewer agent works identically with different drivers."""

    @pytest.mark.parametrize("driver_key,model", DRIVER_CONFIGS)
    async def test_reviewer_returns_structured_response_from_any_driver(
        self,
        tmp_path: Path,
        driver_key: str,
        model: str,
    ) -> None:
        """Reviewer should return ReviewResult regardless of driver type.

        The Reviewer uses driver.generate() with a schema.
        Both drivers should return the same structured ReviewResponse.
        Mock at driver.generate() level - the correct integration boundary.
        """
        profile = make_profile(
            driver=driver_key,
            model=model,
            working_dir=str(tmp_path),
        )
        state = make_execution_state(
            profile=profile,
            goal="Add logging to the application",
            code_changes_for_review="diff --git a/app.py b/app.py\n+import logging",
        )
        config = make_config(thread_id=f"test-review-{driver_key}", profile=profile)

        mock_response = ReviewResponse(
            approved=True,
            comments=["LGTM! Good use of standard logging module."],
            severity="low",
        )

        # Mock at driver.generate() level - returns (output, session_id)
        if driver_key.startswith("api:"):
            patch_target = "amelia.drivers.api.deepagents.ApiDriver.generate"
        else:
            patch_target = "amelia.drivers.cli.claude.ClaudeCliDriver.generate"

        with patch(patch_target, new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = (mock_response, "session-123")
            result = await call_reviewer_node(state, cast(RunnableConfig, config))

        assert result["last_review"] is not None
        assert result["last_review"].approved is True
        assert "LGTM" in result["last_review"].comments[0]

    @pytest.mark.parametrize("driver_key,model", DRIVER_CONFIGS)
    async def test_reviewer_rejection_from_any_driver(
        self,
        tmp_path: Path,
        driver_key: str,
        model: str,
    ) -> None:
        """Reviewer rejection should work consistently across drivers."""
        profile = make_profile(
            driver=driver_key,
            model=model,
            working_dir=str(tmp_path),
        )
        state = make_execution_state(
            profile=profile,
            goal="Implement authentication",
            code_changes_for_review="diff --git a/auth.py\n+password = 'hardcoded'",
        )
        config = make_config(thread_id=f"test-reject-{driver_key}", profile=profile)

        mock_response = ReviewResponse(
            approved=False,
            comments=["Critical: Hardcoded password. Use environment variables."],
            severity="critical",
        )

        # Mock at driver.generate() level
        if driver_key.startswith("api:"):
            patch_target = "amelia.drivers.api.deepagents.ApiDriver.generate"
        else:
            patch_target = "amelia.drivers.cli.claude.ClaudeCliDriver.generate"

        with patch(patch_target, new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = (mock_response, "session-456")
            result = await call_reviewer_node(state, cast(RunnableConfig, config))

        assert result["last_review"] is not None
        assert result["last_review"].approved is False
        assert result["last_review"].severity == "critical"
