"""Tests for brainstormer prompt constants."""

from amelia.server.services.brainstormer_agent import (
    BRAINSTORMER_FILESYSTEM_PROMPT,
    BRAINSTORMER_SYSTEM_PROMPT,
    BRAINSTORMER_USER_PROMPT_TEMPLATE,
)


class TestBrainstormerSystemPrompt:
    """Tests for BRAINSTORMER_SYSTEM_PROMPT constant."""

    def test_system_prompt_contains_role_section(self) -> None:
        """System prompt should define the agent's role."""
        assert "# Role" in BRAINSTORMER_SYSTEM_PROMPT

    def test_system_prompt_emphasizes_no_code(self) -> None:
        """System prompt should emphasize no implementation code."""
        assert "NOT an implementer" in BRAINSTORMER_SYSTEM_PROMPT
        assert "NEVER write implementation code" in BRAINSTORMER_SYSTEM_PROMPT

    def test_system_prompt_contains_process_section(self) -> None:
        """System prompt should define the process."""
        assert "# Process" in BRAINSTORMER_SYSTEM_PROMPT

    def test_system_prompt_contains_principles_section(self) -> None:
        """System prompt should define principles."""
        assert "# Principles" in BRAINSTORMER_SYSTEM_PROMPT


class TestBrainstormerUserPromptTemplate:
    """Tests for BRAINSTORMER_USER_PROMPT_TEMPLATE constant."""

    def test_template_has_placeholder(self) -> None:
        """Template should have {idea} placeholder."""
        assert "{idea}" in BRAINSTORMER_USER_PROMPT_TEMPLATE

    def test_template_formats_correctly(self) -> None:
        """Template should format with idea correctly."""
        result = BRAINSTORMER_USER_PROMPT_TEMPLATE.format(idea="build a chat app")
        assert "build a chat app" in result


class TestBrainstormerFilesystemPrompt:
    """Tests for updated BRAINSTORMER_FILESYSTEM_PROMPT."""

    def test_filesystem_prompt_restricts_writing(self) -> None:
        """Filesystem prompt should restrict writing to markdown only."""
        assert "ONLY write markdown files" in BRAINSTORMER_FILESYSTEM_PROMPT
        assert ".md" in BRAINSTORMER_FILESYSTEM_PROMPT
