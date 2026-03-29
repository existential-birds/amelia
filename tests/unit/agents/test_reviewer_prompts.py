"""Tests for Reviewer agent prompt injection."""
from collections.abc import Callable
from unittest.mock import MagicMock, patch

import pytest

from amelia.agents.reviewer import Reviewer
from amelia.core.types import AgentConfig, DriverType


@pytest.fixture
def create_reviewer(mock_driver: MagicMock) -> Callable[..., Reviewer]:
    """Factory fixture to create Reviewer with mock driver injected."""
    def _create(prompts: dict[str, str] | None = None) -> Reviewer:
        with patch("amelia.agents.reviewer.get_driver", return_value=mock_driver):
            config = AgentConfig(driver=DriverType.CLAUDE, model="sonnet", options={})
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
        assert "diff_path" in reviewer.agentic_prompt
        assert "review_guidelines" in reviewer.agentic_prompt

    async def test_agentic_prompt_property(
        self,
        create_reviewer: Callable[..., Reviewer],
    ) -> None:
        """Test agentic_prompt property returns correct value."""
        custom_prompt = "Custom agentic prompt with {diff_path}"

        # With custom prompt
        reviewer_custom = create_reviewer(prompts={"reviewer.agentic": custom_prompt})
        assert reviewer_custom.agentic_prompt == custom_prompt

        # Without custom prompt (default)
        reviewer_default = create_reviewer()
        assert "diff_path" in reviewer_default.agentic_prompt


class TestAgenticReviewPromptDiffPath:
    """Tests for AGENTIC_REVIEW_PROMPT diff_path integration."""

    def test_agentic_review_prompt_contains_diff_path_placeholder(self) -> None:
        """AGENTIC_REVIEW_PROMPT must contain {diff_path} format placeholder.

        The reviewer should read the diff from a pre-fetched file rather than
        running git diff itself.
        """
        assert "{diff_path}" in Reviewer.AGENTIC_REVIEW_PROMPT, (
            "AGENTIC_REVIEW_PROMPT must contain {diff_path} placeholder for pre-fetched diff"
        )

    def test_agentic_review_prompt_does_not_instruct_git_diff(self) -> None:
        """AGENTIC_REVIEW_PROMPT must NOT instruct agent to run 'git diff --name-only {base_commit}'.

        The diff is pre-fetched and provided via diff_path, so the reviewer should
        read from the file instead of running git diff.
        """
        prompt = Reviewer.AGENTIC_REVIEW_PROMPT
        assert "git diff --name-only {base_commit}" not in prompt, (
            "AGENTIC_REVIEW_PROMPT must not instruct 'git diff --name-only {base_commit}' — "
            "use pre-fetched diff_path instead"
        )
        assert "git diff {base_commit}" not in prompt, (
            "AGENTIC_REVIEW_PROMPT must not instruct 'git diff {base_commit}' — "
            "use pre-fetched diff_path instead"
        )

    def test_prompt_defaults_reviewer_has_diff_path_placeholder(self) -> None:
        """PROMPT_DEFAULTS['reviewer.agentic'] must also contain {diff_path} placeholder."""
        from amelia.agents.prompts.defaults import PROMPT_DEFAULTS

        content = PROMPT_DEFAULTS["reviewer.agentic"].content
        assert "{diff_path}" in content, (
            "PROMPT_DEFAULTS['reviewer.agentic'] must contain {diff_path} placeholder"
        )

    def test_prompt_defaults_reviewer_does_not_instruct_git_diff(self) -> None:
        """PROMPT_DEFAULTS['reviewer.agentic'] must NOT instruct running git diff with base_commit."""
        from amelia.agents.prompts.defaults import PROMPT_DEFAULTS

        content = PROMPT_DEFAULTS["reviewer.agentic"].content
        assert "git diff --name-only {base_commit}" not in content, (
            "PROMPT_DEFAULTS['reviewer.agentic'] must not instruct 'git diff --name-only {base_commit}'"
        )
        assert "git diff {base_commit}" not in content, (
            "PROMPT_DEFAULTS['reviewer.agentic'] must not instruct 'git diff {base_commit}'"
        )


class TestReviewOutputFormatConstant:
    """Tests for REVIEW_OUTPUT_FORMAT shared constant."""

    def test_review_output_format_in_both_prompts(self) -> None:
        """REVIEW_OUTPUT_FORMAT must appear in both AGENTIC_REVIEW_PROMPT and PROMPT_DEFAULTS."""
        from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
        from amelia.agents.reviewer import REVIEW_OUTPUT_FORMAT, Reviewer

        assert REVIEW_OUTPUT_FORMAT in Reviewer.AGENTIC_REVIEW_PROMPT, (
            "REVIEW_OUTPUT_FORMAT missing from Reviewer.AGENTIC_REVIEW_PROMPT"
        )
        assert REVIEW_OUTPUT_FORMAT in PROMPT_DEFAULTS["reviewer.agentic"].content, (
            "REVIEW_OUTPUT_FORMAT missing from PROMPT_DEFAULTS['reviewer.agentic']"
        )

    def test_prompt_defaults_reviewer_has_ready_verdict_not_json(self) -> None:
        """PROMPT_DEFAULTS['reviewer.agentic'] must use markdown Ready: format, not JSON."""
        from amelia.agents.prompts.defaults import PROMPT_DEFAULTS

        content = PROMPT_DEFAULTS["reviewer.agentic"].content
        assert "Ready: Yes" in content, "Prompt must instruct Ready: Yes|No verdict"
        assert '"approved"' not in content, "Prompt must not instruct JSON output"
