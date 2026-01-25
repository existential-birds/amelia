"""Tests for Architect agent agentic execution."""
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.agents.architect import Architect
from amelia.core.types import AgentConfig, Profile
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.pipelines.implementation.state import ImplementationState
from amelia.server.models.events import WorkflowEvent


class TestArchitectInitWithAgentConfig:
    """Tests for Architect initialization with AgentConfig."""

    def test_architect_init_with_agent_config(self):
        """Architect should accept AgentConfig and create its own driver."""
        config = AgentConfig(driver="cli", model="sonnet")

        with patch("amelia.agents.architect.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_get_driver.return_value = mock_driver

            architect = Architect(config)

            mock_get_driver.assert_called_once_with("cli", model="sonnet")
            assert architect.driver is mock_driver
            assert architect.options == {}


class TestArchitectPlanAsyncGenerator:
    """Tests for Architect.plan() as async generator."""

    @pytest.fixture
    def mock_agentic_driver(self) -> MagicMock:
        """Driver that supports execute_agentic."""
        driver = MagicMock()
        driver.execute_agentic = AsyncMock()
        return driver

    @pytest.fixture
    def state_with_issue(self, mock_issue_factory, mock_profile_factory) -> tuple[ImplementationState, Profile]:
        """ImplementationState with required issue."""
        issue = mock_issue_factory(title="Add feature", description="Add feature X")
        profile = mock_profile_factory()
        state = ImplementationState(
            workflow_id="test-workflow",
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            issue=issue,
        )
        return state, profile

    async def test_plan_returns_async_iterator(
        self,
        mock_agentic_driver: MagicMock,
        state_with_issue: tuple[ImplementationState, Profile],
    ) -> None:
        """plan() should return an async iterator."""
        state, profile = state_with_issue
        config = AgentConfig(driver="cli", model="sonnet")

        # Mock empty stream
        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[AgenticMessage]:
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="# Plan\n\n**Goal:** Test",
            )

        mock_agentic_driver.execute_agentic = mock_stream

        with patch("amelia.agents.architect.get_driver", return_value=mock_agentic_driver):
            architect = Architect(config)

            result = architect.plan(state, profile, workflow_id="wf-1")

            # Should be an async iterator, not a coroutine
            assert hasattr(result, "__aiter__")
            assert hasattr(result, "__anext__")

    async def test_plan_yields_state_and_event_tuples(
        self,
        mock_agentic_driver: MagicMock,
        state_with_issue: tuple[ImplementationState, Profile],
    ) -> None:
        """plan() should yield (ImplementationState, WorkflowEvent) tuples."""
        state, profile = state_with_issue
        config = AgentConfig(driver="cli", model="sonnet")

        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[AgenticMessage]:
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="read_file",
                tool_input={"path": "src/main.py"},
                tool_call_id="call-1",
            )
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="# Plan\n\n**Goal:** Test goal",
            )

        mock_agentic_driver.execute_agentic = mock_stream

        with patch("amelia.agents.architect.get_driver", return_value=mock_agentic_driver):
            architect = Architect(config)

            results = []
            async for new_state, event in architect.plan(state, profile, workflow_id="wf-1"):
                results.append((new_state, event))

            assert len(results) >= 1
            for new_state, event in results:
                assert isinstance(new_state, ImplementationState)
                assert isinstance(event, WorkflowEvent)


class TestArchitectCwdPassing:
    """Tests for working directory passing to execute_agentic."""

    async def test_plan_passes_working_dir_as_cwd(
        self,
        mock_driver,
        mock_issue_factory,
        mock_profile_factory,
        tmp_path,
    ) -> None:
        """Architect.plan() should pass profile.working_dir as cwd to execute_agentic."""
        issue = mock_issue_factory()
        # Use tmp_path as working_dir to verify it's passed correctly
        expected_cwd = str(tmp_path)
        profile = mock_profile_factory(working_dir=expected_cwd)
        state = ImplementationState(
            workflow_id="test-workflow",
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            issue=issue,
        )
        config = AgentConfig(driver="cli", model="sonnet")

        # Track the actual cwd passed to execute_agentic
        captured_cwd = None

        async def mock_stream(*args, **kwargs):
            nonlocal captured_cwd
            captured_cwd = kwargs.get("cwd")
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="**Goal:** Test",
            )

        mock_driver.execute_agentic = mock_stream

        with patch("amelia.agents.architect.get_driver", return_value=mock_driver):
            architect = Architect(config)

            async for _ in architect.plan(state, profile, workflow_id="wf-1"):
                pass

        assert captured_cwd == expected_cwd, (
            f"Expected cwd={expected_cwd}, got cwd={captured_cwd}. "
            "Architect is not passing working_dir correctly to execute_agentic."
        )



