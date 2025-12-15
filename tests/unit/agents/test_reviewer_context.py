# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for ReviewerContextStrategy.

Tests cover all acceptance criteria from Phase 3, Task 3.3:
- [x] Test compile with code diff
- [x] Test persona appears in system prompt
- [x] Test task context included (not full issue)
- [x] Test handles missing task description gracefully
- [x] Test SYSTEM_PROMPT_TEMPLATE produces stable prefix per persona (Gap 3)
- [x] Test only 'task', 'diff', 'criteria' sections allowed (Gap 5)
- [x] Test does NOT include issue or developer reasoning (Gap 5)
"""
import pytest

from amelia.agents.reviewer import ReviewerContextStrategy
from amelia.core.context import CompiledContext


class TestReviewerContextStrategy:
    """Test ReviewerContextStrategy context compilation."""

    @pytest.fixture
    def strategy(self):
        """Create a ReviewerContextStrategy instance with default persona."""
        return ReviewerContextStrategy(persona="General")

    @pytest.fixture
    def code_diff(self):
        """Sample code diff for testing."""
        return """diff --git a/auth.py b/auth.py
index 1234567..abcdefg 100644
--- a/auth.py
+++ b/auth.py
@@ -10,6 +10,7 @@ def login(username, password):
     if not user:
         return None
