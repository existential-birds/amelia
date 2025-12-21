# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for ReviewerContextStrategy.

Tests cover context compilation for review with ExecutionPlan batches,
issue fallback, and persona system prompts.
"""
import pytest

from amelia.agents.reviewer import ReviewerContextStrategy
from amelia.core.context import CompiledContext
from amelia.core.state import (
    ExecutionPlan,
    ExecutionState,
)


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
    def state_with_batch(
        self,
        mock_execution_state_factory,
        mock_execution_plan_factory,
        code_diff
    ):
        """Create execution state with a current batch and code changes."""
        plan = mock_execution_plan_factory(
            goal="Review authentication implementation for security vulnerabilities",
            num_batches=1,
            steps_per_batch=2,
        )
        return mock_execution_state_factory(
            execution_plan=plan,
            current_batch_index=0,
            code_changes_for_review=code_diff
        )

    def test_compile_with_code_diff(self, strategy, state_with_batch, code_diff):
        """Test compile produces context with code diff section."""
        context = strategy.compile(state_with_batch)

        assert isinstance(context, CompiledContext)
        # Should have diff section
        diff_sections = [s for s in context.sections if s.name == "diff"]
        assert len(diff_sections) == 1
        assert code_diff in diff_sections[0].content

    @pytest.mark.parametrize("persona", ["Security", "Performance", "General"])
    def test_compile_with_persona(self, state_with_batch, persona):
        """Test persona appears in system prompt and produces stable output."""
        strategy = ReviewerContextStrategy(persona=persona)
        context = strategy.compile(state_with_batch)

        assert context.system_prompt is not None
        assert persona in context.system_prompt

        # Test stability by compiling twice
        context2 = strategy.compile(state_with_batch)
        assert context.system_prompt == context2.system_prompt

    def test_compile_batch_context_included(
        self,
        strategy,
        state_with_batch
    ):
        """Test batch context is included in sections."""
        context = strategy.compile(state_with_batch)

        # Should have task section from batch
        task_sections = [s for s in context.sections if s.name == "task"]
        assert len(task_sections) == 1

        # Should NOT have issue section when batch is present
        issue_sections = [s for s in context.sections if s.name == "issue"]
        assert len(issue_sections) == 0

    def test_compile_falls_back_to_issue(
        self,
        strategy,
        mock_execution_state_factory,
        code_diff
    ):
        """Test compile falls back to issue when no batch is present."""
        # State with issue but no execution plan
        state = mock_execution_state_factory(
            execution_plan=None,
            code_changes_for_review=code_diff
        )

        context = strategy.compile(state)

        # Should have issue section (fallback)
        issue_sections = [s for s in context.sections if s.name == "issue"]
        assert len(issue_sections) == 1

        # Should NOT have task section
        task_sections = [s for s in context.sections if s.name == "task"]
        assert len(task_sections) == 0

    def test_compile_raises_when_no_batch_or_issue(
        self,
        mock_profile_factory,
        code_diff
    ):
        """Test raises ValueError when state has no batch and no issue."""
        # State with no execution_plan AND no issue
        state = ExecutionState(
            profile=mock_profile_factory(),
            issue=None,
            execution_plan=None,
            code_changes_for_review=code_diff
        )

        strategy = ReviewerContextStrategy()
        with pytest.raises(ValueError, match="No batch, task, or issue context found"):
            strategy.compile(state)

    def test_system_prompt_template_produces_stable_prefix_per_persona(
        self,
        state_with_batch
    ):
        """Test SYSTEM_PROMPT_TEMPLATE produces stable prefix per persona."""
        persona = "Security"

        # Compile multiple times with same persona
        strategy1 = ReviewerContextStrategy(persona=persona)
        context1 = strategy1.compile(state_with_batch)
        strategy2 = ReviewerContextStrategy(persona=persona)
        context2 = strategy2.compile(state_with_batch)

        # System prompts should be identical for same persona
        assert context1.system_prompt == context2.system_prompt

        # Should be different for different personas
        strategy3 = ReviewerContextStrategy(persona="Performance")
        context3 = strategy3.compile(state_with_batch)
        assert context1.system_prompt != context3.system_prompt

    def test_compile_validates_allowed_sections(
        self,
        strategy,
        state_with_batch
    ):
        """Test compile only produces allowed sections."""
        context = strategy.compile(state_with_batch)

        # All sections should be in ALLOWED_SECTIONS
        for section in context.sections:
            assert section.name in ReviewerContextStrategy.ALLOWED_SECTIONS

    def test_to_messages_integration(
        self,
        state_with_batch
    ):
        """Test compiled context can be converted to messages."""
        strategy = ReviewerContextStrategy(persona="Security")
        context = strategy.compile(state_with_batch)

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
        mock_execution_plan_factory
    ):
        """Test raises ValueError when state has no code changes."""
        plan = mock_execution_plan_factory(num_batches=1)
        state = mock_execution_state_factory(
            execution_plan=plan,
            code_changes_for_review=None
        )

        strategy = ReviewerContextStrategy()
        with pytest.raises(ValueError, match="No code changes provided"):
            strategy.compile(state)

    def test_compile_section_sources_for_debugging(
        self,
        strategy,
        state_with_batch
    ):
        """Test sections have source metadata for debugging."""
        context = strategy.compile(state_with_batch)

        # All sections should have source metadata with meaningful values
        for section in context.sections:
            assert section.source is not None
            assert section.source != ""

    def test_compile_default_persona(
        self,
        state_with_batch
    ):
        """Test compile with default persona when not specified."""
        # Create strategy without explicit persona (should use default)
        strategy = ReviewerContextStrategy()
        context = strategy.compile(state_with_batch)

        # Should have a system prompt even without explicit persona
        assert context.system_prompt is not None
        # Should contain default "General" persona
        assert "General" in context.system_prompt


class TestReviewerValidation:
    """Tests for Reviewer agent fallback behavior."""

    async def test_reviewer_allows_no_execution_plan_with_issue(
        self,
        mock_execution_state_factory,
        mock_async_driver_factory,
        mock_review_response_factory,
    ):
        """Reviewer should work without execution_plan when issue is present.

        This allows reviewing with just issue context when no plan exists.
        """
        from amelia.agents.reviewer import Reviewer

        state = mock_execution_state_factory(
            execution_plan=None,
            code_changes_for_review="diff --git a/file.py"
        )

        mock_response = mock_review_response_factory()
        mock_driver = mock_async_driver_factory(generate_return=(mock_response, None))

        reviewer = Reviewer(mock_driver)

        # Should not raise - falls back to issue context
        result = await reviewer.review(state, code_changes="diff --git a/file.py", workflow_id="test-workflow")
        assert result is not None

    async def test_reviewer_works_with_empty_batches(
        self,
        mock_execution_state_factory,
        mock_async_driver_factory,
        mock_review_response_factory,
    ):
        """Reviewer should work when execution plan has no batches."""
        from amelia.agents.reviewer import Reviewer

        # Create empty plan (no batches)
        empty_plan = ExecutionPlan(
            goal="Empty plan",
            batches=(),
            total_estimated_minutes=0,
            tdd_approach=False,
        )
        state = mock_execution_state_factory(
            execution_plan=empty_plan,
            code_changes_for_review="diff --git a/file.py"
        )

        mock_response = mock_review_response_factory()
        mock_driver = mock_async_driver_factory(generate_return=(mock_response, None))

        reviewer = Reviewer(mock_driver)

        # Should not raise - falls back to issue context
        result = await reviewer.review(state, code_changes="diff --git a/file.py", workflow_id="test-workflow")
        assert result is not None


class TestReviewerSessionId:
    """Tests for Reviewer session_id handling."""

    async def test_reviewer_passes_session_id_to_driver(
        self,
        mock_execution_state_factory,
        mock_async_driver_factory,
        mock_review_response_factory,
    ):
        """Test that Reviewer passes session_id from state to driver."""
        from amelia.agents.reviewer import Reviewer

        mock_response = mock_review_response_factory(approved=True)
        mock_driver = mock_async_driver_factory(generate_return=(mock_response, "new-sess"))

        state = mock_execution_state_factory(
            driver_session_id="review-sess-123",
            code_changes_for_review="diff content",
        )

        reviewer = Reviewer(mock_driver)
        result, result_session_id = await reviewer._single_review(state, "diff", "General", workflow_id="wf-1")

        mock_driver.generate.assert_called_once()
        call_kwargs = mock_driver.generate.call_args.kwargs
        assert call_kwargs.get("session_id") == "review-sess-123"

        # Verify return value includes session_id
        assert result_session_id == "new-sess"
        assert result is not None
