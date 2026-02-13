"""Unit tests for Developer prompt building with task extraction."""

from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from amelia.agents.developer import Developer
from amelia.core.types import AgentConfig, Issue, Profile
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.pipelines.implementation.state import ImplementationState
from tests.conftest import create_mock_execute_agentic


@pytest.fixture
def mock_developer() -> Developer:
    """Create a Developer with a mocked driver for prompt tests."""
    config = AgentConfig(driver="api", model="test-model")
    with patch("amelia.agents.developer.get_driver") as mock_get_driver:
        mock_get_driver.return_value = MagicMock()
        return Developer(config)


@pytest.fixture
def multi_task_plan() -> str:
    """A plan with header and 3 tasks."""
    return """# Implementation Plan

## Goal
Build a feature with multiple tasks.

## Architecture
Modular design with clear separation.

## Tech Stack
Python, pytest

---

## Phase 1: Foundation

### Task 1: Create module

Create the base module structure.

### Task 2: Add validation

Add input validation logic.

## Phase 2: Testing

### Task 3: Write tests

Add comprehensive test coverage.
"""


class TestDeveloperBuildPrompt:
    """Tests for Developer._build_prompt task extraction."""

    def test_single_task_uses_full_plan(self, mock_developer: Developer) -> None:
        """When total_tasks is 1, use full plan without extraction."""
        state = ImplementationState(
            workflow_id="test-workflow",
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            goal="Implement feature",
            plan_markdown="# Simple Plan\n\nJust do the thing.",
            total_tasks=1,
            current_task_index=0,
        )
        prompt = mock_developer._build_prompt(state)

        assert "# Simple Plan" in prompt
        assert "Just do the thing." in prompt

    def test_multi_task_extracts_current_section(
        self, mock_developer: Developer, multi_task_plan: str
    ) -> None:
        """For multi-task execution, extract only the current task section."""
        state = ImplementationState(
            workflow_id="test-workflow",
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            goal="Implement feature",
            plan_markdown=multi_task_plan,
            total_tasks=3,
            current_task_index=1,  # Task 2 (0-indexed)
        )
        prompt = mock_developer._build_prompt(state)

        # Should contain Task 2 content
        assert "Task 2" in prompt
        assert "Add validation" in prompt
        # Should NOT contain other tasks
        assert "Task 1:" not in prompt and "### Task 1:" not in prompt
        assert "Task 3:" not in prompt and "### Task 3:" not in prompt

    def test_multi_task_includes_breadcrumb(
        self, mock_developer: Developer, multi_task_plan: str
    ) -> None:
        """Breadcrumb shows task progress for context."""
        state = ImplementationState(
            workflow_id="test-workflow",
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            goal="Implement feature",
            plan_markdown=multi_task_plan,
            total_tasks=3,
            current_task_index=2,  # Task 3 (0-indexed)
        )
        prompt = mock_developer._build_prompt(state)

        # Should show progress breadcrumb
        assert "Tasks 1-2 of 3 completed" in prompt
        assert "Task 3" in prompt

    def test_first_task_breadcrumb(
        self, mock_developer: Developer, multi_task_plan: str
    ) -> None:
        """First task shows appropriate breadcrumb."""
        state = ImplementationState(
            workflow_id="test-workflow",
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            goal="Implement feature",
            plan_markdown=multi_task_plan,
            total_tasks=3,
            current_task_index=0,  # Task 1 (0-indexed)
        )
        prompt = mock_developer._build_prompt(state)

        # First task breadcrumb
        assert "Executing Task 1 of 3" in prompt
        # Should NOT say "completed"
        assert "completed" not in prompt.lower()

    def test_missing_plan_raises_error(self, mock_developer: Developer) -> None:
        """Developer requires plan_markdown from Architect."""
        state = ImplementationState(
            workflow_id="test-workflow",
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            goal="Implement feature",
            plan_markdown=None,
        )

        with pytest.raises(ValueError, match="requires plan_markdown"):
            mock_developer._build_prompt(state)


class TestDeveloperSystemPrompt:
    """Tests for Developer system prompt injection to drivers."""

    @pytest.mark.asyncio
    async def test_run_passes_custom_system_prompt_to_driver(
        self,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Developer.run should pass configured prompt as driver instructions."""
        config = AgentConfig(driver="api", model="test-model")
        profile: Profile = mock_profile_factory()
        captured_kwargs: list[dict[str, object]] = []
        custom_prompt = "Custom Amelia developer system prompt"

        with patch("amelia.agents.developer.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_driver.execute_agentic = create_mock_execute_agentic(
                [
                    AgenticMessage(
                        type=AgenticMessageType.RESULT,
                        content="Done",
                        session_id="session-1",
                    )
                ],
                capture_kwargs=captured_kwargs,
            )
            mock_get_driver.return_value = mock_driver
            developer = Developer(config, prompts={"developer.system": custom_prompt})

        state = ImplementationState(
            workflow_id="test-workflow",
            created_at=datetime.now(UTC),
            status="running",
            profile_id=profile.name,
            issue=Issue(id="TEST-1", title="Test", description="Test"),
            goal="Implement feature",
            plan_markdown="# Plan\n\nDo work",
        )

        async for _state_update, _event in developer.run(state, profile, "wf-test"):
            pass

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["instructions"] == custom_prompt

    @pytest.mark.asyncio
    async def test_run_uses_default_system_prompt_when_not_configured(
        self,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Developer.run should pass built-in default when no custom prompt exists."""
        config = AgentConfig(driver="api", model="test-model")
        profile: Profile = mock_profile_factory()
        captured_kwargs: list[dict[str, object]] = []

        with patch("amelia.agents.developer.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_driver.execute_agentic = create_mock_execute_agentic(
                [
                    AgenticMessage(
                        type=AgenticMessageType.RESULT,
                        content="Done",
                        session_id="session-1",
                    )
                ],
                capture_kwargs=captured_kwargs,
            )
            mock_get_driver.return_value = mock_driver
            developer = Developer(config)

        state = ImplementationState(
            workflow_id="test-workflow",
            created_at=datetime.now(UTC),
            status="running",
            profile_id=profile.name,
            issue=Issue(id="TEST-2", title="Test", description="Test"),
            goal="Implement feature",
            plan_markdown="# Plan\n\nDo work",
        )

        async for _state_update, _event in developer.run(state, profile, "wf-test"):
            pass

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["instructions"] == developer.system_prompt