+    # Added password verification
     if not verify_password(password, user.password_hash):
         return None"""

    @pytest.fixture
    def state_with_task(
        self,
        mock_execution_state_factory,
        mock_task_factory,
        mock_task_dag_factory,
        code_diff
    ):
        """Create execution state with a current task and code changes."""
        task = mock_task_factory(
            id="1",
            description="Review authentication implementation for security vulnerabilities"
        )
        plan = mock_task_dag_factory(tasks=[task])
        return mock_execution_state_factory(
            plan=plan,
            current_task_id="1",
            code_changes_for_review=code_diff
        )

    def test_compile_with_code_diff(self, strategy, state_with_task, code_diff):
        """Test compile produces context with code diff section."""
        context = strategy.compile(state_with_task)

        assert isinstance(context, CompiledContext)
        # Should have diff section
        diff_sections = [s for s in context.sections if s.name == "diff"]
        assert len(diff_sections) == 1
        assert code_diff in diff_sections[0].content

    @pytest.mark.parametrize("persona", ["Security", "Performance", "General"])
    def test_compile_with_persona(self, state_with_task, persona):
        """Test persona appears in system prompt and produces stable output."""
        strategy = ReviewerContextStrategy(persona=persona)
        context = strategy.compile(state_with_task)

        assert context.system_prompt is not None
        assert persona in context.system_prompt

        # Test stability by compiling twice
        context2 = strategy.compile(state_with_task)
        assert context.system_prompt == context2.system_prompt

    def test_compile_task_context_included_not_full_issue(
        self,
        strategy,
        state_with_task
    ):
        """Test task context included but not full issue details."""
        context = strategy.compile(state_with_task)

        # Should have task section
        task_sections = [s for s in context.sections if s.name == "task"]
        assert len(task_sections) == 1
        task_content = task_sections[0].content
        assert "authentication" in task_content.lower()

        # Should NOT have issue section (Gap 5: scope isolation)
        issue_sections = [s for s in context.sections if s.name == "issue"]
        assert len(issue_sections) == 0

    def test_compile_handles_minimal_task_description(
        self,
        strategy,
        mock_execution_state_factory,
        mock_task_factory,
        mock_task_dag_factory,
        code_diff
    ):
        """Test handles task with minimal description."""
        # Create task - note that mock_task_factory provides fallback "Task {id}"
        # when description is empty, which tests graceful handling
        task = mock_task_factory(id="1", description="")
        plan = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(
            plan=plan,
            current_task_id="1",
            code_changes_for_review=code_diff
        )

        # Should compile successfully even with minimal description
        context = strategy.compile(state)

        assert isinstance(context, CompiledContext)
        # Task section should exist
        task_sections = [s for s in context.sections if s.name == "task"]
        assert len(task_sections) == 1
        # Factory provides fallback description "Task 1"
        assert task_sections[0].content == "Task 1"

    def test_compile_raises_when_no_task_or_issue(
        self,
        mock_profile_factory,
        code_diff
    ):
        """Test raises ValueError when state has no task and no issue."""
        from amelia.core.state import ExecutionState

        # State with no plan, no current_task_id, AND no issue
        state = ExecutionState(
            profile=mock_profile_factory(),
            issue=None,
            plan=None,
            current_task_id=None,
            code_changes_for_review=code_diff
        )

        # Should raise ValueError
        strategy = ReviewerContextStrategy()
        with pytest.raises(ValueError, match="No task or issue context found"):
            strategy.compile(state)

    def test_system_prompt_template_produces_stable_prefix_per_persona(
        self,
        state_with_task
    ):
        """Test SYSTEM_PROMPT_TEMPLATE produces stable prefix per persona (Gap 3)."""
        persona = "Security"

        # Compile multiple times with same persona
        strategy1 = ReviewerContextStrategy(persona=persona)
        context1 = strategy1.compile(state_with_task)
        strategy2 = ReviewerContextStrategy(persona=persona)
        context2 = strategy2.compile(state_with_task)

        # System prompts should be identical for same persona
        assert context1.system_prompt == context2.system_prompt

        # Should be different for different personas
        strategy3 = ReviewerContextStrategy(persona="Performance")
        context3 = strategy3.compile(state_with_task)
        assert context1.system_prompt != context3.system_prompt

    def test_compile_validates_allowed_sections(
        self,
        strategy,
        state_with_task
    ):
        """Test compile only produces allowed sections (Gap 5)."""
        context = strategy.compile(state_with_task)

        # All sections should be in ALLOWED_SECTIONS
        for section in context.sections:
            assert section.name in ReviewerContextStrategy.ALLOWED_SECTIONS

    @pytest.mark.parametrize("has_task,expected_section,excluded_section", [
        (True, "task", "issue"),
        (False, "issue", "task"),
    ], ids=["task_present", "issue_fallback"])
    def test_compile_task_vs_issue_fallback(
        self,
        strategy,
        mock_execution_state_factory,
        mock_task_factory,
        mock_task_dag_factory,
        code_diff,
        has_task,
        expected_section,
        excluded_section
    ):
        """Test compile uses task when present, otherwise falls back to issue (Gap 5)."""
        if has_task:
            # State with task
            task = mock_task_factory(id="1", description="Test task")
            plan = mock_task_dag_factory(tasks=[task])
            state = mock_execution_state_factory(
                plan=plan,
                current_task_id="1",
                code_changes_for_review=code_diff
            )
        else:
            # State with issue but no plan/task
            state = mock_execution_state_factory(
                plan=None,
                current_task_id=None,
                code_changes_for_review=code_diff
            )

        context = strategy.compile(state)

        section_names = {s.name for s in context.sections}
        assert expected_section in section_names
        assert excluded_section not in section_names

    def test_compile_does_not_include_developer_reasoning(
        self,
        strategy,
        mock_execution_state_factory,
        mock_task_factory,
        mock_task_dag_factory,
        code_diff
    ):
        """Test compile does NOT include developer reasoning (Gap 5)."""
        # Create task with steps (which might contain developer reasoning)
        task = mock_task_factory(
            id="1",
            description="Implement authentication",
            steps=[
                {
                    "description": "Developer reasoning: I decided to use JWT tokens",
                    "code": "def generate_token(): pass"
                }
            ]
        )
        plan = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(
            plan=plan,
            current_task_id="1",
            code_changes_for_review=code_diff
        )

        context = strategy.compile(state)

        # Should not have 'steps' or 'reasoning' sections
        section_names = {s.name for s in context.sections}
        assert "steps" not in section_names
        assert "reasoning" not in section_names
        assert "developer_reasoning" not in section_names

        # Only allowed sections should be present
        assert section_names.issubset(ReviewerContextStrategy.ALLOWED_SECTIONS)

    def test_to_messages_integration(
        self,
        state_with_task
    ):
        """Test compiled context can be converted to messages."""
        strategy = ReviewerContextStrategy(persona="Security")
        context = strategy.compile(state_with_task)

        messages = strategy.to_messages(context)

        # System prompt is passed separately - to_messages only returns user messages
        assert len(messages) == 1
        assert messages[0].role == "user"
        # Should contain markdown headers for sections
        assert "##" in messages[0].content

        # Verify system_prompt is still set on the context
        assert context.system_prompt is not None
        assert "Security" in context.system_prompt

    def test_compile_raises_when_no_code_changes(
        self,
        mock_execution_state_factory,
        mock_task_factory,
        mock_task_dag_factory
    ):
        """Test raises ValueError when state has no code changes."""
        task = mock_task_factory(id="1", description="Test task")
        plan = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(
            plan=plan,
            current_task_id="1",
            code_changes_for_review=None
        )

        # Should raise ValueError
        strategy = ReviewerContextStrategy()
        with pytest.raises(ValueError, match="No code changes provided"):
            strategy.compile(state)

    def test_compile_section_sources_for_debugging(
        self,
        strategy,
        state_with_task
    ):
        """Test sections have source metadata for debugging."""
        context = strategy.compile(state_with_task)

        # All sections should have source metadata with meaningful values
        for section in context.sections:
            assert section.source is not None
            assert section.source != ""
            # Source should indicate where the section came from
            assert any([
                "state" in section.source.lower(),
                "task" in section.source.lower(),
                "diff" in section.source.lower(),
                "code" in section.source.lower(),
            ])

    def test_compile_default_persona(
        self,
        state_with_task
    ):
        """Test compile with default persona when not specified."""
        # Create strategy without explicit persona (should use default)
        strategy = ReviewerContextStrategy()
        context = strategy.compile(state_with_task)

        # Should have a system prompt even without explicit persona
        assert context.system_prompt is not None
        # Should contain default "General" persona
        assert "General" in context.system_prompt


class TestReviewerValidation:
    """Tests for Reviewer agent state validation."""

    async def test_reviewer_raises_when_plan_has_tasks_but_no_current_task_id(
        self,
        mock_execution_state_factory,
        mock_task_dag_factory,
        mock_async_driver_factory,
    ):
        """Reviewer should raise ValueError if plan has tasks but current_task_id is missing.

        State preparation is the orchestrator's responsibility. The Reviewer should
        not silently patch state but instead fail fast with a clear error message.
        """
        from amelia.agents.reviewer import Reviewer

        plan = mock_task_dag_factory(num_tasks=2)
        state = mock_execution_state_factory(
            plan=plan,
            current_task_id=None,  # Missing!
            code_changes_for_review="diff --git a/file.py"
        )

        mock_driver = mock_async_driver_factory()
        reviewer = Reviewer(mock_driver)

        with pytest.raises(ValueError, match="current_task_id is required when plan has tasks"):
            await reviewer.review(state, code_changes="diff --git a/file.py", workflow_id="test-workflow")

    async def test_reviewer_allows_no_current_task_id_when_no_plan(
        self,
        mock_execution_state_factory,
        mock_async_driver_factory,
        mock_review_response_factory,
    ):
        """Reviewer should work without current_task_id when there's no plan.

        This allows reviewing with just issue context when no task plan exists.
        """
        from amelia.agents.reviewer import Reviewer

        state = mock_execution_state_factory(
            plan=None,
            current_task_id=None,
            code_changes_for_review="diff --git a/file.py"
        )

        mock_driver = mock_async_driver_factory()
        mock_driver.generate.return_value = mock_review_response_factory()

        reviewer = Reviewer(mock_driver)

        # Should not raise - falls back to issue context
        result = await reviewer.review(state, code_changes="diff --git a/file.py", workflow_id="test-workflow")
        assert result is not None

    async def test_reviewer_allows_no_current_task_id_when_plan_has_no_tasks(
        self,
        mock_execution_state_factory,
        mock_task_dag_factory,
        mock_async_driver_factory,
        mock_review_response_factory,
    ):
        """Reviewer should work without current_task_id when plan has no tasks.

        Edge case: plan exists but is empty.
        """
        from amelia.agents.reviewer import Reviewer

        # Create empty plan (no tasks)
        plan = mock_task_dag_factory(tasks=[])
        state = mock_execution_state_factory(
            plan=plan,
            current_task_id=None,
            code_changes_for_review="diff --git a/file.py"
        )

        mock_driver = mock_async_driver_factory()
        mock_driver.generate.return_value = mock_review_response_factory()

        reviewer = Reviewer(mock_driver)

        # Should not raise - plan has no tasks
        result = await reviewer.review(state, code_changes="diff --git a/file.py", workflow_id="test-workflow")
        assert result is not None
