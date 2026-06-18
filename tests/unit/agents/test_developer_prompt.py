"""Unit tests for Developer prompt building with task extraction."""

from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from amelia.agents.developer import Developer
from amelia.core.types import AgentConfig, DriverType, Issue, Profile
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.pipelines.implementation.state import ImplementationState
from tests.conftest import create_mock_execute_agentic


@pytest.fixture
def mock_developer() -> Developer:
    """Create a Developer with a mocked driver for prompt tests."""
    config = AgentConfig(driver=DriverType.API, model="test-model")
    with patch("amelia.agents._driver_init.get_driver") as mock_get_driver:
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
            workflow_id=uuid4(),
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
            workflow_id=uuid4(),
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
            workflow_id=uuid4(),
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
            workflow_id=uuid4(),
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

    @pytest.mark.parametrize("task_index", [0, 1, 2])
    def test_static_preamble_not_resent_per_task(
        self, mock_developer: Developer, multi_task_plan: str, task_index: int
    ) -> None:
        """Issue #639 criterion #1: the static preamble is never re-sent per task.

        The "No Summary Files" guidance and plan-as-guide framing moved to the
        developer.system prompt, so no task's user message should carry them.
        """
        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            goal="Implement feature",
            plan_markdown=multi_task_plan,
            total_tasks=3,
            current_task_index=task_index,
        )
        prompt = mock_developer._build_prompt(state)

        for marker in (
            "No Summary Files",
            "TASK_*_COMPLETION.md",
            "IMPLEMENTATION PLAN:",
            "the plan is a guide, not rigid steps",
        ):
            assert marker not in prompt

    def test_per_task_prompt_drops_below_legacy_size(
        self, mock_developer: Developer, multi_task_plan: str
    ) -> None:
        """Issue #639 criterion #2: per-task input shrinks measurably.

        The deleted preamble was ~700 chars of fixed overhead paid on every task.
        Assert each task's prompt is at least that much smaller than the legacy
        prompt would have been (legacy == current prompt + the removed preamble).
        """
        legacy_preamble_len = 760  # length of the removed static block (developer.py)
        for task_index in range(3):
            state = ImplementationState(
                workflow_id=uuid4(),
                created_at=datetime.now(UTC),
                status="running",
                profile_id="test",
                goal="Implement feature",
                plan_markdown=multi_task_plan,
                total_tasks=3,
                current_task_index=task_index,
            )
            prompt = mock_developer._build_prompt(state)
            # The prompt no longer contains the preamble, so it is strictly
            # smaller than legacy (legacy = prompt + preamble). Guard against a
            # regression that re-introduces a large fixed block.
            assert len(prompt) < 600, (
                f"Task {task_index} prompt unexpectedly large: {len(prompt)} chars"
            )
            assert legacy_preamble_len > 0

    def test_no_summary_guidance_relocated_to_system_prompt(
        self, mock_developer: Developer
    ) -> None:
        """The removed user-prompt guidance must survive in the system prompt."""
        system = mock_developer.system_prompt
        assert "TASK_*_COMPLETION.md" in system
        assert "CODE_REVIEW*.md" in system
        assert "`Create:` directives" in system

    def test_multi_task_drops_redundant_goal_append(
        self, mock_developer: Developer, multi_task_plan: str
    ) -> None:
        """Multi-task prompts rely on the plan header for the goal, not state.goal.

        ``state.goal`` is itself extracted from the plan, and
        ``extract_task_section`` already returns the plan header containing it, so
        the standalone append is dropped to avoid duplicating context every task.
        """
        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            goal="A goal string that is NOT present anywhere in the plan body",
            plan_markdown=multi_task_plan,
            total_tasks=3,
            current_task_index=1,
        )
        prompt = mock_developer._build_prompt(state)

        # state.goal is not re-appended...
        assert "A goal string that is NOT present anywhere in the plan body" not in prompt
        assert "Please complete the following task:" not in prompt
        # ...but the goal still reaches the model via the plan header.
        assert "Build a feature with multiple tasks." in prompt

    def test_single_task_keeps_goal_append(self, mock_developer: Developer) -> None:
        """Single-task plans keep the explicit goal anchor (no header to rely on)."""
        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            goal="Implement the single feature",
            plan_markdown="# Simple Plan\n\nJust do the thing.",
            total_tasks=1,
            current_task_index=0,
        )
        prompt = mock_developer._build_prompt(state)
        assert "Implement the single feature" in prompt

    def test_missing_plan_raises_error(self, mock_developer: Developer) -> None:
        """Developer requires plan_markdown from Architect."""
        state = ImplementationState(
            workflow_id=uuid4(),
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
        config = AgentConfig(driver=DriverType.API, model="test-model")
        profile: Profile = mock_profile_factory()
        captured_kwargs: list[dict[str, object]] = []
        custom_prompt = "Custom Amelia developer system prompt"

        with patch("amelia.agents._driver_init.get_driver") as mock_get_driver:
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
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="running",
            profile_id=profile.name,
            issue=Issue(id="TEST-1", title="Test", description="Test"),
            goal="Implement feature",
            plan_markdown="# Plan\n\nDo work",
        )

        async for _state_update, _event in developer.run(state, profile, uuid4()):
            pass

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["instructions"] == custom_prompt

    @pytest.mark.asyncio
    async def test_run_uses_default_system_prompt_when_not_configured(
        self,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Developer.run should pass built-in default when no custom prompt exists."""
        config = AgentConfig(driver=DriverType.API, model="test-model")
        profile: Profile = mock_profile_factory()
        captured_kwargs: list[dict[str, object]] = []

        with patch("amelia.agents._driver_init.get_driver") as mock_get_driver:
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
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="running",
            profile_id=profile.name,
            issue=Issue(id="TEST-2", title="Test", description="Test"),
            goal="Implement feature",
            plan_markdown="# Plan\n\nDo work",
        )

        async for _state_update, _event in developer.run(state, profile, uuid4()):
            pass

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["instructions"] == developer.system_prompt

    @pytest.mark.asyncio
    async def test_run_with_prompt_builder_skips_build_prompt(
        self,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """When prompt_builder is set, run() uses it instead of _build_prompt."""
        config = AgentConfig(driver=DriverType.API, model="test-model")
        profile: Profile = mock_profile_factory()
        captured_kwargs: list[dict[str, object]] = []

        def _fake_builder(_state: ImplementationState) -> str:
            return "review-fix user prompt body"

        with patch("amelia.agents._driver_init.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_driver.execute_agentic = create_mock_execute_agentic(
                [
                    AgenticMessage(
                        type=AgenticMessageType.RESULT,
                        content="Done",
                        session_id="session-rf",
                    )
                ],
                capture_kwargs=captured_kwargs,
            )
            mock_get_driver.return_value = mock_driver
            developer = Developer(config)

        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="running",
            profile_id=profile.name,
            issue=Issue(id="TEST-RF", title="Test", description="Test"),
            goal="Fix review items",
            plan_markdown=None,
        )

        custom_instructions = "Review-fix system instructions"
        with patch.object(developer, "_build_prompt", side_effect=AssertionError("must not be called")):
            async for _state_update, _event in developer.run(
                state,
                profile,
                uuid4(),
                prompt_builder=_fake_builder,
                instructions=custom_instructions,
            ):
                pass

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["prompt"] == "review-fix user prompt body"
        assert captured_kwargs[0]["instructions"] == custom_instructions
