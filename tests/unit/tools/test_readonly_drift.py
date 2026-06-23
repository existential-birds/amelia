"""Drift guard: READONLY_TOOLS preset must equal the registry's 'readonly' toolset.

Makes the previously only-partially-consumed ``READONLY_TOOLS`` constant
load-bearing against the registry. ``READONLY_TOOLS`` is consumed by the Codex
driver (``drivers/cli/codex.py``) to pick its sandbox approval mode, so the
registry's ``readonly`` toolset is kept in sync with it.
"""

from __future__ import annotations

from amelia.core.constants import READONLY_TOOLS
from amelia.tools.registry.registry import discover_builtin_tools, registry


def test_readonly_tools_matches_registry():
    """set(READONLY_TOOLS) must equal registry.names_for_toolset('readonly').

    If this fails, either ``READONLY_TOOLS`` in constants.py or the ``readonly``
    toolset tag on the registering stubs has drifted — fix the side that's wrong.
    """
    discover_builtin_tools()
    preset = {t.value for t in READONLY_TOOLS}
    registered = registry.names_for_toolset("readonly")
    assert preset == registered, (
        f"READONLY_TOOLS drift: preset={sorted(preset)} "
        f"!= registry readonly toolset={sorted(registered)}"
    )
