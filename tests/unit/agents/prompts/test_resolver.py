# tests/unit/agents/prompts/test_resolver.py
"""Tests for PromptResolver."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
from amelia.agents.prompts.models import Prompt, PromptVersion
from amelia.agents.prompts.resolver import PromptResolver


@pytest.fixture
def mock_repository():
    """Create a mock PromptRepository."""
    repo = MagicMock()
    repo.get_prompt = AsyncMock(return_value=None)
    repo.get_version = AsyncMock(return_value=None)
    repo.record_workflow_prompt = AsyncMock()
    return repo


class TestGetPrompt:
    """Tests for get_prompt method."""

    async def test_returns_default_when_no_custom_version(self, mock_repository) -> None:
        """Should return default when no custom version set."""
        mock_repository.get_prompt.return_value = Prompt(
            id="architect.system",
            agent="architect",
            name="Architect System Prompt",
            current_version_id=None,  # No custom version
        )
        resolver = PromptResolver(mock_repository)
        result = await resolver.get_prompt("architect.system")

        assert result.is_default is True
        assert result.version_id is None
        assert result.content == PROMPT_DEFAULTS["architect.system"].content

    async def test_returns_custom_version_when_set(self, mock_repository) -> None:
        """Should return custom version content when active."""
        custom_content = "Custom architect prompt..."
        mock_repository.get_prompt.return_value = Prompt(
            id="architect.system",
            agent="architect",
            name="Architect System Prompt",
            current_version_id="v-123",
        )
        mock_repository.get_version.return_value = PromptVersion(
            id="v-123",
            prompt_id="architect.system",
            version_number=3,
            content=custom_content,
        )
        resolver = PromptResolver(mock_repository)
        result = await resolver.get_prompt("architect.system")

        assert result.is_default is False
        assert result.version_id == "v-123"
        assert result.version_number == 3
        assert result.content == custom_content

    async def test_falls_back_to_default_on_db_error(self, mock_repository) -> None:
        """Should return default when database fails."""
        mock_repository.get_prompt.side_effect = Exception("DB error")
        resolver = PromptResolver(mock_repository)
        result = await resolver.get_prompt("architect.system")

        assert result.is_default is True
        assert result.content == PROMPT_DEFAULTS["architect.system"].content

    async def test_raises_for_unknown_prompt(self, mock_repository) -> None:
        """Should raise ValueError for unknown prompt ID."""
        mock_repository.get_prompt.return_value = None
        resolver = PromptResolver(mock_repository)

        with pytest.raises(ValueError, match="Unknown prompt"):
            await resolver.get_prompt("nonexistent.prompt")


class TestGetAllActive:
    """Tests for get_all_active method."""

    async def test_returns_all_prompts(self, mock_repository) -> None:
        """Should return all prompt defaults."""
        mock_repository.get_prompt.return_value = None  # All use defaults
        resolver = PromptResolver(mock_repository)
        result = await resolver.get_all_active()

        assert len(result) == len(PROMPT_DEFAULTS)
        assert "architect.system" in result
        assert "architect.plan" in result
        assert "reviewer.structured" in result


class TestRecordForWorkflow:
    """Tests for record_for_workflow method."""

    async def test_records_custom_versions_only(self, mock_repository) -> None:
        """Should only record custom versions, not defaults."""
        mock_repository.get_prompt.return_value = Prompt(
            id="architect.system",
            agent="architect",
            name="Test",
            current_version_id="v-123",
        )
        mock_repository.get_version.return_value = PromptVersion(
            id="v-123",
            prompt_id="architect.system",
            version_number=1,
            content="Custom content",
        )
        resolver = PromptResolver(mock_repository)
        await resolver.record_for_workflow("wf-1")

        # Should have been called for each prompt with a version_id
        assert mock_repository.record_workflow_prompt.called

    async def test_does_not_record_defaults(self, mock_repository) -> None:
        """Should not record anything when all use defaults."""
        mock_repository.get_prompt.return_value = None  # All defaults
        resolver = PromptResolver(mock_repository)
        await resolver.record_for_workflow("wf-1")

        mock_repository.record_workflow_prompt.assert_not_called()
