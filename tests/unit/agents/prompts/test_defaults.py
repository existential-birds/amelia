# tests/unit/agents/prompts/test_defaults.py
"""Tests for hardcoded prompt defaults."""
import pytest
from pydantic import ValidationError

from amelia.agents.prompts.defaults import PROMPT_DEFAULTS


def test_prompt_default_is_frozen() -> None:
    """PromptDefault should be immutable."""
    default = PROMPT_DEFAULTS["architect.system"]
    with pytest.raises(ValidationError, match="Instance is frozen"):
        default.agent = "modified"  # type: ignore[misc]  # Intentional: testing frozen model rejects assignment


@pytest.mark.parametrize("prompt_id,expected_agent", [
    ("architect.system", "architect"),
    ("architect.plan", "architect"),
    ("reviewer.structured", "reviewer"),
    ("reviewer.agentic", "reviewer"),
])
def test_prompt_default_exists(prompt_id: str, expected_agent: str) -> None:
    """Test that required prompt defaults exist with correct agent."""
    assert prompt_id in PROMPT_DEFAULTS
    default = PROMPT_DEFAULTS[prompt_id]
    assert default.agent == expected_agent
    assert default.description
    assert default.content


def test_all_defaults_have_required_fields() -> None:
    """All prompt defaults should have non-empty required fields."""
    for prompt_id, default in PROMPT_DEFAULTS.items():
        assert default.agent, f"{prompt_id} missing agent"
        assert default.name, f"{prompt_id} missing name"
        assert default.content, f"{prompt_id} missing content"
        assert default.description, f"{prompt_id} missing description"
