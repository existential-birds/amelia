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
from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverUsage
from amelia.pipelines.implementation.context_compaction import COMPACTION_MARKER_TOOL_NAME
from amelia.pipelines.implementation.state import ImplementationState


def test_developer_init_with_agent_config() -> None:
    """Developer should accept AgentConfig and create its own driver."""
    config = AgentConfig(driver="api", model="anthropic/claude-sonnet-4")

    with patch("amelia.agents._driver_init.get_driver") as mock_get_driver:
        mock_driver = MagicMock()
        mock_get_driver.return_value = mock_driver

        developer = Developer(config)

        mock_get_driver.assert_called_once_with(
            "api",
            model="anthropic/claude-sonnet-4",
            sandbox_config=SandboxConfig(),
            sandbox_provider=None,
            profile_name="default",
            options={},
        )
        assert developer.driver is mock_driver
        assert developer.options == {}


def test_developer_init_with_options() -> None:
    """Developer should pass through options from AgentConfig."""
    config = AgentConfig(
        driver="claude",
        model="claude-sonnet-4-20250514",
        options={"max_iterations": 10},
    )

    with patch("amelia.agents._driver_init.get_driver") as mock_get_driver:
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

    with patch("amelia.agents._driver_init.get_driver") as mock_get_driver:
        mock_get_driver.return_value = MagicMock()
        Developer(config)

        mock_get_driver.assert_called_once_with(
            "api",
            model="test-model",
            sandbox_config=sandbox,
            sandbox_provider=None,
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
        config = AgentConfig(driver="claude", model="sonnet")

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

        with patch("amelia.agents._driver_init.get_driver", return_value=mock_driver):
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

    async def test_run_compacts_when_context_utilization_crosses_threshold(
        self,
        mock_driver,
        state_with_existing_tool_data,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Developer.run() should compact returned state and emit a visible event."""
        state, profile = state_with_existing_tool_data
        state = state.model_copy(update={
            "tool_calls": [
                ToolCall(id=f"old-{i}", tool_name="read_file", tool_input={"path": f"{i}.py"})
                for i in range(6)
            ],
            "tool_results": [
                ToolResult(
                    call_id=f"old-{i}",
                    tool_name="read_file",
                    output=f"old output {i}",
                    success=True,
                )
                for i in range(6)
            ],
        })
        monkeypatch.setenv("AMELIA_CONTEXT_COMPACTION_THRESHOLD", "0.8")
        monkeypatch.setenv("AMELIA_CONTEXT_KEEP_LAST_TURNS", "2")

        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[AgenticMessage]:
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="bash",
                tool_input={"command": "true"},
                tool_call_id="new-1",
            )
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="bash",
                tool_output="ok",
                tool_call_id="new-1",
            )
            yield AgenticMessage(type=AgenticMessageType.RESULT, content="Done", session_id="sess-1")

        mock_driver.execute_agentic = mock_stream
        mock_driver.get_usage.return_value = DriverUsage(context_utilization=0.9)
        config = AgentConfig(driver="claude", model="sonnet")

        yielded = []
        with patch("amelia.agents._driver_init.get_driver", return_value=mock_driver):
            developer = Developer(config)
            async for item in developer.run(state, profile, workflow_id=state.workflow_id):
                yielded.append(item)

        compacted_state, compaction_event = yielded[-1]
        assert compaction_event.event_type == "context_compacted"
        assert any(
            result.tool_name == COMPACTION_MARKER_TOOL_NAME
            for result in compacted_state.tool_results
        )
        assert len(compacted_state.tool_results) < 7


async def test_developer_passes_allowed_tools_when_tool_context_set(
    mock_issue_factory,
    mock_profile_factory,
) -> None:
    """With a ToolContext, Developer.run resolves the developer profile and
    passes allowed_tools + tool_context to execute_agentic."""
    from amelia.tools.registry import ToolContext
    from amelia.tools.registry.registry import discover_builtin_tools

    discover_builtin_tools()
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
    )
    config = AgentConfig(driver="api", model="anthropic/claude-sonnet-4")

    captured: dict[str, Any] = {}

    async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[AgenticMessage]:
        captured.update(kwargs)
        yield AgenticMessage(type=AgenticMessageType.RESULT, content="done", session_id="s")

    mock_driver = MagicMock()
    mock_driver.execute_agentic = mock_stream

    with patch("amelia.agents._driver_init.get_driver", return_value=mock_driver):
        developer = Developer(config, tool_context=ToolContext(cwd="/tmp"))
        async for _ in developer.run(state, profile, workflow_id=uuid4()):
            pass

    assert "allowed_tools" in captured
    assert captured["allowed_tools"] is not None
    # The developer profile includes the vcs + quality toolsets.
    assert "git_diff" in captured["allowed_tools"]
    assert "run_tests" in captured["allowed_tools"]
    # tool_context is forwarded so factory tools can resolve.
    assert captured.get("tool_context") is not None


async def test_developer_omits_allowed_tools_without_tool_context(
    mock_issue_factory,
    mock_profile_factory,
) -> None:
    """Without a ToolContext, Developer.run must NOT restrict tools (backward compat)."""
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
    )
    config = AgentConfig(driver="api", model="anthropic/claude-sonnet-4")

    captured: dict[str, Any] = {}

    async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[AgenticMessage]:
        captured.update(kwargs)
        yield AgenticMessage(type=AgenticMessageType.RESULT, content="done", session_id="s")

    mock_driver = MagicMock()
    mock_driver.execute_agentic = mock_stream

    with patch("amelia.agents._driver_init.get_driver", return_value=mock_driver):
        developer = Developer(config)
        async for _ in developer.run(state, profile, workflow_id=uuid4()):
            pass

    assert "allowed_tools" not in captured or captured.get("allowed_tools") is None


class TestDeveloperCompactionConfigValidation:
    """Developer.run() parses compaction env config eagerly with validation."""

    def test_invalid_threshold_raises_value_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from amelia.agents.developer import _parse_compaction_threshold

        monkeypatch.setenv("AMELIA_CONTEXT_COMPACTION_THRESHOLD", "not-a-number")
        with pytest.raises(ValueError, match="AMELIA_CONTEXT_COMPACTION_THRESHOLD"):
            _parse_compaction_threshold()

        monkeypatch.setenv("AMELIA_CONTEXT_COMPACTION_THRESHOLD", "1.5")
        with pytest.raises(ValueError, match=r"\(0, 1\]"):
            _parse_compaction_threshold()

        monkeypatch.setenv("AMELIA_CONTEXT_COMPACTION_THRESHOLD", "0")
        with pytest.raises(ValueError, match=r"\(0, 1\]"):
            _parse_compaction_threshold()

    def test_invalid_keep_last_raises_value_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from amelia.agents.developer import _parse_keep_last_turns

        monkeypatch.setenv("AMELIA_CONTEXT_KEEP_LAST_TURNS", "not-an-int")
        with pytest.raises(ValueError, match="AMELIA_CONTEXT_KEEP_LAST_TURNS"):
            _parse_keep_last_turns()

        monkeypatch.setenv("AMELIA_CONTEXT_KEEP_LAST_TURNS", "0")
        with pytest.raises(ValueError, match=">= 1"):
            _parse_keep_last_turns()

        monkeypatch.setenv("AMELIA_CONTEXT_KEEP_LAST_TURNS", "-3")
        with pytest.raises(ValueError, match=">= 1"):
            _parse_keep_last_turns()

    def test_valid_config_parses(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from amelia.agents.developer import _parse_compaction_threshold, _parse_keep_last_turns

        monkeypatch.setenv("AMELIA_CONTEXT_COMPACTION_THRESHOLD", "0.9")
        monkeypatch.setenv("AMELIA_CONTEXT_KEEP_LAST_TURNS", "4")
        assert _parse_compaction_threshold() == 0.9
        assert _parse_keep_last_turns() == 4
