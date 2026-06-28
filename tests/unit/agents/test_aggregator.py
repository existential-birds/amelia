"""Tests for the Aggregator agent's prompt default and tool profile.

The Aggregator synthesizes one canonical plan from N candidate plans and
writes it via the ``write_plan`` tool, mirroring the Architect's profile.
"""

from __future__ import annotations

from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
from amelia.agents.tool_profiles import resolve_agent_tools
from amelia.tools.registry import ToolContext
from amelia.tools.registry.registry import discover_builtin_tools


def test_aggregator_prompt_default_exists_and_is_non_empty() -> None:
    default = PROMPT_DEFAULTS["aggregator.system"]
    assert default.content.strip()


def test_resolve_agent_tools_aggregator_includes_write_plan() -> None:
    discover_builtin_tools()
    ctx = ToolContext(cwd="/tmp")
    tools = resolve_agent_tools("aggregator", ctx)
    names = {t.name for t in tools}
    assert tools
    assert "write_plan" in names
