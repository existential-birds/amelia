# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for ReviewerContextStrategy.

Tests cover context compilation for review with goal and markdown plan,
issue fallback, and persona system prompts.
"""
import pytest

from amelia.agents.reviewer import ReviewerContextStrategy
from amelia.core.context import CompiledContext
from amelia.core.state import ExecutionState


class TestReviewerContextStrategy:
    """Test ReviewerContextStrategy context compilation."""

    @pytest.fixture
    def strategy(self) -> ReviewerContextStrategy:
        """Create a ReviewerContextStrategy instance with default persona."""
        return ReviewerContextStrategy(persona="General")

    @pytest.fixture
    def code_diff(self) -> str:
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
    def state_with_goal(
        self,
        mock_execution_state_factory,
        code_diff
    ) -> ExecutionState:
        """Create execution state with a goal and code changes."""
        state, _profile = mock_execution_state_factory(
            goal="Review authentication implementation for security vulnerabilities",
            code_changes_for_review=code_diff
        )
        return state

    def test_compile_with_code_diff(self, strategy, state_with_goal, code_diff, mock_profile_factory) -> None:
        """Test compile produces context with code diff section."""
        profile = mock_profile_factory()
        context = strategy.compile(state_with_goal, profile)

        assert isinstance(context, CompiledContext)
        # Should have diff section
        diff_sections = [s for s in context.sections if s.name == "diff"]
        assert len(diff_sections) == 1
        assert code_diff in diff_sections[0].content

    @pytest.mark.parametrize("persona", ["Security", "Performance", "General"])
    def test_compile_with_persona(self, state_with_goal, persona, mock_profile_factory) -> None:
        """Test persona appears in system prompt and produces stable output."""
        profile = mock_profile_factory()
        strategy = ReviewerContextStrategy(persona=persona)
        context = strategy.compile(state_with_goal, profile)

        assert context.system_prompt is not None
        assert persona in context.system_prompt

        # Test stability by compiling twice
        context2 = strategy.compile(state_with_goal, profile)
        assert context.system_prompt == context2.system_prompt

    def test_compile_goal_context_included(
        self,
        strategy,
        state_with_goal,
        mock_profile_factory
    ) -> None:
        """Test goal context is included in sections."""
        profile = mock_profile_factory()
        context = strategy.compile(state_with_goal, profile)

        # Should have task section from goal
        task_sections = [s for s in context.sections if s.name == "task"]
        assert len(task_sections) == 1

        # Should NOT have issue section when goal is present
        issue_sections = [s for s in context.sections if s.name == "issue"]
        assert len(issue_sections) == 0

    def test_compile_falls_back_to_issue(
        self,
        strategy,
        mock_execution_state_factory,
        code_diff
    ) -> None:
        """Test compile falls back to issue when no goal is present."""
        # State with issue but no goal
        state, profile = mock_execution_state_factory(
            goal=None,
            code_changes_for_review=code_diff
        )

        context = strategy.compile(state, profile)

        # Should have issue section (fallback)
        issue_sections = [s for s in context.sections if s.name == "issue"]
        assert len(issue_sections) == 1

        # Should NOT have task section
        task_sections = [s for s in context.sections if s.name == "task"]
        assert len(task_sections) == 0

    def test_compile_raises_when_no_goal_or_issue(
        self,
        mock_profile_factory,
        code_diff
    ) -> None:
        """Test raises ValueError when state has no goal and no issue."""
        # State with no goal AND no issue
        profile = mock_profile_factory()
        state = ExecutionState(
            profile_id=profile.name,
            issue=None,
            goal=None,
            code_changes_for_review=code_diff
        )

        strategy = ReviewerContextStrategy()
        with pytest.raises(ValueError, match="No task or issue context found"):
            strategy.compile(state, profile)

    def test_system_prompt_template_produces_stable_prefix_per_persona(
        self,
        state_with_goal,
        mock_profile_factory
    ) -> None:
        """Test SYSTEM_PROMPT_TEMPLATE produces stable prefix per persona."""
        profile = mock_profile_factory()
        persona = "Security"

        # Compile multiple times with same persona
        strategy1 = ReviewerContextStrategy(persona=persona)
        context1 = strategy1.compile(state_with_goal, profile)
        strategy2 = ReviewerContextStrategy(persona=persona)
        context2 = strategy2.compile(state_with_goal, profile)

        # System prompts should be identical for same persona
        assert context1.system_prompt == context2.system_prompt

        # Should be different for different personas
        strategy3 = ReviewerContextStrategy(persona="Performance")
        context3 = strategy3.compile(state_with_goal, profile)
        assert context1.system_prompt != context3.system_prompt

    def test_compile_validates_allowed_sections(
        self,
        strategy,
        state_with_goal,
        mock_profile_factory
    ) -> None:
        """Test compile only produces allowed sections."""
        profile = mock_profile_factory()
        context = strategy.compile(state_with_goal, profile)

        # All sections should be in ALLOWED_SECTIONS
        for section in context.sections:
            assert section.name in ReviewerContextStrategy.ALLOWED_SECTIONS

    def test_to_messages_integration(
        self,
        state_with_goal,
        mock_profile_factory
    ) -> None:
        """Test compiled context can be converted to messages."""
        profile = mock_profile_factory()
        strategy = ReviewerContextStrategy(persona="Security")
        context = strategy.compile(state_with_goal, profile)

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
    ) -> None:
        """Test raises ValueError when state has no code changes."""
        state, profile = mock_execution_state_factory(
            goal="Test goal",
            code_changes_for_review=None
        )

        strategy = ReviewerContextStrategy()
        with pytest.raises(ValueError, match="No code changes provided"):
            strategy.compile(state, profile)

    def test_compile_section_sources_for_debugging(
        self,
        strategy,
        state_with_goal,
        mock_profile_factory
    ) -> None:
        """Test sections have source metadata for debugging."""
        profile = mock_profile_factory()
        context = strategy.compile(state_with_goal, profile)

        # All sections should have source metadata with meaningful values
        for section in context.sections:
            assert section.source is not None
            assert section.source != ""

    def test_compile_default_persona(
        self,
        state_with_goal,
        mock_profile_factory
    ) -> None:
        """Test compile with default persona when not specified."""
        profile = mock_profile_factory()
        # Create strategy without explicit persona (should use default)
        strategy = ReviewerContextStrategy()
        context = strategy.compile(state_with_goal, profile)

        # Should have a system prompt even without explicit persona
        assert context.system_prompt is not None
        # Should contain default "General" persona
        assert "General" in context.system_prompt


class TestReviewerValidation:
    """Tests for Reviewer agent fallback behavior."""

    async def test_reviewer_auto_approves_empty_code_changes(
        self,
        mock_execution_state_factory,
    ) -> None:
        """Reviewer should auto-approve when code_changes is empty instead of raising.

        This prevents HTTP 500 errors when there are no changes to review.
        """
        from unittest.mock import AsyncMock, MagicMock

        from amelia.agents.reviewer import Reviewer

        state, profile = mock_execution_state_factory(
            code_changes_for_review=None
        )

        # Driver should never be called for empty changes
        mock_driver = MagicMock()
        mock_driver.generate = AsyncMock()

        reviewer = Reviewer(mock_driver)

        # Should NOT raise - should auto-approve
        result, session_id = await reviewer._single_review(
            state, "", profile, "General", workflow_id="test-workflow"
        )

        # Verify auto-approved result
        assert result is not None
        assert result.approved is True
        assert result.severity == "low"
        assert "No code changes to review" in result.comments

        # Driver should not have been called
        mock_driver.generate.assert_not_called()

    async def test_reviewer_auto_approves_whitespace_only_code_changes(
        self,
        mock_execution_state_factory,
    ) -> None:
        """Reviewer should auto-approve when code_changes is whitespace only."""
        from unittest.mock import AsyncMock, MagicMock

        from amelia.agents.reviewer import Reviewer

        state, profile = mock_execution_state_factory()

        mock_driver = MagicMock()
        mock_driver.generate = AsyncMock()

        reviewer = Reviewer(mock_driver)

        # Should NOT raise for whitespace-only changes
        result, _ = await reviewer._single_review(
            state, "   \n\t  ", profile, "General", workflow_id="test-workflow"
        )

        assert result.approved is True
        assert "No code changes to review" in result.comments
        mock_driver.generate.assert_not_called()

    async def test_reviewer_allows_no_goal_with_issue(
        self,
        mock_execution_state_factory,
        mock_async_driver_factory,
        mock_review_result_factory,
    ) -> None:
        """Reviewer should work without goal when issue is present.

        This allows reviewing with just issue context when no plan exists.
        """
        from amelia.agents.reviewer import Reviewer

        state, profile = mock_execution_state_factory(
            goal=None,
            code_changes_for_review="diff --git a/file.py"
        )

        mock_response = mock_review_result_factory()
        mock_driver = mock_async_driver_factory(generate_return=(mock_response, None))

        reviewer = Reviewer(mock_driver)

        # Should not raise - falls back to issue context
        result, _ = await reviewer.review(state, code_changes="diff --git a/file.py", profile=profile, workflow_id="test-workflow")
        assert result is not None


class TestReviewerSessionId:
    """Tests for Reviewer session_id handling."""

    async def test_reviewer_passes_session_id_to_driver(
        self,
        mock_execution_state_factory,
        mock_async_driver_factory,
        mock_review_result_factory,
    ) -> None:
        """Test that Reviewer passes session_id from state to driver."""
        from amelia.agents.reviewer import Reviewer

        mock_response = mock_review_result_factory(approved=True)
        mock_driver = mock_async_driver_factory(generate_return=(mock_response, "new-sess"))

        state, profile = mock_execution_state_factory(
            driver_session_id="review-sess-123",
            code_changes_for_review="diff content",
        )

        reviewer = Reviewer(mock_driver)
        result, result_session_id = await reviewer._single_review(state, "diff", profile, "General", workflow_id="wf-1")

        mock_driver.generate.assert_called_once()
        call_kwargs = mock_driver.generate.call_args.kwargs
        assert call_kwargs.get("session_id") == "review-sess-123"

        # Verify return value includes session_id
        assert result_session_id == "new-sess"
        assert result is not None


class TestReviewerNodeConfig:
    """Tests for call_reviewer_node using profile from config."""

    async def test_reviewer_node_uses_profile_from_config(
        self,
        mock_profile_factory,
        mock_issue_factory,
    ) -> None:
        """call_reviewer_node should get profile from config."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from langchain_core.runnables.config import RunnableConfig

        from amelia.core.orchestrator import call_reviewer_node
        from amelia.core.state import ExecutionState

        profile = mock_profile_factory()
        state = ExecutionState(
            profile_id=profile.name,
            issue=mock_issue_factory(),
            code_changes_for_review="diff content",
        )

        config: RunnableConfig = {
            "configurable": {
                "thread_id": "wf-test",
                "profile": profile,
            }
        }

        with patch("amelia.core.orchestrator.Reviewer") as mock_rev:
            mock_rev_instance = MagicMock()
            mock_rev_instance.review = AsyncMock(return_value=(MagicMock(approved=True), "sess-123"))
            mock_rev.return_value = mock_rev_instance

            await call_reviewer_node(state, config)

            # Verify Reviewer was created
            mock_rev.assert_called_once()
            # Verify review was called
            mock_rev_instance.review.assert_called_once()
