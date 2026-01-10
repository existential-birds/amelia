"""Tests for Reviewer agent prompt injection."""
from unittest.mock import MagicMock

from amelia.agents.reviewer import Reviewer


class TestReviewerPromptInjection:
    """Tests for Reviewer agent prompt injection."""

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

    async def test_falls_back_to_class_default_for_agentic(
        self,
        mock_driver: MagicMock,
    ) -> None:
        """Should use class default when agentic prompt not injected."""
        reviewer = Reviewer(mock_driver)  # No prompts injected
        # Should contain agentic review markers
        assert "git diff" in reviewer.agentic_prompt
        assert "Skill" in reviewer.agentic_prompt

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
