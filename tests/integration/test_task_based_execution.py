"""Integration tests for task-based execution flow.

Tests verify that multi-task plans are processed correctly through
the orchestrator's routing logic and node transitions:
1. Tasks are executed sequentially (indices 0, 1, 2, ...)
2. Each task gets reviewed before moving to the next
3. Commits are made between tasks
4. Execution halts when max review iterations reached
"""

from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.types import Issue, Profile
from amelia.drivers.api import ApiDriver
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.pipelines.implementation.nodes import next_task_node
from amelia.pipelines.nodes import call_developer_node, call_reviewer_node
from tests.integration.conftest import (
    make_config,
    make_execution_state,
    make_profile,
    make_reviewer_agentic_messages,
)


@pytest.fixture(autouse=True)
def mock_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set API key env var to allow driver construction."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-for-integration-tests")


@pytest.fixture
def multi_task_plan_content() -> str:
    """A plan with 3 tasks for testing multi-task execution."""
    return """# Test Plan

## Goal
Implement a feature with three distinct tasks.

## Architecture
Modular design with clear separation of concerns.

## Tech Stack
Python, pytest

---

## Phase 1: Foundation

### Task 1: Create module

Create the new module file with basic structure.
- Create src/feature.py with FeatureClass
- Implement core logic

### Task 2: Add tests

Add unit tests for the module.
- Create tests/test_feature.py
- Write test cases for all methods

## Phase 2: Documentation

### Task 3: Update docs

Update documentation to reflect the changes.
- Update README.md
- Add API documentation
"""


@pytest.fixture
def integration_profile(tmp_path: Path) -> Profile:
    """Create profile configured for task-based execution testing."""
    return make_profile(
        name="test-task-execution",
        driver="api:openrouter",
        model="openrouter:anthropic/claude-sonnet-4-20250514",
        working_dir=str(tmp_path),
        plan_output_dir=str(tmp_path / "plans"),
        max_task_review_iterations=2,
    )


@pytest.fixture
def integration_issue() -> Issue:
    """Create test issue for task-based execution."""
    return Issue(
        id="TEST-TASK-123",
        title="Test Task-Based Execution",
        description="Test issue for verifying multi-task execution flow",
    )


def _create_developer_mock_messages(task_index: int) -> list[AgenticMessage]:
    """Create mock developer messages for a given task."""
    return [
        AgenticMessage(
            type=AgenticMessageType.THINKING,
            content=f"Working on task {task_index + 1}...",
        ),
        AgenticMessage(
            type=AgenticMessageType.TOOL_CALL,
            tool_name="write_file",
            tool_input={"path": f"task_{task_index}.py", "content": "# code"},
            tool_call_id=f"write-{task_index}",
        ),
        AgenticMessage(
            type=AgenticMessageType.TOOL_RESULT,
            tool_name="write_file",
            tool_output="File written successfully",
            tool_call_id=f"write-{task_index}",
        ),
        AgenticMessage(
            type=AgenticMessageType.RESULT,
            content=f"Completed task {task_index + 1}",
            session_id=f"session-task-{task_index}",
        ),
    ]


