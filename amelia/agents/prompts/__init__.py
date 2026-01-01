# amelia/agents/prompts/__init__.py
"""Agent prompt configuration package.

Provides prompt defaults and resolution for configurable agent prompts.
"""
from amelia.agents.prompts.defaults import PROMPT_DEFAULTS, PromptDefault
from amelia.agents.prompts.models import (
    Prompt,
    PromptRepositoryProtocol,
    PromptVersion,
    ResolvedPrompt,
    WorkflowPromptVersion,
)
from amelia.agents.prompts.resolver import PromptResolver


__all__ = [
    "PROMPT_DEFAULTS",
    "Prompt",
    "PromptDefault",
    "PromptRepositoryProtocol",
    "PromptResolver",
    "PromptVersion",
    "ResolvedPrompt",
    "WorkflowPromptVersion",
]
