"""Reusable toolset and policy presets built from the registry."""

from __future__ import annotations

from amelia.core.constants import READONLY_TOOLS
from amelia.tools.registry.policy import ToolPolicy
from amelia.tools.registry.registry import discover_builtin_tools, registry
from amelia.tools.registry.spec import RiskLevel


def readonly_tool_names() -> frozenset[str]:
    """Return the explicit read-only tool allow-set.

    ``READONLY_TOOLS`` is the source of truth for observer-style agents. This
    helper validates that every listed tool is registered and classified no
    higher than ``READ_ONLY`` so the constant cannot drift into dead or unsafe
    configuration.
    """
    discover_builtin_tools()
    names = frozenset(tool.value for tool in READONLY_TOOLS)
    missing = sorted(name for name in names if registry.get(name) is None)
    if missing:
        raise ValueError(
            "READONLY_TOOLS contains unregistered tool(s): " + ", ".join(missing)
        )

    too_risky = sorted(
        name
        for name in names
        if (spec := registry.get(name)) is not None and spec.risk_level > RiskLevel.READ_ONLY
    )
    if too_risky:
        raise ValueError(
            "READONLY_TOOLS contains non-read-only tool(s): " + ", ".join(too_risky)
        )
    return names


def readonly_tool_policy(
    *,
    extra_allowed: frozenset[str] = frozenset(),
    max_risk: RiskLevel = RiskLevel.READ_ONLY,
) -> ToolPolicy:
    """Build a ToolPolicy for read-only agents.

    Args:
        extra_allowed: Optional per-agent exceptions, such as ``write_plan`` for
            Architect.  When an extra tool's risk level exceeds ``max_risk``,
            the ceiling is automatically raised to cover it so the exception is
            actually usable through ``ToolPolicyMiddleware``.
        max_risk: Risk ceiling for the policy. Defaults to strict read-only.
    """
    effective_risk = max_risk
    for name in extra_allowed:
        spec = registry.get(name)
        if spec is not None and spec.risk_level > effective_risk:
            effective_risk = spec.risk_level

    return ToolPolicy(
        allowed=readonly_tool_names() | extra_allowed,
        max_risk=effective_risk,
    )
