"""Unit tests for Developer agent initialization."""
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from amelia.agents.developer import Developer
from amelia.core.agentic_state import ToolCall, ToolResult
from amelia.core.types import AgentConfig, SandboxConfig
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.pipelines.implementation.state import ImplementationState


def test_developer_init_with_agent_config() -> None:
    """Developer should accept AgentConfig and create its own driver."""
    config = AgentConfig(driver="api", model="anthropic/claude-sonnet-4")

    with patch("amelia.agents.developer.get_driver") as mock_get_driver:
        mock_driver = MagicMock()
        mock_get_driver.return_value = mock_driver

        developer = Developer(config)

        mock_get_driver.assert_called_once_with(
            "api",
            model="anthropic/claude-sonnet-4",
            sandbox_config=SandboxConfig(),
            profile_name="default",
            options={},
        )
        assert developer.driver is mock_driver
        assert developer.options == {}


def test_developer_init_with_options() -> None:
    """Developer should pass through options from AgentConfig."""
    config = AgentConfig(
        driver="cli",
        model="claude-sonnet-4-20250514",
        options={"max_iterations": 10},
    )

    with patch("amelia.agents.developer.get_driver") as mock_get_driver:
        mock_driver = MagicMock()
        mock_get_driver.return_value = mock_driver

        developer = Developer(config)

        assert developer.options == {"max_iterations": 10}


def test_developer_init_passes_sandbox_config() -> None:
    """Developer should pass sandbox_config and profile_name to get_driver."""
    sandbox = SandboxConfig(mode="container", image="custom:latest")
    config = AgentConfig(
        driver="api",
        model="test-model",
        sandbox=sandbox,
        profile_name="work",
        options={"max_iterations": 5},
    )

    with patch("amelia.agents.developer.get_driver") as mock_get_driver:
        mock_get_driver.return_value = MagicMock()
        Developer(config)

        mock_get_driver.assert_called_once_with(
            "api",
            model="test-model",
            sandbox_config=sandbox,
            profile_name="work",
            options={"max_iterations": 5},
        )


class TestDeveloperRunNoDoubleCount:
    """Verify Developer.run() returns only NEW tool calls/results, not accumulated ones from state.

    The bug was that Developer.run() used to initialize tool_calls = list(state.tool_calls)
    which copied existing state entries, causing double-counting when LangGraph's operator.add
    reducer appends the returned list to existing state. The fix changed it to tool_calls = []
    so only new entries are returned.
    """

    @pytest.fixture
    def state_with_existing_tool_data(
        self, mock_issue_factory, mock_profile_factory
    ) -> tuple[ImplementationState, Any]:
        """ImplementationState with pre-existing tool_calls and tool_results."""
        issue = mock_issue_factory(title="Implement feature", description="Feature desc")
        profile = mock_profile_factory()
        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            issue=issue,
            goal="implement feature",
            plan_markdown="# Plan\n\nImplement the feature.",
            tool_calls=[
                ToolCall(id="old-1", tool_name="read_file", tool_input={"path": "x.py"}),
            ],
            tool_results=[
                ToolResult(call_id="old-1", tool_name="read_file", output="content", success=True),
            ],
        )
        return state, profile

    async def test_run_returns_only_new_tool_calls_and_results(
        self,
        mock_driver,
        state_with_existing_tool_data,
    ) -> None:
        """Developer.run() should return only new tool calls/results, not pre-existing ones.

        When LangGraph uses operator.add to merge returned state into existing state,
        returning pre-existing entries would cause them to be duplicated.
        """
        state, profile = state_with_existing_tool_data
        config = AgentConfig(driver="cli", model="sonnet")

        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[AgenticMessage]:
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="bash",
                tool_input={"command": "ls"},
                tool_call_id="new-1",
            )
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="bash",
                tool_output="file.py",
                tool_call_id="new-1",
            )
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Done",
                session_id="sess-1",
            )

        mock_driver.execute_agentic = mock_stream

        with patch("amelia.agents.developer.get_driver", return_value=mock_driver):
            developer = Developer(config)

            final_state = None
            async for new_state, _event in developer.run(state, profile, workflow_id=uuid4()):
                final_state = new_state

        assert final_state is not None

        # Must contain ONLY the new tool call, not the pre-existing "old-1"
        assert len(final_state.tool_calls) == 1, (
            f"Expected 1 new tool call, got {len(final_state.tool_calls)}. "
            "Developer.run() may be copying pre-existing state.tool_calls."
        )
        assert final_state.tool_calls[0].id == "new-1"
        assert final_state.tool_calls[0].tool_name == "bash"

        # Must contain ONLY the new tool result, not the pre-existing "old-1"
        assert len(final_state.tool_results) == 1, (
            f"Expected 1 new tool result, got {len(final_state.tool_results)}. "
            "Developer.run() may be copying pre-existing state.tool_results."
        )
        assert final_state.tool_results[0].call_id == "new-1"
        assert final_state.tool_results[0].tool_name == "bash"
