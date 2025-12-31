"""Tests for the Reviewer agent."""
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from amelia.agents.reviewer import (
    Reviewer,
    ReviewItem,
    StructuredReviewResult,
)
from amelia.core.state import ExecutionState
from amelia.core.types import Profile


class TestReviewItem:
    """Tests for ReviewItem model."""

    def test_review_item_frozen(self) -> None:
        """Test that ReviewItem is immutable."""
        item = ReviewItem(
            number=1,
            title="Test Issue",
            file_path="test.py",
            line=10,
            severity="major",
            issue="Found a bug",
            why="Could cause crash",
            fix="Add null check",
        )
        with pytest.raises(ValidationError):
            item.number = 2

    def test_review_item_severity_values(self) -> None:
        """Test that severity accepts only valid values."""
        for severity in ["critical", "major", "minor"]:
            item = ReviewItem(
                number=1,
                title="Test",
                file_path="test.py",
                line=1,
                severity=severity,  # type: ignore[arg-type]
                issue="Issue",
                why="Why",
                fix="Fix",
            )
            assert item.severity == severity


class TestStructuredReviewResult:
    """Tests for StructuredReviewResult model."""

    def test_structured_review_result_frozen(self) -> None:
        """Test that StructuredReviewResult is immutable."""
        result = StructuredReviewResult(
            summary="All good",
            items=[],
            good_patterns=["Clean code"],
            verdict="approved",
        )
        with pytest.raises(ValidationError):
            result.summary = "Changed"

    def test_structured_review_result_verdict_values(self) -> None:
        """Test that verdict accepts only valid values."""
        for verdict in ["approved", "needs_fixes", "blocked"]:
            result = StructuredReviewResult(
                summary="Review",
                items=[],
                verdict=verdict,  # type: ignore[arg-type]
            )
            assert result.verdict == verdict

    def test_structured_review_result_default_good_patterns(self) -> None:
        """Test that good_patterns defaults to empty list."""
        result = StructuredReviewResult(
            summary="Review",
            items=[],
            verdict="approved",
        )
        assert result.good_patterns == []


