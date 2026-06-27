"""Tool registry package — canonical tool metadata + policy enforcement.

Re-exports the public surface so callers can write::

    from amelia.tools.registry import ToolSpec, register, registry, RiskLevel
"""

from __future__ import annotations

from amelia.tools.registry.context import ToolContext
from amelia.tools.registry.policy import (
    HighRiskDecision,
    ToolPolicy,
    ToolPolicyAuditDecision,
    ToolPolicyMiddleware,
    ToolValidationContext,
    ToolValidationResult,
)
from amelia.tools.registry.registry import (
    ToolRegistry,
    discover_builtin_tools,
    get,
    register,
    registry,
)
from amelia.tools.registry.spec import (
    Permission,
    RiskLevel,
    ToolSpec,
)
from amelia.tools.registry.toolsets import readonly_tool_names, readonly_tool_policy


__all__ = [
    "Permission",
    "RiskLevel",
    "HighRiskDecision",
    "ToolContext",
    "ToolPolicy",
    "ToolPolicyAuditDecision",
    "ToolPolicyMiddleware",
    "ToolRegistry",
    "ToolSpec",
    "ToolValidationContext",
    "ToolValidationResult",
    "discover_builtin_tools",
    "get",
    "register",
    "registry",
    "readonly_tool_names",
    "readonly_tool_policy",
]
