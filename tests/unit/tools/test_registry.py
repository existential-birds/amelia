"""Tests for the Tool registry: ToolSpec schema, enums, and ToolRegistry."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from amelia.tools.registry.registry import ToolRegistry
from amelia.tools.registry.spec import Permission, RiskLevel, ToolSpec


class _DummyInput(BaseModel):
    """Minimal input schema for test specs."""

    value: str = ""


async def _dummy_handler(**kwargs: Any) -> str:
    return "ok"


def _make_spec(
    *,
    name: str = "read_file",
    description: str = "d",
    risk: RiskLevel = RiskLevel.READ_ONLY,
    toolsets: frozenset[str] = frozenset({"readonly"}),
) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        input_schema=_DummyInput,
        handler=_dummy_handler,
        risk_level=risk,
        required_permissions=frozenset(),
        toolsets=toolsets,
    )


class TestRiskLevel:
    def test_ordering(self):
        assert RiskLevel.READ_ONLY < RiskLevel.WRITE < RiskLevel.EXECUTE < RiskLevel.DESTRUCTIVE

    def test_values(self):
        assert int(RiskLevel.READ_ONLY) == 0
        assert int(RiskLevel.DESTRUCTIVE) == 3


class TestToolSpec:
    def test_construct_minimal(self):
        spec = _make_spec()
        assert spec.name == "read_file"
        assert spec.risk_level == RiskLevel.READ_ONLY
        assert spec.handler is _dummy_handler
        assert spec.toolsets == frozenset({"readonly"})

    def test_frozen(self):
        spec = _make_spec()
        with pytest.raises((ValidationError, TypeError)):
            spec.name = "write_file"  # type: ignore[misc]

    def test_invalid_name_rejected(self):
        with pytest.raises(ValidationError):
            ToolSpec(
                name="not_a_real_tool",
                description="d",
                input_schema=_DummyInput,
                handler=_dummy_handler,
                risk_level=RiskLevel.READ_ONLY,
                required_permissions=frozenset(),
                toolsets=frozenset(),
            )

    def test_required_permissions_are_frozenset(self):
        spec = ToolSpec(
            name="run_shell_command",
            description="d",
            input_schema=_DummyInput,
            handler=_dummy_handler,
            risk_level=RiskLevel.EXECUTE,
            required_permissions={Permission.SHELL_EXEC},
            toolsets=frozenset({"execute"}),
        )
        assert spec.required_permissions == frozenset({Permission.SHELL_EXEC})


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        spec = _make_spec()
        reg.register(spec)
        assert reg.get("read_file") is spec

    def test_get_missing_returns_none(self):
        reg = ToolRegistry()
        assert reg.get("nope") is None

    def test_duplicate_register_raises(self):
        reg = ToolRegistry()
        reg.register(_make_spec())
        with pytest.raises(ValueError):
            reg.register(_make_spec())

    def test_duplicate_register_override_allowed(self):
        reg = ToolRegistry()
        reg.register(_make_spec())
        replacement = _make_spec(description="d2")
        reg.register(replacement, override=True)
        assert reg.get("read_file") is replacement

    def test_names_for_toolset(self):
        reg = ToolRegistry()
        reg.register(_make_spec(name="read_file", toolsets=frozenset({"readonly", "filesystem"})))
        reg.register(_make_spec(name="glob", toolsets=frozenset({"readonly"})))
        reg.register(_make_spec(name="write_file", risk=RiskLevel.WRITE, toolsets=frozenset({"filesystem"})))
        readonly = reg.names_for_toolset("readonly")
        assert "read_file" in readonly
        assert "glob" in readonly
        assert "write_file" not in readonly

    def test_resolve_returns_specs(self):
        reg = ToolRegistry()
        reg.register(_make_spec(name="read_file"))
        reg.register(_make_spec(name="glob"))
        resolved = reg.resolve(["read_file", "glob"])
        assert {s.name for s in resolved} == {"read_file", "glob"}

    def test_resolve_unknown_raises(self):
        reg = ToolRegistry()
        with pytest.raises(KeyError):
            reg.resolve(["ghost"])

    def test_module_singleton_and_free_function(self):
        from amelia.tools.registry import register, registry

        # The module-level singleton must be a ToolRegistry instance.
        assert isinstance(registry, ToolRegistry)
        assert callable(register)
