"""The tool registry — a module-level singleton tools self-register against.

Public surface:
    registry   — the singleton ``ToolRegistry`` instance.
    register() — convenience wrapper around ``registry.register``.
    get()      — convenience wrapper around ``registry.get``.
"""

from __future__ import annotations

from amelia.tools.registry.spec import ToolSpec


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
