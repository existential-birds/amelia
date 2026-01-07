"""Tests for Architect agent agentic execution."""
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.agents.architect import Architect
from amelia.core.state import ExecutionState
from amelia.core.types import Profile
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.server.models.events import WorkflowEvent


class TestArchitectPlanAsyncGenerator:
    """Tests for Architect.plan() as async generator."""

    @pytest.fixture
    def mock_agentic_driver(self) -> MagicMock:
        """Driver that supports execute_agentic."""
        driver = MagicMock()
        driver.execute_agentic = AsyncMock()
        return driver

    @pytest.fixture
    def state_with_issue(self, mock_issue_factory, mock_profile_factory) -> tuple[ExecutionState, Profile]:
        """ExecutionState with required issue."""
        issue = mock_issue_factory(title="Add feature", description="Add feature X")
        profile = mock_profile_factory()
        state = ExecutionState(profile_id="test", issue=issue)
        return state, profile

    async def test_plan_returns_async_iterator(
        self,
        mock_agentic_driver: MagicMock,
        state_with_issue: tuple[ExecutionState, Profile],
    ) -> None:
        """plan() should return an async iterator."""
        state, profile = state_with_issue

        # Mock empty stream
        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[AgenticMessage]:
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="# Plan\n\n**Goal:** Test",
            )

        mock_agentic_driver.execute_agentic = mock_stream
        architect = Architect(mock_agentic_driver)

        result = architect.plan(state, profile, workflow_id="wf-1")

        # Should be an async iterator, not a coroutine
        assert hasattr(result, "__aiter__")
        assert hasattr(result, "__anext__")

    async def test_plan_yields_state_and_event_tuples(
        self,
        mock_agentic_driver: MagicMock,
        state_with_issue: tuple[ExecutionState, Profile],
    ) -> None:
        """plan() should yield (ExecutionState, WorkflowEvent) tuples."""
        state, profile = state_with_issue

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
        architect = Architect(mock_agentic_driver)

        results = []
        async for new_state, event in architect.plan(state, profile, workflow_id="wf-1"):
            results.append((new_state, event))

        assert len(results) >= 1
        for new_state, event in results:
            assert isinstance(new_state, ExecutionState)
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
        state = ExecutionState(profile_id="test", issue=issue)

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
        architect = Architect(mock_driver)

        async for _ in architect.plan(state, profile, workflow_id="wf-1"):
            pass

        assert captured_cwd == expected_cwd, (
            f"Expected cwd={expected_cwd}, got cwd={captured_cwd}. "
            "Architect is not passing working_dir correctly to execute_agentic."
        )

    async def test_plan_uses_dot_when_working_dir_is_none(
        self,
        mock_driver,
        mock_issue_factory,
        mock_profile_factory,
    ) -> None:
        """Architect.plan() should use '.' as cwd when profile.working_dir is None."""
        issue = mock_issue_factory()
        # Explicitly set working_dir to None
        profile = mock_profile_factory(working_dir=None)
        state = ExecutionState(profile_id="test", issue=issue)

        captured_cwd = None

        async def mock_stream(*args, **kwargs):
            nonlocal captured_cwd
            captured_cwd = kwargs.get("cwd")
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="**Goal:** Test",
            )

        mock_driver.execute_agentic = mock_stream
        architect = Architect(mock_driver)

        async for _ in architect.plan(state, profile, workflow_id="wf-1"):
            pass

        assert captured_cwd == ".", (
            f"Expected cwd='.', got cwd={captured_cwd}. "
            "Architect should fallback to '.' when working_dir is None."
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
        state = ExecutionState(profile_id="test", issue=issue)

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
        architect = Architect(mock_driver)

        final_state = None
        async for new_state, _ in architect.plan(state, profile, workflow_id="wf-1"):
            final_state = new_state

        assert final_state is not None
        assert len(final_state.tool_calls) == 2
        assert final_state.tool_calls[0].tool_name == "read_file"
        assert final_state.tool_calls[1].tool_name == "list_dir"
        assert len(final_state.tool_results) == 1
