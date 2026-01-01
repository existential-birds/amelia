# amelia/agents/prompts/resolver.py
"""Prompt resolution for agents.

Provides the PromptResolver that returns current prompt content,
falling back to defaults when no custom version exists.
"""
from loguru import logger

from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
from amelia.agents.prompts.models import PromptRepositoryProtocol, ResolvedPrompt


class PromptResolver:
    """Resolves prompts from database or defaults.

    Handles the logic of returning custom versions when available
    and falling back to hardcoded defaults otherwise.

    Attributes:
        repository: Database repository for prompt data.
    """

    def __init__(self, repository: PromptRepositoryProtocol) -> None:
        """Initialize resolver with repository.

        Args:
            repository: Database repository for prompts.
        """
        self.repository = repository

    async def get_prompt(self, prompt_id: str) -> ResolvedPrompt:
        """Get the active prompt content.

        Returns custom version if set, otherwise returns default.
        Falls back to default on any database error.

        Args:
            prompt_id: The prompt identifier.

        Returns:
            Resolved prompt with content and metadata.

        Raises:
            ValueError: If prompt_id is unknown (not in defaults).
        """
        try:
            prompt = await self.repository.get_prompt(prompt_id)
            if prompt and prompt.current_version_id:
                version = await self.repository.get_version(prompt.current_version_id)
                if version:
                    return ResolvedPrompt(
                        prompt_id=prompt_id,
                        content=version.content,
                        version_id=version.id,
                        version_number=version.version_number,
                        is_default=False,
                    )
        except Exception as e:
            logger.warning(
                "Failed to get custom prompt, using default",
                prompt_id=prompt_id,
                error=str(e),
            )

        # Fall through to default
        default = PROMPT_DEFAULTS.get(prompt_id)
        if not default:
            raise ValueError(f"Unknown prompt: {prompt_id}")

        return ResolvedPrompt(
            prompt_id=prompt_id,
            content=default.content,
            version_id=None,
            version_number=None,
            is_default=True,
        )

    async def get_all_active(self) -> dict[str, ResolvedPrompt]:
        """Get all prompts for workflow startup.

        Returns:
            Dictionary mapping prompt_id to resolved prompt.
        """
        result = {}
        for prompt_id in PROMPT_DEFAULTS:
            result[prompt_id] = await self.get_prompt(prompt_id)
        return result

    async def record_for_workflow(self, workflow_id: str) -> None:
        """Record which prompt versions a workflow uses.

        Only records custom versions (not defaults) since defaults
        are immutable and can be reconstructed from code.

        Args:
            workflow_id: The workflow identifier.
        """
        prompts = await self.get_all_active()
        for prompt_id, resolved in prompts.items():
            if resolved.version_id:  # Only record custom versions
                await self.repository.record_workflow_prompt(
                    workflow_id, prompt_id, resolved.version_id
                )
