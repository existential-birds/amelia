"""Tests for discover_builtin_tools() AST-based discovery.

These pass fully once Step 3 migrates the tool modules to self-register; the
discovery mechanism itself is validated here against the registry singleton.
"""

from __future__ import annotations

import pytest

from amelia.tools.registry import registry
from amelia.tools.registry.registry import discover_builtin_tools


@pytest.fixture(autouse=True)
def _discover_once():
    """Ensure discovery has run before each test in this module."""
    discover_builtin_tools()
    yield


def test_discover_returns_list_of_names():
    names = discover_builtin_tools()
    assert isinstance(names, list)
    # Idempotent: running again does not raise and still returns names.
    again = discover_builtin_tools()
    assert set(again) == set(names)


def test_discover_imports_self_registering_modules():
    # shell_executor self-registers after Step 3.
    names = discover_builtin_tools()
    assert "run_shell_command" in names


def test_discovered_names_are_in_registry():
    names = discover_builtin_tools()
    for name in names:
        assert registry.get(name) is not None


def test_discover_is_idempotent_no_duplicate_error():
    # Repeated discovery must not raise on re-registration of cached modules.
    for _ in range(3):
        discover_builtin_tools()
    assert "run_shell_command" in registry.all_names()
