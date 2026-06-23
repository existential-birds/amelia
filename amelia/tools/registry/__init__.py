"""Tool registry package — canonical tool metadata + policy enforcement.

Re-exports the public surface so callers can write::

    from amelia.tools.registry import ToolSpec, register, registry, RiskLevel
"""

from __future__ import annotations

from amelia.tools.registry.registry import ToolRegistry, get, register, registry
from amelia.tools.registry.spec import (
    Permission,
    RiskLevel,
    ToolSpec,
)


__all__ = [
    "Permission",
    "RiskLevel",
    "ToolRegistry",
    "ToolSpec",
    "get",
    "register",
    "registry",
]
