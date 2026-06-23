"""The tool registry — a module-level singleton tools self-register against.

Public surface:
    registry             — the singleton ``ToolRegistry`` instance.
    register()           — convenience wrapper around ``registry.register``.
    get()                — convenience wrapper around ``registry.get``.
    discover_builtin_tools() — AST-scan ``amelia/tools/*.py`` and import every
                          module that self-registers a tool at module level.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

from loguru import logger

from amelia.tools.registry.spec import ToolSpec


# Directory containing tool modules that may self-register. Resolved relative to
# this file so discovery works regardless of the current working directory.
_TOOLS_DIR = Path(__file__).resolve().parent.parent
_TOOLS_PACKAGE = "amelia.tools"


def _module_registers_tools(module_path: Path) -> bool:
    """Return True if ``module_path`` has a top-level ``register(...)`` call.

    We deliberately only look at *top-level* statements so that helper modules
    which mention ``register`` inside functions/classes are not imported for
    their side effects.
    """
    try:
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return False

    for node in tree.body:
        if not isinstance(node, ast.Expr):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if isinstance(func, ast.Name) and func.id == "register":
            return True
    return False


class ToolRegistry:
    """In-memory map of canonical tool name → ``ToolSpec``.

    Tests should instantiate their own ``ToolRegistry`` to avoid polluting the
    module-level singleton; production code uses ``registry`` (below).
    """

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec, *, override: bool = False) -> None:
        """Register a ``ToolSpec``.

        Args:
            spec: The spec to register.
            override: When True, silently replace an existing spec with the
                same name. When False (default), duplicate names raise
                ``ValueError`` so accidental shadowing is loud.

        Raises:
            ValueError: If the name is already registered and ``override`` is
                False.
        """
        if spec.name in self._specs and not override:
            raise ValueError(
                f"Tool {spec.name!r} is already registered. "
                "Pass override=True to replace it."
            )
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        """Return the spec for ``name``, or ``None`` if unregistered."""
        return self._specs.get(name)

    def resolve(self, names: list[str]) -> list[ToolSpec]:
        """Return specs for ``names`` in order.

        Raises:
            KeyError: If any name is not registered (with the missing name).
        """
        resolved: list[ToolSpec] = []
        for name in names:
            spec = self._specs.get(name)
            if spec is None:
                raise KeyError(name)
            resolved.append(spec)
        return resolved

    def names_for_toolset(self, toolset: str) -> frozenset[str]:
        """Return the names of all registered tools belonging to ``toolset``."""
        return frozenset(
            spec.name for spec in self._specs.values() if toolset in spec.toolsets
        )

    def all_names(self) -> frozenset[str]:
        """Return every registered tool name."""
        return frozenset(self._specs)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._specs

    def __len__(self) -> int:
        return len(self._specs)


# The module-level singleton. Tool modules call ``register(ToolSpec(...))`` at
# import time; ``discover_builtin_tools`` imports those modules.
registry: ToolRegistry = ToolRegistry()


def register(spec: ToolSpec, *, override: bool = False) -> None:
    """Register ``spec`` against the module-level singleton.

    Thin convenience wrapper so tool modules can write ``register(ToolSpec(...))``
    without holding a reference to the singleton.
    """
    registry.register(spec, override=override)


def get(name: str) -> ToolSpec | None:
    """Look up ``name`` in the module-level singleton."""
    return registry.get(name)


def discover_builtin_tools() -> list[str]:
    """Import every ``amelia/tools/*.py`` module that self-registers a tool.

    Uses an AST scan (no execution) to decide which modules to import, then
    imports them so their top-level ``register(ToolSpec(...))`` calls populate
    the module-level ``registry``.

    The registry is a plain dict and Python caches imported modules, so this
    function is idempotent: calling it more than once neither raises on
    duplicate registration nor re-runs module-level code.

    Returns:
        Sorted list of all tool names registered after discovery.
    """
    for path in sorted(_TOOLS_DIR.glob("*.py")):
        # Skip package init — it triggers discovery itself and never registers.
        if path.name == "__init__.py":
            continue
        if not _module_registers_tools(path):
            continue
        module_name = f"{_TOOLS_PACKAGE}.{path.stem}"
        try:
            importlib.import_module(module_name)
        except Exception:
            # A failing tool module must not break discovery for the rest.
            logger.exception("Failed to import self-registering tool module", module=module_name)
    return sorted(registry.all_names())
