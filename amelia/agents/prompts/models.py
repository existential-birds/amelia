# amelia/agents/prompts/models.py
"""Pydantic models for prompt configuration.

Provides data models for prompts, versions, and resolution results.
"""
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, Field, field_validator


class Prompt(BaseModel):
    """A prompt definition (one per agent prompt type).

    Attributes:
        id: Unique identifier (e.g., "architect.system").
        agent: Agent name (architect, developer, reviewer).
        name: Human-readable name.
        description: What this prompt controls.
        current_version_id: Active version ID, or None to use default.
    """

    id: str
    agent: str
    name: str
    description: str | None = None
    current_version_id: str | None = None


class PromptVersion(BaseModel):
    """A version of a prompt (append-only history).

    Attributes:
        id: Unique version identifier (UUID).
        prompt_id: Reference to parent prompt.
        version_number: Sequential version number.
        content: The prompt text content.
        created_at: When this version was created.
        change_note: Optional note describing the change.
    """

    id: str
    prompt_id: str
    version_number: int
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    change_note: str | None = None

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        """Validate that content is not empty."""
        if not v.strip():
            raise ValueError("Prompt content cannot be empty")
        return v


class ResolvedPrompt(BaseModel):
    """Result of prompt resolution (custom or default).

    Attributes:
        prompt_id: The prompt identifier.
        content: The resolved prompt text.
        version_id: Version ID if using custom, None if default.
        version_number: Version number if using custom.
        is_default: True if using hardcoded default.
    """

    prompt_id: str
    content: str
    version_id: str | None = None
    version_number: int | None = None
    is_default: bool = True


class WorkflowPromptVersion(BaseModel):
    """Links a workflow to the prompt versions it used.

    Attributes:
        workflow_id: The workflow ID.
        prompt_id: The prompt ID.
        version_id: The version ID used by this workflow.
    """

    workflow_id: str
    prompt_id: str
    version_id: str


class PromptRepositoryProtocol(Protocol):
    """Protocol for prompt repository operations.

    Defines the interface that PromptResolver depends on.
    This allows for dependency injection and easier testing.
    """

    async def get_prompt(self, prompt_id: str) -> Prompt | None:
        """Get a prompt by ID.

        Args:
            prompt_id: The prompt identifier.

        Returns:
            The prompt if found, None otherwise.
        """
        ...

    async def get_version(self, version_id: str) -> PromptVersion | None:
        """Get a specific version by ID.

        Args:
            version_id: The version identifier.

        Returns:
            The version if found, None otherwise.
        """
        ...

    async def record_workflow_prompt(
        self,
        workflow_id: str,
        prompt_id: str,
        version_id: str,
    ) -> None:
        """Record which prompt version a workflow used.

        Args:
            workflow_id: The workflow identifier.
            prompt_id: The prompt identifier.
            version_id: The version identifier.
        """
        ...