class TestStructuredReview:
    """Tests for Reviewer.structured_review method."""

    @pytest.fixture
    def reviewer(self, mock_driver: MagicMock) -> Reviewer:
        """Create a Reviewer instance with mocked driver."""
        return Reviewer(driver=mock_driver)

    @pytest.fixture
    def structured_review_output(self) -> StructuredReviewResult:
        """Create a sample structured review output."""
        return StructuredReviewResult(
            summary="Code review completed with minor issues",
            items=[
                ReviewItem(
                    number=1,
                    title="Missing type hint",
                    file_path="src/main.py",
                    line=15,
                    severity="minor",
                    issue="Function lacks return type annotation",
                    why="Type hints improve code maintainability",
                    fix="Add -> None return type",
                ),
                ReviewItem(
                    number=2,
                    title="Potential null reference",
                    file_path="src/utils.py",
                    line=42,
                    severity="major",
                    issue="Variable may be None before use",
                    why="Could cause runtime exception",
                    fix="Add null check before accessing",
                ),
            ],
            good_patterns=["Consistent naming", "Good error handling"],
            verdict="needs_fixes",
        )

    async def test_structured_review_returns_structured_result(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
        structured_review_output: StructuredReviewResult,
    ) -> None:
        """Test structured_review returns StructuredReviewResult."""
        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        mock_driver.generate = AsyncMock(
            return_value=(structured_review_output, "session-456")
        )

        reviewer = Reviewer(driver=mock_driver)
        result, session_id = await reviewer.structured_review(
            state,
            code_changes="diff content",
            profile=profile,
            workflow_id="wf-123",
        )

        assert isinstance(result, StructuredReviewResult)
        assert session_id == "session-456"
        assert result.summary == "Code review completed with minor issues"
        assert len(result.items) == 2
        assert result.verdict == "needs_fixes"
        assert len(result.good_patterns) == 2

        # Verify driver was called with correct schema
        mock_driver.generate.assert_called_once()
        call_kwargs = mock_driver.generate.call_args.kwargs
        assert call_kwargs["schema"] == StructuredReviewResult

    async def test_structured_review_empty_changes_auto_approves(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test empty code changes result in auto-approval."""
        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        reviewer = Reviewer(driver=mock_driver)

        # Test with empty string
        result, session_id = await reviewer.structured_review(
            state,
            code_changes="",
            profile=profile,
            workflow_id="wf-123",
        )

        assert result.verdict == "approved"
        assert result.items == []
        assert "No code changes" in result.summary

        # Driver should NOT be called for empty changes
        mock_driver.generate.assert_not_called()

    async def test_structured_review_whitespace_only_auto_approves(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test whitespace-only code changes result in auto-approval."""
        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        reviewer = Reviewer(driver=mock_driver)

        result, _ = await reviewer.structured_review(
            state,
            code_changes="   \n\t  ",
            profile=profile,
            workflow_id="wf-123",
        )

        assert result.verdict == "approved"
        assert result.items == []
        mock_driver.generate.assert_not_called()

    async def test_structured_review_with_stream_emitter(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
        structured_review_output: StructuredReviewResult,
    ) -> None:
        """Test that stream emitter is called during structured review."""
        stream_emitter = AsyncMock()

        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        mock_driver.generate = AsyncMock(
            return_value=(structured_review_output, None)
        )

        reviewer = Reviewer(driver=mock_driver, stream_emitter=stream_emitter)
        await reviewer.structured_review(
            state,
            code_changes="diff content",
            profile=profile,
            workflow_id="wf-123",
        )

        # Verify stream emitter was called
        stream_emitter.assert_called_once()
        call_args = stream_emitter.call_args[0][0]
        assert call_args.agent == "reviewer"
        assert call_args.workflow_id == "wf-123"

    async def test_structured_review_builds_prompt_with_goal(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that prompt includes goal when available."""
        state, profile = mock_execution_state_factory(
            goal="Implement authentication",
        )

        review_output = StructuredReviewResult(
            summary="Review",
            items=[],
            verdict="approved",
        )
        mock_driver.generate = AsyncMock(return_value=(review_output, None))

        reviewer = Reviewer(driver=mock_driver)
        await reviewer.structured_review(
            state,
            code_changes="diff content",
            profile=profile,
            workflow_id="wf-123",
        )

        # Check that prompt contains the goal
        call_args = mock_driver.generate.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "Implement authentication" in prompt

    async def test_structured_review_builds_prompt_with_issue_fallback(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that prompt uses issue context when no goal available."""
        state, profile = mock_execution_state_factory(
            goal=None,  # No goal
        )

        review_output = StructuredReviewResult(
            summary="Review",
            items=[],
            verdict="approved",
        )
        mock_driver.generate = AsyncMock(return_value=(review_output, None))

        reviewer = Reviewer(driver=mock_driver)
        await reviewer.structured_review(
            state,
            code_changes="diff content",
            profile=profile,
            workflow_id="wf-123",
        )

        # Check that prompt contains issue context
        call_args = mock_driver.generate.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "Test Issue" in prompt or "Issue" in prompt

    async def test_structured_review_uses_structured_system_prompt(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that structured_review uses STRUCTURED_SYSTEM_PROMPT."""
        state, profile = mock_execution_state_factory(
            goal="Test goal",
        )

        review_output = StructuredReviewResult(
            summary="Review",
            items=[],
            verdict="approved",
        )
        mock_driver.generate = AsyncMock(return_value=(review_output, None))

        reviewer = Reviewer(driver=mock_driver)
        await reviewer.structured_review(
            state,
            code_changes="diff content",
            profile=profile,
            workflow_id="wf-123",
        )

        # Verify system prompt is the structured one
        call_args = mock_driver.generate.call_args
        system_prompt = call_args.kwargs.get("system_prompt")
        assert "OUTPUT FORMAT" in system_prompt
        assert "SEVERITY LEVELS" in system_prompt


class TestReviewer:
    """Tests for Reviewer agent review method."""

    async def test_review_requires_context(
        self,
        mock_driver: MagicMock,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Test that review raises error when no task or issue context."""
        # Create state manually without issue or goal (factory defaults issue)
        profile = mock_profile_factory()
        state = ExecutionState(
            profile_id=profile.name,
            issue=None,
            goal=None,
        )

        reviewer = Reviewer(driver=mock_driver)
        with pytest.raises(ValueError, match="No task or issue context"):
            await reviewer.review(
                state,
                code_changes="diff content",
                profile=profile,
                workflow_id="wf-123",
            )

    async def test_review_empty_changes_auto_approves(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that empty code changes result in auto-approval."""
        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        reviewer = Reviewer(driver=mock_driver)
        result, _ = await reviewer.review(
            state,
            code_changes="",
            profile=profile,
            workflow_id="wf-123",
        )

        assert result.approved is True
        assert "No code changes" in result.comments[0]
        mock_driver.generate.assert_not_called()