@pytest.mark.integration
class TestDeveloperNodeTaskInjection:
    """Test that developer node injects task-scoped prompts."""

    async def test_developer_node_clears_session_for_task_execution(
        self,
        tmp_path: Path,
        integration_profile: Profile,
        integration_issue: Issue,
        multi_task_plan_content: str,
    ) -> None:
        """Developer node should clear driver_session_id for fresh task sessions.

        Real components: call_developer_node session handling
        Mock boundary: ApiDriver.execute_agentic
        """
        plan_path = tmp_path / "plans" / "test-plan.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(multi_task_plan_content)

        # State with existing session that should be cleared
        state = make_execution_state(
            profile=integration_profile,
            issue=integration_issue,
            goal="Implement feature",
            plan_markdown=multi_task_plan_content,
            plan_path=plan_path,
            total_tasks=2,  # Task-based mode
            current_task_index=0,
            driver_session_id="old-session-123",  # Should be cleared
        )

        config = make_config(
            thread_id="test-session-clear",
            profile=integration_profile,
        )

        # Track session_id passed to driver
        captured_session_id: list[str | None] = []

        async def mock_execute_agentic(*args: Any, **kwargs: Any) -> Any:
            captured_session_id.append(kwargs.get("session_id"))
            for msg in _create_developer_mock_messages(0):
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
            await call_developer_node(state, cast(RunnableConfig, config))

        # Session should have been cleared (None passed to driver)
        assert len(captured_session_id) == 1
        assert captured_session_id[0] is None

    async def test_developer_node_injects_task_prompt(
        self,
        tmp_path: Path,
        integration_profile: Profile,
        integration_issue: Issue,
        multi_task_plan_content: str,
    ) -> None:
        """Developer node should inject task-specific prompt for multi-task execution.

        Real components: call_developer_node task prompt injection
        Mock boundary: ApiDriver.execute_agentic
        """
        plan_path = tmp_path / "plans" / "test-plan.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(multi_task_plan_content)

        state = make_execution_state(
            profile=integration_profile,
            issue=integration_issue,
            goal="Implement feature",
            plan_markdown=multi_task_plan_content,
            plan_path=plan_path,
            total_tasks=3,
            current_task_index=1,  # Task 2 (1-indexed display)
        )

        config = make_config(
            thread_id="test-task-prompt",
            profile=integration_profile,
        )

        captured_prompt: list[str] = []

        async def mock_execute_agentic(*args: Any, **kwargs: Any) -> Any:
            # Prompt is passed in kwargs to driver.execute_agentic
            prompt = kwargs.get("prompt", "")
            captured_prompt.append(prompt)
            for msg in _create_developer_mock_messages(1):
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
            await call_developer_node(state, cast(RunnableConfig, config))

        assert len(captured_prompt) == 1
        # The prompt should include task progress indicator and task content
        assert "Task 2" in captured_prompt[0]
        # Task 2 content should be present (extracted from plan_markdown)
        assert "Add tests" in captured_prompt[0]

    async def test_developer_node_preserves_session_for_legacy_mode(
        self,
        tmp_path: Path,
        integration_profile: Profile,
        integration_issue: Issue,
    ) -> None:
        """Developer node should preserve session_id when total_tasks is None (legacy).

        Real components: call_developer_node legacy mode handling
        Mock boundary: ApiDriver.execute_agentic
        """
        state = make_execution_state(
            profile=integration_profile,
            issue=integration_issue,
            goal="Legacy goal",
            plan_markdown="Do stuff",
            total_tasks=None,  # Legacy mode
            driver_session_id="existing-session",
        )

        config = make_config(
            thread_id="test-legacy-session",
            profile=integration_profile,
        )

        captured_session_id: list[str | None] = []

        async def mock_execute_agentic(*args: Any, **kwargs: Any) -> Any:
            captured_session_id.append(kwargs.get("session_id"))
            for msg in _create_developer_mock_messages(0):
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
            await call_developer_node(state, cast(RunnableConfig, config))

        # Session should be preserved in legacy mode
        assert len(captured_session_id) == 1
        assert captured_session_id[0] == "existing-session"


@pytest.mark.integration
class TestReviewerNodeTaskIteration:
    """Test that reviewer node increments task_review_iteration."""

    async def test_reviewer_node_increments_task_review_iteration(
        self,
        tmp_path: Path,
        integration_profile: Profile,
        integration_issue: Issue,
    ) -> None:
        """Reviewer node should increment task_review_iteration for task-based execution.

        Real components: call_reviewer_node iteration tracking
        Mock boundary: ApiDriver.execute_agentic
        """
        state = make_execution_state(
            profile=integration_profile,
            issue=integration_issue,
            goal="Implement feature",
            total_tasks=2,  # Task-based mode
            current_task_index=0,
            task_review_iteration=1,  # Already at 1
            code_changes_for_review="diff --git a/test.py\n+# code",
        )

        config = make_config(
            thread_id="test-iteration-incr",
            profile=integration_profile,
        )

        mock_messages = make_reviewer_agentic_messages(
            approved=False,
            comments=["Needs work"],
            severity="high",
        )

        async def mock_execute_agentic(*_args: Any, **_kwargs: Any) -> Any:
            for msg in mock_messages:
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
            result = await call_reviewer_node(state, cast(RunnableConfig, config))

        # task_review_iteration should be incremented to 2
        assert result["task_review_iteration"] == 2


