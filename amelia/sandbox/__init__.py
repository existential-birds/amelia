"""Sandbox execution infrastructure for isolated agent environments.

Lazy imports are used because the worker entrypoint (amelia.sandbox.worker)
runs inside a container that does not have fastapi installed.  Eagerly
importing proxy.py (which requires fastapi) would break the worker.
"""

from __future__ import annotations  # noqa: I001

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from amelia.sandbox.docker import DockerSandboxProvider
    from amelia.sandbox.provider import SandboxProvider
    from amelia.sandbox.proxy import ProviderConfig
    from amelia.sandbox.worktree import WorktreeManager

__all__ = [
    "DockerSandboxProvider",
    "ProviderConfig",
    "SandboxProvider",
    "WorktreeManager",
]


def __getattr__(name: str) -> object:
    if name == "DockerSandboxProvider":
        from amelia.sandbox.docker import DockerSandboxProvider  # noqa: PLC0415

        return DockerSandboxProvider
    if name == "ProviderConfig":
        from amelia.sandbox.proxy import ProviderConfig  # noqa: PLC0415

        return ProviderConfig
    if name == "SandboxProvider":
        from amelia.sandbox.provider import SandboxProvider  # noqa: PLC0415

        return SandboxProvider
    if name == "WorktreeManager":
        from amelia.sandbox.worktree import WorktreeManager  # noqa: PLC0415

        return WorktreeManager
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
