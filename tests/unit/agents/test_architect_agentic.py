"""Tests for Architect agent agentic execution."""
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.agents.architect import Architect
from amelia.core.state import ExecutionState
from amelia.core.types import Profile, StreamEvent
from amelia.drivers.base import AgenticMessage, AgenticMessageType


class TestArchitectAgenticPrompt:
    """Tests for agentic architect system prompt."""

    def test_plan_prompt_includes_exploration_guidance(self, mock_driver) -> None:
        """System prompt should guide exploration before planning."""
        architect = Architect(mock_driver)
        prompt = architect.plan_prompt

        assert "read-only" in prompt.lower() or "exploration" in prompt.lower()
        assert "DO NOT modify" in prompt or "do not modify" in prompt.lower()

    def test_plan_prompt_emphasizes_references_over_code(self, mock_driver) -> None:
        """System prompt should emphasize file references over code examples."""
        architect = Architect(mock_driver)
        prompt = architect.plan_prompt

        assert "reference" in prompt.lower()
        assert "NOT to Include" in prompt or "What NOT" in prompt


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
        """plan() should yield (ExecutionState, StreamEvent) tuples."""
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
            assert isinstance(event, StreamEvent)