@pytest.mark.integration
class TestNextTaskNodeTransition:
    """Test next_task_node transitions between tasks."""

    async def test_next_task_node_increments_index_and_resets_iteration(
        self,
        git_repo: Path,
        integration_issue: Issue,
    ) -> None:
        """next_task_node should increment task index and reset iteration.

        Real components: next_task_node state transitions
        Mock boundary: git commands for commit (via subprocess)
        """
        # Create profile with git_repo as working directory
        profile = make_profile(
            name="test-task-execution",
            driver="api:openrouter",
            model="openrouter:anthropic/claude-sonnet-4-20250514",
            working_dir=str(git_repo),
            plan_output_dir=str(git_repo / "plans"),
            max_task_review_iterations=2,
        )

        # Create a change to commit
        (git_repo / "task_0.py").write_text("# Task 0 code")

        state = make_execution_state(
            profile=profile,
            issue=integration_issue,
            total_tasks=3,
            current_task_index=0,
            task_review_iteration=2,  # Will be reset
            driver_session_id="task-0-session",  # Will be cleared
        )

        config = make_config(
            thread_id="test-next-task",
            profile=profile,
        )

        result = await next_task_node(state, cast(RunnableConfig, config))

        # Verify state updates
        assert result["current_task_index"] == 1  # Incremented
        assert result["task_review_iteration"] == 0  # Reset
        assert result["driver_session_id"] is None  # Cleared

    async def test_next_task_node_commits_changes(
        self,
        git_repo: Path,
        integration_issue: Issue,
    ) -> None:
        """next_task_node should commit changes for the completed task.

        Real components: next_task_node, commit_task_changes
        """
        import subprocess

        # Create profile with git_repo as working directory
        profile = make_profile(
            name="test-task-execution",
            driver="api:openrouter",
            model="openrouter:anthropic/claude-sonnet-4-20250514",
            working_dir=str(git_repo),
            plan_output_dir=str(git_repo / "plans"),
            max_task_review_iterations=2,
        )

        # Create a change that will be committed
        (git_repo / "new_file.py").write_text("# New code")

        state = make_execution_state(
            profile=profile,
            issue=integration_issue,
            total_tasks=3,
            current_task_index=0,
        )

        config = make_config(
            thread_id="test-commit",
            profile=profile,
        )

        await next_task_node(state, cast(RunnableConfig, config))

        # Verify commit was made
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=git_repo,
            capture_output=True,
            text=True,
        )
        commits = result.stdout.strip().split("\n")
        assert len(commits) == 2  # Initial + task commit
        assert "complete task 1" in commits[0].lower()


@pytest.mark.integration
class TestPlanMarkdownPreservation:
    """Tests that plan_markdown stays intact across task transitions."""

    async def test_plan_markdown_unchanged_after_developer_node(
        self,
        tmp_path: Path,
        integration_profile: Profile,
        integration_issue: Issue,
        multi_task_plan_content: str,
    ) -> None:
        """Developer node should NOT mutate plan_markdown in returned state.

        Real components: call_developer_node state handling
        Mock boundary: ApiDriver.execute_agentic
        """
        plan_path = tmp_path / "plans" / "test-plan.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(multi_task_plan_content)

        original_plan = multi_task_plan_content

        state = make_execution_state(
            profile=integration_profile,
            issue=integration_issue,
            goal="Implement feature",
            plan_markdown=original_plan,
            plan_path=plan_path,
            total_tasks=3,
            current_task_index=0,
        )

        config = make_config(
            thread_id="test-preservation",
            profile=integration_profile,
        )

        async def mock_execute_agentic(*args: Any, **kwargs: Any) -> Any:
            for msg in _create_developer_mock_messages(1):
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
            result = await call_developer_node(state, cast(RunnableConfig, config))

        # The returned state dict should NOT contain plan_markdown
        # (preserving immutability - orchestrator uses state.plan_markdown directly)
        assert "plan_markdown" not in result, (
            "call_developer_node should not return plan_markdown in updates"
        )

    async def test_developer_prompt_contains_task_section_not_full_plan(
        self,
        tmp_path: Path,
        integration_profile: Profile,
        integration_issue: Issue,
        multi_task_plan_content: str,
    ) -> None:
        """Developer should receive extracted task section, not full plan.

        Real components: Developer._build_prompt, extract_task_section
        Mock boundary: ApiDriver.execute_agentic
        """
        plan_path = tmp_path / "plans" / "test-plan.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(multi_task_plan_content)

        state = make_execution_state(
            profile=integration_profile,
            issue=integration_issue,
            goal="Implement feature",
            plan_markdown=multi_task_plan_content,
            plan_path=plan_path,
            total_tasks=3,
            current_task_index=1,  # Task 2
        )

        config = make_config(
            thread_id="test-extraction",
            profile=integration_profile,
        )

        captured_prompt: list[str] = []

        async def mock_execute_agentic(*args: Any, **kwargs: Any) -> Any:
            prompt = kwargs.get("prompt", "")
            captured_prompt.append(prompt)
            for msg in _create_developer_mock_messages(1):
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
            await call_developer_node(state, cast(RunnableConfig, config))

        assert len(captured_prompt) == 1
        prompt = captured_prompt[0]

        # Should have Task 2 content
        assert "Task 2" in prompt
        assert "Add tests" in prompt
        # Should NOT have Task 3 content (Task 3 is in Phase 2)
        assert "### Task 3:" not in prompt
        assert "Update docs" not in prompt
