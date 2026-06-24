"""Per-agent tool profiles and the ``resolve_agent_tools`` resolver.

Each profile maps an agent name to:

* ``toolsets`` — the registry toolsets the agent draws from (union of members).
* ``extra_tools`` — specific tool names not captured by a toolset (e.g. an
  agent-only factory tool).
* ``max_risk`` — a risk ceiling; any candidate whose ``risk_level`` exceeds it
  is dropped.

``resolve_agent_tools`` expands a profile against the registry and returns the
concrete ``ToolSpec`` list, applying the ceiling and omitting factory tools
whose runtime context deps are unavailable (graceful degradation).
"""

from __future__ import annotations

from dataclasses import dataclass

from amelia.tools.registry import ToolContext, ToolSpec, registry
from amelia.tools.registry.spec import RiskLevel


@dataclass(frozen=True)
class AgentToolProfile:
    """Declarative tool access for a single agent.

    Attributes:
        toolsets: Registry toolsets to union for this agent.
        extra_tools: Specific canonical tool names to add beyond the toolsets.
        max_risk: Maximum permitted risk level for this agent.
    """

    toolsets: frozenset[str]
    extra_tools: frozenset[str] = frozenset()
    max_risk: RiskLevel = RiskLevel.EXECUTE


# Profile table — see .beagle/concepts/tool-wiring/spec.md §2.2.
AGENT_TOOL_PROFILES: dict[str, AgentToolProfile] = {
    "developer": AgentToolProfile(
        toolsets=frozenset({"filesystem", "execute", "vcs", "knowledge", "quality", "agent_state", "coordination"}),
        max_risk=RiskLevel.EXECUTE,
    ),
    "architect": AgentToolProfile(
        toolsets=frozenset({"readonly", "knowledge", "agent_state"}),
        extra_tools=frozenset({"write_plan"}),
        max_risk=RiskLevel.WRITE,
    ),
    "oracle": AgentToolProfile(
        toolsets=frozenset({"readonly", "knowledge", "agent_state"}),
        max_risk=RiskLevel.READ_ONLY,
    ),
    "reviewer": AgentToolProfile(
        toolsets=frozenset({"readonly", "knowledge", "agent_state"}),
        max_risk=RiskLevel.READ_ONLY,
    ),
    "evaluator": AgentToolProfile(
        toolsets=frozenset({"readonly", "agent_state"}),
        max_risk=RiskLevel.READ_ONLY,
    ),
}


def _factory_available(spec: ToolSpec, ctx: ToolContext | None) -> bool:
    """Return True if a factory tool can be built with the given context.

    Calls the factory (cheap: it only builds a closure) and treats ``None`` as
    "deps unavailable". A missing context also means the tool is unavailable.
    """
    if spec.factory is None:
        return True
    if ctx is None:
        return False
    try:
        return spec.factory(ctx) is not None
    except Exception:  # noqa: BLE001 - a failing availability probe => omit
        return False


def resolve_agent_tools(
    agent_name: str,
    ctx: ToolContext | None = None,
) -> list[ToolSpec]:
    """Resolve the full tool list for an agent from its profile + registry.

    Args:
        agent_name: Name of the agent (must be a key in ``AGENT_TOOL_PROFILES``).
        ctx: Optional runtime context; factory tools needing it are omitted
            when absent or when the factory reports deps unavailable.

    Returns:
        Sorted-by-name list of ``ToolSpec`` objects the agent may use. Empty
        for an unknown agent name.
    """
    profile = AGENT_TOOL_PROFILES.get(agent_name)
    if profile is None:
        return []

    candidate_names: set[str] = set()
    for toolset in profile.toolsets:
        candidate_names |= registry.names_for_toolset(toolset)
    candidate_names |= set(profile.extra_tools)

    resolved: list[ToolSpec] = []
    for name in sorted(candidate_names):
        spec = registry.get(name)
        if spec is None:
            continue
        if spec.risk_level > profile.max_risk:
            continue
        if not _factory_available(spec, ctx):
            continue
        resolved.append(spec)

    return resolved
