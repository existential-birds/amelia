"""Tests for per-agent tool profiles and resolve_agent_tools.

Profiles map each agent to a toolset membership + risk ceiling.
``resolve_agent_tools`` expands a profile against the registry and returns the
concrete ToolSpec list, applying the risk ceiling and omitting factory tools
whose runtime context deps are unavailable.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from amelia.agents.tool_profiles import (
    AGENT_TOOL_PROFILES,
    AgentToolProfile,
    resolve_agent_tools,
)
from amelia.tools.registry import RiskLevel, ToolContext
from amelia.tools.registry.registry import discover_builtin_tools


def test_developer_profile_includes_quality_and_vcs() -> None:
    profile = AGENT_TOOL_PROFILES["developer"]
    assert "quality" in profile.toolsets
    assert "vcs" in profile.toolsets
    assert "knowledge" in profile.toolsets
    assert profile.max_risk == RiskLevel.EXECUTE


def test_reviewer_profile_is_readonly() -> None:
    profile = AGENT_TOOL_PROFILES["reviewer"]
    assert "readonly" in profile.toolsets
    assert profile.max_risk == RiskLevel.READ_ONLY


def test_oracle_profile_is_readonly() -> None:
    profile = AGENT_TOOL_PROFILES["oracle"]
    assert profile.max_risk == RiskLevel.READ_ONLY


def test_resolve_agent_tools_developer_includes_git_diff_and_run_tests() -> None:
    """Developer's resolved tools include git_diff (vcs) and run_tests (quality)."""
    discover_builtin_tools()
    ctx = ToolContext(cwd="/tmp")
    tools = resolve_agent_tools("developer", ctx)
    names = {t.name for t in tools}
    assert "git_diff" in names
    assert "git_log" in names
    assert "run_tests" in names
    assert "run_linter" in names


def test_resolve_agent_tools_developer_excludes_knowledge_without_repo() -> None:
    """knowledge_search is omitted when the context has no knowledge repo."""
    discover_builtin_tools()
    ctx = ToolContext(cwd="/tmp")
    tools = resolve_agent_tools("developer", ctx)
    names = {t.name for t in tools}
    assert "knowledge_search" not in names


def test_resolve_agent_tools_developer_includes_knowledge_with_repo() -> None:
    """knowledge_search appears when embedding + repo deps are present."""
    discover_builtin_tools()
    mock_embed = AsyncMock()
    mock_repo = AsyncMock()
    ctx = ToolContext(
        cwd="/tmp",
        embedding_client=mock_embed,
        knowledge_repo=mock_repo,
    )
    tools = resolve_agent_tools("developer", ctx)
    names = {t.name for t in tools}
    assert "knowledge_search" in names


def test_resolve_agent_tools_reviewer_excludes_write() -> None:
    """Reviewer (readonly) cannot receive write_file / edit_file."""
    discover_builtin_tools()
    ctx = ToolContext(cwd="/tmp")
    tools = resolve_agent_tools("reviewer", ctx)
    names = {t.name for t in tools}
    assert "write_file" not in names
    assert "edit_file" not in names
    assert "execute" not in names
    assert "run_tests" not in names  # EXECUTE-risk, below reviewer's ceiling
    assert "read_file" in names


def test_resolve_agent_tools_unknown_agent_returns_empty() -> None:
    discover_builtin_tools()
    assert resolve_agent_tools("nonexistent", ToolContext()) == []


def test_agent_tool_profile_is_frozen() -> None:
    profile = AgentToolProfile(toolsets=frozenset({"readonly"}))
    # Frozen dataclass: attribute assignment must fail.
    try:
        profile.max_risk = RiskLevel.EXECUTE  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("AgentToolProfile should be frozen")
