# tests/unit/agents/prompts/test_models.py
"""Tests for prompt Pydantic models."""
import pytest
from pydantic import ValidationError

from amelia.agents.prompts.models import (
    Prompt,
    PromptVersion,
    ResolvedPrompt,
    WorkflowPromptVersion,
)


class TestPrompt:
    """Tests for Prompt model."""

    def test_create_prompt(self):
        """Should create a valid Prompt."""
        prompt = Prompt(
            id="architect.system",
            agent="architect",
            name="Architect System Prompt",
            description="Defines the architect's role",
            current_version_id=None,
        )
        assert prompt.id == "architect.system"
        assert prompt.agent == "architect"
        assert prompt.current_version_id is None

    def test_prompt_with_version(self):
        """Should allow setting current_version_id."""
        prompt = Prompt(
            id="architect.system",
            agent="architect",
            name="Architect System Prompt",
            description="Defines the architect's role",
            current_version_id="version-123",
        )
        assert prompt.current_version_id == "version-123"


class TestPromptVersion:
    """Tests for PromptVersion model."""

    def test_create_version(self):
        """Should create a valid PromptVersion."""
        version = PromptVersion(
            id="v-123",
            prompt_id="architect.system",
            version_number=1,
            content="You are an architect...",
            change_note="Initial version",
        )
        assert version.id == "v-123"
        assert version.version_number == 1
        assert version.created_at is not None

    def test_version_requires_content(self):
        """Should reject empty content."""
        with pytest.raises(ValidationError):
            PromptVersion(
                id="v-123",
                prompt_id="architect.system",
                version_number=1,
                content="",
            )


class TestResolvedPrompt:
    """Tests for ResolvedPrompt model."""

    def test_resolved_default_prompt(self):
        """Should represent a default prompt."""
        resolved = ResolvedPrompt(
            prompt_id="architect.system",
            content="You are an architect...",
            version_id=None,
            version_number=None,
            is_default=True,
        )
        assert resolved.is_default is True
        assert resolved.version_id is None

    def test_resolved_custom_prompt(self):
        """Should represent a custom prompt version."""
        resolved = ResolvedPrompt(
            prompt_id="architect.system",
            content="Custom architect prompt...",
            version_id="v-123",
            version_number=3,
            is_default=False,
        )
        assert resolved.is_default is False
        assert resolved.version_number == 3


class TestWorkflowPromptVersion:
    """Tests for WorkflowPromptVersion model."""

    def test_create_workflow_prompt_version(self):
        """Should link workflow to prompt version."""
        wpv = WorkflowPromptVersion(
            workflow_id="wf-123",
            prompt_id="architect.system",
            version_id="v-456",
        )
        assert wpv.workflow_id == "wf-123"
        assert wpv.prompt_id == "architect.system"
        assert wpv.version_id == "v-456"
