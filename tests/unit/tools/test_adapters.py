"""Tests for the LangChain adapter (to_langchain)."""

from __future__ import annotations

import pytest
from langchain_core.tools import BaseTool, StructuredTool

from amelia.tools.registry import ToolSpec
from amelia.tools.registry.adapters import to_langchain
from amelia.tools.registry.registry import discover_builtin_tools, registry
from amelia.tools.registry.spec import RiskLevel


def test_to_langchain_produces_callable_tool():
    discover_builtin_tools()
    spec = registry.get("bundle_files")
    assert spec is not None
    tool = to_langchain(spec)
    assert isinstance(tool, BaseTool)
    assert isinstance(tool, StructuredTool)
    assert tool.name == "bundle_files"
    assert tool.description == spec.description


async def test_to_langchain_tool_invokes_handler(tmp_path):
    discover_builtin_tools()
    spec = registry.get("bundle_files")
    assert spec is not None
    tool = to_langchain(spec)

    # Create a file the bundler can pick up.
    (tmp_path / "hello.md").write_text("# hi", encoding="utf-8")

    result = await tool.ainvoke({"working_dir": str(tmp_path), "patterns": ["*.md"]})
    # bundle_files returns a FileBundle pydantic model with a `files` attribute.
    assert hasattr(result, "files")
    assert len(result.files) == 1
    assert result.files[0].path == "hello.md"


def test_to_langchain_rejects_stub():
    discover_builtin_tools()
    stub = registry.get("read_file")
    assert stub is not None
    assert stub.is_stub
    with pytest.raises(ValueError, match="handler"):
        to_langchain(stub)


def test_to_langchain_rejects_factory_only_spec():
    discover_builtin_tools()
    spec = registry.get("knowledge_search")
    assert spec is not None
    assert spec.handler is None
    with pytest.raises(ValueError, match="handler"):
        to_langchain(spec)


async def test_to_langchain_round_trip_on_inline_handler(tmp_path):
    """A spec built from an inline async handler must be invokable end-to-end."""
    from pydantic import BaseModel

    class EchoInput(BaseModel):
        msg: str

    async def echo(*, msg: str) -> str:
        return f"echo:{msg}"

    spec = ToolSpec(
        name="glob",  # reuse a valid ToolName; register on a throwaway registry path
        description="echo",
        input_schema=EchoInput,
        handler=echo,
        risk_level=RiskLevel.READ_ONLY,
        required_permissions=frozenset(),
        toolsets=frozenset(),
    )
    tool = to_langchain(spec)
    out = await tool.ainvoke({"msg": "hi"})
    assert out == "echo:hi"
