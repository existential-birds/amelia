"""Tests for Architect agent plan path in prompt."""

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest

from amelia.agents.architect import Architect
from amelia.core.state import ExecutionState
from amelia.core.types import Issue, Profile
from amelia.drivers.base import AgenticMessage, AgenticMessageType


class TestArchitectPlanPath:
    """Tests for plan path in architect prompt."""

    @pytest.fixture
    def mock_driver(self) -> MagicMock:
        """Create a mock driver."""
        return MagicMock()

    @pytest.fixture
    def state_and_profile(self) -> tuple[ExecutionState, Profile]:
        """Create state and profile for testing."""
        issue = Issue(id="TEST-123", title="Test Issue", description="Test description")
        profile = Profile(name="test", driver="cli:claude", model="sonnet")
        state = ExecutionState(profile_id="test", issue=issue)
        return state, profile

    def test_architect_agentic_prompt_includes_plan_path(
        self,
        mock_driver: MagicMock,
        state_and_profile: tuple[ExecutionState, Profile],
    ) -> None:
        """Prompt should include the resolved plan path with Write instruction."""
        state, profile = state_and_profile
        architect = Architect(driver=mock_driver)

        prompt = architect._build_agentic_prompt(state, profile)

        # Check path components
        assert "docs/plans/" in prompt
        assert "test-123" in prompt.lower()
        assert "Write your plan to" in prompt

    def test_architect_agentic_prompt_uses_todays_date(
        self,
        mock_driver: MagicMock,
        state_and_profile: tuple[ExecutionState, Profile],
    ) -> None:
        """Prompt should include today's date in the plan path."""
        state, profile = state_and_profile
        architect = Architect(driver=mock_driver)

        prompt = architect._build_agentic_prompt(state, profile)

        today = date.today().isoformat()
        assert today in prompt

    def test_architect_agentic_prompt_uses_custom_pattern(
        self,
        mock_driver: MagicMock,
    ) -> None:
        """Prompt should use custom plan_path_pattern from profile."""
        issue = Issue(id="JIRA-456", title="Test", description="Desc")
        profile = Profile(
            name="test",
            driver="cli:claude",
            model="sonnet",
            plan_path_pattern=".amelia/plans/{issue_key}.md",
        )
        state = ExecutionState(profile_id="test", issue=issue)
        architect = Architect(driver=mock_driver)

        prompt = architect._build_agentic_prompt(state, profile)

        assert ".amelia/plans/jira-456.md" in prompt

    async def test_plan_method_passes_profile_to_build_agentic_prompt(
        self,
        mock_driver: MagicMock,
        state_and_profile: tuple[ExecutionState, Profile],
    ) -> None:
        """Plan method should pass profile to _build_agentic_prompt."""
        state, profile = state_and_profile

        # Capture the prompt passed to execute_agentic
        captured_prompts: list[str] = []

        async def mock_execute_agentic(*args: Any, **kwargs: Any) -> Any:
            captured_prompts.append(kwargs.get("prompt", args[0] if args else ""))
            # Yield a result message to complete the generator
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Plan complete",
                session_id="session-1",
            )

        mock_driver.execute_agentic = mock_execute_agentic

        architect = Architect(driver=mock_driver)
        async for _ in architect.plan(state, profile, workflow_id="wf-1"):
            pass

        assert len(captured_prompts) == 1
        assert "docs/plans/" in captured_prompts[0]
        assert "test-123" in captured_prompts[0].lower()
