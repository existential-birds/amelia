"""Tool implementations for agent actions.

Importing this package triggers ``discover_builtin_tools()``, which AST-scans
the modules below and imports each one that self-registers a tool against the
registry. The call is idempotent: Python caches imported modules and the
registry is a plain dict, so re-importing this package is a no-op.
"""

from __future__ import annotations

from amelia.tools.registry import discover_builtin_tools


# Populate the registry on first import. Guarded so a single broken tool module
# (caught and logged inside discover_builtin_tools) never blocks the package.
discover_builtin_tools()
