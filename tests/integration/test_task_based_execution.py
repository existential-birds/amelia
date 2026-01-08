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
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.agents.reviewer import ReviewResponse
from amelia.core.orchestrator import (
    call_developer_node,
    call_reviewer_node,
    next_task_node,
    route_after_review_or_task,
    route_after_task_review,
)
from amelia.core.state import ExecutionState, ReviewResult
from amelia.core.types import Issue, Profile
from amelia.drivers.api import ApiDriver
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from tests.integration.conftest import make_config, make_profile


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

### Task 1: Create module

Create the new module file with basic structure.

### Task 2: Add tests

Add unit tests for the module.

### Task 3: Update docs

Update documentation to reflect the changes.
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
class TestTaskBasedRoutingLogic:
    """Test the routing logic for task-based execution."""

    def test_route_after_task_review_ends_when_all_tasks_complete(
        self,
        integration_profile: Profile,
    ) -> None:
        """Should END when approved and all tasks complete.

        Real components: route_after_task_review routing function
        """
        # State: on last task (index 1 of 2 total), review approved
        state = ExecutionState(
            profile_id="test",
            total_tasks=2,
            current_task_index=1,  # On task 2 (0-indexed)
            last_review=ReviewResult(
                reviewer_persona="single",
                approved=True,
                comments=["LGTM!"],
                severity="low",
            ),
        )
        config = {"configurable": {"profile": integration_profile}}

        result = route_after_task_review(state, cast(RunnableConfig, config))
        assert result == "__end__"

    def test_route_after_task_review_goes_to_next_task_when_approved(
        self,
        integration_profile: Profile,
    ) -> None:
        """Should go to next_task_node when approved and more tasks remain.

        Real components: route_after_task_review routing function
        """
        # State: on first task (index 0 of 3 total), review approved
        state = ExecutionState(
            profile_id="test",
            total_tasks=3,
            current_task_index=0,  # On task 1, more tasks remain
            last_review=ReviewResult(
                reviewer_persona="single",
                approved=True,
                comments=["Task 1 done!"],
                severity="low",
            ),
        )
        config = {"configurable": {"profile": integration_profile}}

        result = route_after_task_review(state, cast(RunnableConfig, config))
        assert result == "next_task_node"

    def test_route_after_task_review_retries_developer_when_not_approved(
        self,
        integration_profile: Profile,
    ) -> None:
        """Should retry developer when review not approved and iterations remain.

        Real components: route_after_task_review routing function
        """
        # State: task rejected, under iteration limit (max=2, current=1)
        state = ExecutionState(
            profile_id="test",
            total_tasks=2,
            current_task_index=0,
            task_review_iteration=1,  # Under limit of 2
            last_review=ReviewResult(
                reviewer_persona="single",
                approved=False,
                comments=["Needs work"],
                severity="high",
            ),
        )
        config = {"configurable": {"profile": integration_profile}}

        result = route_after_task_review(state, cast(RunnableConfig, config))
        assert result == "developer"

    def test_route_after_task_review_ends_on_max_iterations(
        self,
        integration_profile: Profile,
    ) -> None:
        """Should END when max iterations reached without approval.

        Real components: route_after_task_review routing function
        """
        # State: at max iterations (2), still not approved
        state = ExecutionState(
            profile_id="test",
            total_tasks=2,
            current_task_index=0,
            task_review_iteration=2,  # At limit (max=2)
            last_review=ReviewResult(
                reviewer_persona="single",
                approved=False,
                comments=["Still not right"],
                severity="critical",
            ),
        )
        config = {"configurable": {"profile": integration_profile}}

        result = route_after_task_review(state, cast(RunnableConfig, config))
        assert result == "__end__"

    def test_route_after_review_or_task_uses_task_routing_when_total_tasks_set(
        self,
        integration_profile: Profile,
    ) -> None:
        """Should use task-based routing when total_tasks is set.

        Real components: route_after_review_or_task wrapper function
        """
        # State: task-based execution mode (total_tasks set)
        state = ExecutionState(
            profile_id="test",
            total_tasks=3,  # Task-based mode
            current_task_index=0,
            last_review=ReviewResult(
                reviewer_persona="single",
                approved=True,
                comments=["Done!"],
                severity="low",
            ),
        )
        config = {"configurable": {"profile": integration_profile}}

        result = route_after_review_or_task(state, cast(RunnableConfig, config))
        assert result == "next_task_node"

    def test_route_after_review_or_task_uses_legacy_routing_when_total_tasks_none(
        self,
        integration_profile: Profile,
    ) -> None:
        """Should use legacy routing when total_tasks is None.

        Real components: route_after_review_or_task wrapper function
        """
        # State: legacy mode (total_tasks not set)
        state = ExecutionState(
            profile_id="test",
            total_tasks=None,  # Legacy mode
            last_review=ReviewResult(
                reviewer_persona="single",
                approved=True,
                comments=["Done!"],
                severity="low",
            ),
        )
        config = {"configurable": {"profile": integration_profile}}

        result = route_after_review_or_task(state, cast(RunnableConfig, config))
        assert result == "__end__"


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
        state = ExecutionState(
            profile_id="test-task-execution",
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

        state = ExecutionState(
            profile_id="test-task-execution",
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
        # The prompt should include the task pointer injected into the goal
        # which then gets built into the prompt by Developer._build_prompt
        assert "Task 2" in captured_prompt[0]
        assert str(plan_path) in captured_prompt[0]

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
        state = ExecutionState(
            profile_id="test-task-execution",
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
        Mock boundary: ApiDriver.generate
        """
        state = ExecutionState(
            profile_id="test-task-execution",
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

        mock_review = ReviewResponse(
            approved=False,
            comments=["Needs work"],
            severity="high",
        )

        with patch.object(
            ApiDriver, "generate", new_callable=AsyncMock
        ) as mock_generate:
            mock_generate.return_value = (mock_review, "session-review")
            result = await call_reviewer_node(state, cast(RunnableConfig, config))

        # task_review_iteration should be incremented to 2
        assert result["task_review_iteration"] == 2


@pytest.mark.integration
class TestNextTaskNodeTransition:
    """Test next_task_node transitions between tasks."""

    async def test_next_task_node_increments_index_and_resets_iteration(
        self,
        tmp_path: Path,
        integration_profile: Profile,
        integration_issue: Issue,
    ) -> None:
        """next_task_node should increment task index and reset iteration.

        Real components: next_task_node state transitions
        Mock boundary: git commands for commit (via subprocess)
        """
        import subprocess

        # Initialize git repo for commit_task_changes
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        # Create a change to commit
        (tmp_path / "task_0.py").write_text("# Task 0 code")

        state = ExecutionState(
            profile_id="test-task-execution",
            issue=integration_issue,
            total_tasks=3,
            current_task_index=0,
            task_review_iteration=2,  # Will be reset
            driver_session_id="task-0-session",  # Will be cleared
        )

        config = make_config(
            thread_id="test-next-task",
            profile=integration_profile,
        )

        result = await next_task_node(state, cast(RunnableConfig, config))

        # Verify state updates
        assert result["current_task_index"] == 1  # Incremented
        assert result["task_review_iteration"] == 0  # Reset
        assert result["driver_session_id"] is None  # Cleared

    async def test_next_task_node_commits_changes(
        self,
        tmp_path: Path,
        integration_profile: Profile,
        integration_issue: Issue,
    ) -> None:
        """next_task_node should commit changes for the completed task.

        Real components: next_task_node, commit_task_changes
        """
        import subprocess

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        # Create a change that will be committed
        (tmp_path / "new_file.py").write_text("# New code")

        state = ExecutionState(
            profile_id="test-task-execution",
            issue=integration_issue,
            total_tasks=3,
            current_task_index=0,
        )

        config = make_config(
            thread_id="test-commit",
            profile=integration_profile,
        )

        await next_task_node(state, cast(RunnableConfig, config))

        # Verify commit was made
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        commits = result.stdout.strip().split("\n")
        assert len(commits) == 2  # Initial + task commit
        assert "complete task 1" in commits[0].lower()