class TestArchitectToolCallAccumulation:
    """Tests for tool call/result accumulation during plan()."""

    async def test_accumulates_tool_calls_in_state(
        self,
        mock_driver,
        mock_issue_factory,
        mock_profile_factory,
    ) -> None:
        """Should accumulate tool calls in yielded state."""
        issue = mock_issue_factory()
        profile = mock_profile_factory()
        state = ImplementationState(
            workflow_id="test-workflow",
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            issue=issue,
        )
        config = AgentConfig(driver="cli", model="sonnet")

        async def mock_stream(*args, **kwargs):
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="read_file",
                tool_input={"path": "a.py"},
                tool_call_id="call-1",
            )
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="read_file",
                tool_output="content",
                tool_call_id="call-1",
            )
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="list_dir",
                tool_input={"path": "."},
                tool_call_id="call-2",
            )
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="**Goal:** Done",
            )

        mock_driver.execute_agentic = mock_stream

        with patch("amelia.agents.architect.get_driver", return_value=mock_driver):
            architect = Architect(config)

            final_state = None
            async for new_state, _ in architect.plan(state, profile, workflow_id="wf-1"):
                final_state = new_state

        assert final_state is not None
        assert len(final_state.tool_calls) == 2
        assert final_state.tool_calls[0].tool_name == "read_file"
        assert final_state.tool_calls[1].tool_name == "list_dir"
        assert len(final_state.tool_results) == 1


class TestArchitectDesignDocumentInPrompt:
    """Tests for design document inclusion in agentic prompt."""

    async def test_agentic_prompt_includes_design_document(
        self,
        mock_driver,
        mock_issue_factory,
        mock_profile_factory,
    ) -> None:
        """When state.design is present, it should be included in the prompt."""
        from amelia.core.types import Design

        issue = mock_issue_factory(title="Implement feature", description="Feature desc")
        profile = mock_profile_factory()
        design_content = "# Feature Design\n\nThis is the brainstorming output."
        state = ImplementationState(
            workflow_id="test-workflow",
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            issue=issue,
            design=Design(content=design_content, source="brainstorming"),
        )
        config = AgentConfig(driver="cli", model="sonnet")

        # Capture the prompt passed to execute_agentic
        captured_prompt = None

        async def mock_stream(*args, **kwargs):
            nonlocal captured_prompt
            captured_prompt = kwargs.get("prompt")
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="**Goal:** Test",
            )

        mock_driver.execute_agentic = mock_stream

        with patch("amelia.agents.architect.get_driver", return_value=mock_driver):
            architect = Architect(config)

            async for _ in architect.plan(state, profile, workflow_id="wf-1"):
                pass

        assert captured_prompt is not None
        assert "## Design Document" in captured_prompt
        assert design_content in captured_prompt

    async def test_agentic_prompt_excludes_design_when_none(
        self,
        mock_driver,
        mock_issue_factory,
        mock_profile_factory,
    ) -> None:
        """When state.design is None, no design section should appear."""
        issue = mock_issue_factory(title="Implement feature", description="Feature desc")
        profile = mock_profile_factory()
        state = ImplementationState(
            workflow_id="test-workflow",
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            issue=issue,
            design=None,
        )
        config = AgentConfig(driver="cli", model="sonnet")

        captured_prompt = None

        async def mock_stream(*args, **kwargs):
            nonlocal captured_prompt
            captured_prompt = kwargs.get("prompt")
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="**Goal:** Test",
            )

        mock_driver.execute_agentic = mock_stream

        with patch("amelia.agents.architect.get_driver", return_value=mock_driver):
            architect = Architect(config)

            async for _ in architect.plan(state, profile, workflow_id="wf-1"):
                pass

        assert captured_prompt is not None
        assert "## Design Document" not in captured_prompt
