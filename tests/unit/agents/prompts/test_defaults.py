# tests/unit/agents/prompts/test_defaults.py
"""Tests for hardcoded prompt defaults."""
import pytest
from pydantic import ValidationError

from amelia.agents.prompts.defaults import PROMPT_DEFAULTS


def test_prompt_default_is_frozen() -> None:
    """PromptDefault should be immutable."""
    default = PROMPT_DEFAULTS["architect.plan"]
    with pytest.raises(ValidationError, match="Instance is frozen"):
        default.agent = "modified"  # type: ignore[misc]  # Intentional: testing frozen model rejects assignment


def test_developer_system_prompt_default_exists() -> None:
    """Developer system prompt should be present in defaults."""
    assert "developer.system" in PROMPT_DEFAULTS
    default = PROMPT_DEFAULTS["developer.system"]
    assert default.agent == "developer"
    assert len(default.content) > 50
