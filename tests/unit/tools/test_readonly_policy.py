"""Tests for reusable read-only tool policy presets."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import ToolMessage

from amelia.core.constants import READONLY_TOOLS, ToolName
from amelia.tools.registry import RiskLevel, ToolPolicyMiddleware
from amelia.tools.registry.registry import discover_builtin_tools
from amelia.tools.registry.toolsets import readonly_tool_names, readonly_tool_policy


def test_readonly_tool_names_are_the_load_bearing_constant() -> None:
    """The reusable read-only preset must consume READONLY_TOOLS exactly."""
    discover_builtin_tools()

    assert readonly_tool_names() == frozenset(tool.value for tool in READONLY_TOOLS)
    assert ToolName.WRITE_FILE.value not in readonly_tool_names()
    assert ToolName.EDIT_FILE.value not in readonly_tool_names()
    assert ToolName.EXECUTE_TOOL.value not in readonly_tool_names()


def test_readonly_tool_policy_has_explicit_allow_set_and_readonly_ceiling() -> None:
    """Read-only policy denies by explicit allow-list and READ_ONLY max risk."""
    discover_builtin_tools()

    policy = readonly_tool_policy()

    assert policy.allowed == readonly_tool_names()
    assert policy.max_risk == RiskLevel.READ_ONLY


async def test_readonly_policy_vetoes_write_before_side_effect(tmp_path: Path) -> None:
    """A denied write_file call returns a ToolMessage error and never invokes handler."""
    discover_builtin_tools()
    target = tmp_path / "should-not-exist.txt"
    middleware = ToolPolicyMiddleware(readonly_tool_policy())
    request = SimpleNamespace(
        tool_call={
            "name": "write_file",
            "id": "call-write",
            "args": {"file_path": str(target), "content": "bad"},
        }
    )

    async def handler(_: Any) -> ToolMessage:
        target.write_text("bad", encoding="utf-8")
        return ToolMessage(content="wrote", tool_call_id="call-write")

    result = await middleware.awrap_tool_call(request, handler)  # type: ignore[arg-type]

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.name == "write_file"
    assert "Denied" in str(result.content)
    assert not target.exists()


async def test_readonly_policy_vetoes_execute_before_side_effect(tmp_path: Path) -> None:
    """A denied execute call returns a ToolMessage error and never invokes handler."""
    discover_builtin_tools()
    target = tmp_path / "executed.txt"
    middleware = ToolPolicyMiddleware(readonly_tool_policy())
    request = SimpleNamespace(
        tool_call={
            "name": "execute",
            "id": "call-execute",
            "args": {"command": f"touch {target}"},
        }
    )

    async def handler(_: Any) -> ToolMessage:
        target.write_text("executed", encoding="utf-8")
        return ToolMessage(content="executed", tool_call_id="call-execute")

    result = await middleware.awrap_tool_call(request, handler)  # type: ignore[arg-type]

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.name == "execute"
    assert "Denied" in str(result.content)
    assert not target.exists()
