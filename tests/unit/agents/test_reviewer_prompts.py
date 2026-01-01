"""Tests for Reviewer agent prompt injection."""
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.agents.reviewer import Reviewer, ReviewResponse, StructuredReviewResult
from amelia.core.state import ExecutionState
from amelia.core.types import Profile


class TestReviewerPromptInjection:
    """Tests for Reviewer agent prompt injection."""

    @pytest.fixture
    def review_response(self) -> ReviewResponse:
        """Sample review response from driver."""
        return ReviewResponse(
            approved=True,
            comments=["Looks good"],
            severity="low",
        )

    @pytest.fixture
    def structured_review_response(self) -> StructuredReviewResult:
        """Sample structured review response from driver."""
        return StructuredReviewResult(
            summary="Code looks good",
            items=[],
            good_patterns=["Clean code"],
            verdict="approved",
        )

    async def test_uses_injected_structured_prompt(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
        structured_review_response: StructuredReviewResult,
    ) -> None:
        """Should use injected structured review prompt."""
        custom_prompt = "Custom structured reviewer..."
        prompts = {"reviewer.structured": custom_prompt}

        state, profile = mock_execution_state_factory(goal="Implement feature")
        mock_driver.generate = AsyncMock(return_value=(
            structured_review_response,
            "session-1",
        ))

        reviewer = Reviewer(mock_driver, prompts=prompts)
        await reviewer.structured_review(
            state,
            code_changes="diff content",
            profile=profile,
            workflow_id="wf-123",
        )

        call_args = mock_driver.generate.call_args
        assert call_args.kwargs["system_prompt"] == custom_prompt

    async def test_uses_injected_agentic_prompt(
        self,
        mock_driver: MagicMock,
    ) -> None:
        """Should use injected agentic review prompt property."""
        custom_prompt = "Custom agentic reviewer..."
        prompts = {"reviewer.agentic": custom_prompt}

        reviewer = Reviewer(mock_driver, prompts=prompts)
        # Test the property directly since agentic_review is complex
        assert reviewer.agentic_prompt == custom_prompt

    async def test_uses_injected_template_prompt(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
        review_response: ReviewResponse,
    ) -> None:
        """Should use injected template prompt for single review."""
        custom_template = "Custom {persona} reviewer..."
        prompts = {"reviewer.template": custom_template}

        state, profile = mock_execution_state_factory(goal="Implement feature")
        mock_driver.generate = AsyncMock(return_value=(
            review_response,
            "session-1",
        ))

        reviewer = Reviewer(mock_driver, prompts=prompts)
        await reviewer.review(
            state,
            code_changes="diff content",
            profile=profile,
            workflow_id="wf-123",
        )

        call_args = mock_driver.generate.call_args
        # The template should have been formatted with persona "General"
        assert call_args.kwargs["system_prompt"] == "Custom General reviewer..."

    async def test_falls_back_to_class_default_for_structured(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
        structured_review_response: StructuredReviewResult,
    ) -> None:
        """Should use class default when structured prompt not injected."""
        state, profile = mock_execution_state_factory(goal="Implement feature")
        mock_driver.generate = AsyncMock(return_value=(
            structured_review_response,
            "session-1",
        ))

        reviewer = Reviewer(mock_driver)  # No prompts injected
        await reviewer.structured_review(
            state,
            code_changes="diff content",
            profile=profile,
            workflow_id="wf-123",
        )

        call_args = mock_driver.generate.call_args
        system_prompt = call_args.kwargs["system_prompt"]
        # Should contain structured review prompt markers
        assert "OUTPUT FORMAT" in system_prompt
        assert "SEVERITY LEVELS" in system_prompt

    async def test_falls_back_to_class_default_for_agentic(
        self,
        mock_driver: MagicMock,
    ) -> None:
        """Should use class default when agentic prompt not injected."""
        reviewer = Reviewer(mock_driver)  # No prompts injected
        # Should contain agentic review markers
        assert "git diff" in reviewer.agentic_prompt
        assert "Skill" in reviewer.agentic_prompt

    async def test_structured_prompt_property(
        self,
        mock_driver: MagicMock,
    ) -> None:
        """Test structured_prompt property returns correct value."""
        custom_prompt = "Custom structured prompt"

        # With custom prompt
        reviewer_custom = Reviewer(mock_driver, prompts={"reviewer.structured": custom_prompt})
        assert reviewer_custom.structured_prompt == custom_prompt

        # Without custom prompt (default)
        reviewer_default = Reviewer(mock_driver)
        assert "OUTPUT FORMAT" in reviewer_default.structured_prompt

    async def test_agentic_prompt_property(
        self,
        mock_driver: MagicMock,
    ) -> None:
        """Test agentic_prompt property returns correct value."""
        custom_prompt = "Custom agentic prompt with {base_commit}"

        # With custom prompt
        reviewer_custom = Reviewer(mock_driver, prompts={"reviewer.agentic": custom_prompt})
        assert reviewer_custom.agentic_prompt == custom_prompt

        # Without custom prompt (default)
        reviewer_default = Reviewer(mock_driver)
        assert "base_commit" in reviewer_default.agentic_prompt

    async def test_template_prompt_property(
        self,
        mock_driver: MagicMock,
    ) -> None:
        """Test template_prompt property returns correct value."""
        custom_template = "Custom {persona} template"

        # With custom prompt
        reviewer_custom = Reviewer(mock_driver, prompts={"reviewer.template": custom_template})
        assert reviewer_custom.template_prompt == custom_template

        # Without custom prompt (default)
        reviewer_default = Reviewer(mock_driver)
        assert "{persona}" in reviewer_default.template_prompt

    async def test_empty_prompts_dict_uses_defaults(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
        structured_review_response: StructuredReviewResult,
    ) -> None:
        """Empty prompts dict should fall back to defaults."""
        state, profile = mock_execution_state_factory(goal="Implement feature")
        mock_driver.generate = AsyncMock(return_value=(
            structured_review_response,
            "session-1",
        ))

        reviewer = Reviewer(mock_driver, prompts={})  # Empty dict
        await reviewer.structured_review(
            state,
            code_changes="diff content",
            profile=profile,
            workflow_id="wf-123",
        )

        call_args = mock_driver.generate.call_args
        system_prompt = call_args.kwargs["system_prompt"]
        assert "OUTPUT FORMAT" in system_prompt
