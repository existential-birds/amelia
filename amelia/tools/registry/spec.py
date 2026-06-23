"""Tool metadata schema and enums.

Defines ``ToolSpec`` — the single schema every amelia tool registers against —
plus the ``RiskLevel`` and ``Permission`` enums used by the policy layer to
reason about tools uniformly across drivers.

See ``.beagle/concepts/tool-registry/spec.md`` §1 for the design.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import IntEnum, StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from amelia.core.constants import ToolName


class RiskLevel(IntEnum):
    """Risk classification for a tool, ordered from least to most dangerous.

    The policy layer vetoes any tool whose risk exceeds the configured ceiling.
    """

    READ_ONLY = 0
    WRITE = 1
    EXECUTE = 2
    DESTRUCTIVE = 3


class Permission(StrEnum):
    """Capabilities a tool requires. Union of these is surfaced for auditing."""

    FS_READ = "fs.read"
    FS_WRITE = "fs.write"
    SHELL_EXEC = "shell.exec"
    NET_READ = "net.read"
    NET_WRITE = "net.write"


# Type aliases for the callable ToolSpec fields. These are arbitrary types from
# Pydantic's perspective (validated via ``arbitrary_types_allowed``).
AvailabilityCheck = Callable[[], Awaitable[bool]]
ToolHandler = Callable[..., Awaitable[Any]]
ToolFactory = Callable[..., ToolHandler]


class ToolSpec(BaseModel):
    """Metadata + handler for a single tool.

    A ``ToolSpec`` is immutable. Tools that own a real implementation set
    ``handler``; tools that need runtime dependencies (DB clients, root dirs)
    set ``factory`` instead and leave ``handler`` empty. Library-provided tools
    that amelia does not implement (deepagents FilesystemMiddleware, sandbox
    ``execute``) are registered as *stubs* with both ``handler`` and ``factory``
    unset so the policy layer can still reason about them.

    Attributes:
        name: Canonical tool name. Must be a member of ``ToolName``.
        description: Human-readable summary surfaced to the model.
        input_schema: Pydantic model describing the tool's arguments.
        handler: Async callable executing the tool, or ``None`` for
            stubs/factory-tools.
        risk_level: Risk classification used by the policy ceiling.
        required_permissions: Capabilities the tool exercises (for audit).
        toolsets: Logical groups the tool belongs to (e.g. ``"readonly"``).
        check_fn: Optional async availability probe (e.g. "is a sandbox up?").
        factory: Optional callable that builds a ``handler`` from runtime deps.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    description: str
    input_schema: type[BaseModel]
    handler: ToolHandler | None = None
    risk_level: RiskLevel = RiskLevel.READ_ONLY
    required_permissions: frozenset[Permission] = frozenset()
    toolsets: frozenset[str] = frozenset()
    check_fn: AvailabilityCheck | None = None
    factory: ToolFactory | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        """Reject names that are not members of the canonical ``ToolName`` enum.

        Keeping the registry and constants in lockstep means the policy layer
        can never see a tool name it cannot reason about.
        """
        try:
            ToolName(v)
        except ValueError as err:  # pragma: no cover - defensive branch
            raise ValueError(
                f"Unknown tool name {v!r}: not a member of ToolName."
            ) from err
        return v

    @property
    def is_stub(self) -> bool:
        """True when this spec carries metadata only (no handler, no factory)."""
        return self.handler is None and self.factory is None
