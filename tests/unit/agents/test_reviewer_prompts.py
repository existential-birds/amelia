"""Tests for Reviewer agent prompt injection."""
from collections.abc import Callable
from unittest.mock import MagicMock, patch

import pytest

from amelia.agents.reviewer import Reviewer
from amelia.core.types import AgentConfig


@pytest.fixture
def create_reviewer(mock_driver: MagicMock) -> Callable[..., Reviewer]:
    """Factory fixture to create Reviewer with mock driver injected."""
    def _create(prompts: dict[str, str] | None = None) -> Reviewer:
        with patch("amelia.agents.reviewer.get_driver", return_value=mock_driver):
            config = AgentConfig(driver="cli", model="sonnet", options={})
            return Reviewer(config, prompts=prompts)
    return _create


class TestReviewerPromptInjection:
    """Tests for Reviewer agent prompt injection."""

    async def test_uses_injected_agentic_prompt(
        self,
        create_reviewer: Callable[..., Reviewer],
    ) -> None:
        """Should use injected agentic review prompt property."""
        custom_prompt = "Custom agentic reviewer..."
        prompts = {"reviewer.agentic": custom_prompt}

        reviewer = create_reviewer(prompts=prompts)
        # Test the property directly since agentic_review is complex
        assert reviewer.agentic_prompt == custom_prompt

    async def test_falls_back_to_class_default_for_agentic(
        self,
        create_reviewer: Callable[..., Reviewer],
    ) -> None:
        """Should use class default when agentic prompt not injected."""
        reviewer = create_reviewer()  # No prompts injected
        # Should contain agentic review markers
        assert "git diff" in reviewer.agentic_prompt
        assert "Skill" in reviewer.agentic_prompt

    async def test_agentic_prompt_property(
        self,
        create_reviewer: Callable[..., Reviewer],
    ) -> None:
        """Test agentic_prompt property returns correct value."""
        custom_prompt = "Custom agentic prompt with {base_commit}"

        # With custom prompt
        reviewer_custom = create_reviewer(prompts={"reviewer.agentic": custom_prompt})
        assert reviewer_custom.agentic_prompt == custom_prompt

        # Without custom prompt (default)
        reviewer_default = create_reviewer()
        assert "base_commit" in reviewer_default.agentic_prompt
