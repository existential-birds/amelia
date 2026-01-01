# tests/unit/agents/prompts/test_defaults.py
"""Tests for hardcoded prompt defaults."""
import pytest

from amelia.agents.prompts.defaults import PROMPT_DEFAULTS, PromptDefault


def test_prompt_default_is_frozen():
    """PromptDefault should be immutable."""
    default = PROMPT_DEFAULTS["architect.system"]
    with pytest.raises(AttributeError):
        default.agent = "modified"


def test_prompt_defaults_contains_architect_system():
    """Should have architect.system prompt defined."""
    assert "architect.system" in PROMPT_DEFAULTS
    default = PROMPT_DEFAULTS["architect.system"]
    assert default.agent == "architect"
    assert default.name == "Architect System Prompt"
    assert len(default.content) > 50  # Has substantial content


def test_prompt_defaults_contains_architect_plan():
    """Should have architect.plan prompt defined."""
    assert "architect.plan" in PROMPT_DEFAULTS
    default = PROMPT_DEFAULTS["architect.plan"]
    assert default.agent == "architect"
    assert default.name == "Architect Plan Format"


def test_prompt_defaults_contains_reviewer_structured():
    """Should have reviewer.structured prompt defined."""
    assert "reviewer.structured" in PROMPT_DEFAULTS
    default = PROMPT_DEFAULTS["reviewer.structured"]
    assert default.agent == "reviewer"


def test_prompt_defaults_contains_reviewer_agentic():
    """Should have reviewer.agentic prompt defined."""
    assert "reviewer.agentic" in PROMPT_DEFAULTS
    default = PROMPT_DEFAULTS["reviewer.agentic"]
    assert default.agent == "reviewer"


def test_all_defaults_have_required_fields():
    """All prompt defaults should have non-empty required fields."""
    for prompt_id, default in PROMPT_DEFAULTS.items():
        assert default.agent, f"{prompt_id} missing agent"
        assert default.name, f"{prompt_id} missing name"
        assert default.content, f"{prompt_id} missing content"
        assert default.description, f"{prompt_id} missing description"
