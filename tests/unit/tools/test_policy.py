"""Tests for ToolPolicy + ToolPolicyMiddleware.

The veto test asserts the OBSERVABLE CONSEQUENCE — that a denied write tool
never touches disk — not merely that the middleware was called. It wires the
middleware into a real langgraph ToolNode via ``awrap_tool_call`` and drives it
through a compiled StateGraph (the same entrypoint real agents use, which is
what supplies the Runtime langgraph requires).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import pytest
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt.tool_node import ToolNode
from pydantic import BaseModel
from typing_extensions import TypedDict

from amelia.tools.registry.policy import ToolPolicy, ToolPolicyMiddleware
from amelia.tools.registry.spec import RiskLevel


class _WriteFileInput(BaseModel):
    file_path: str
    content: str


def _make_write_tool() -> StructuredTool:
    """Build a real StructuredTool that writes to disk (the guarded side effect)."""

    async def _write(*, file_path: str, content: str) -> str:
        Path(file_path).write_text(content, encoding="utf-8")
        return f"wrote {file_path}"

    return StructuredTool.from_function(
        coroutine=_write,
        name="write_file",
        description="write a file to disk",
        args_schema=_WriteFileInput,
    )


class _State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def _build_app(policy: ToolPolicy) -> Any:
    """Compile a single-node graph: START -> ToolNode(+middleware) -> END."""
    mw = ToolPolicyMiddleware(policy=policy)
    node = ToolNode(tools=[_make_write_tool()], awrap_tool_call=mw.awrap_tool_call)
    graph = StateGraph(_State)
    graph.add_node("tools", node)
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    return graph.compile()


def _call(name: str, file_path: str, call_id: str) -> dict[str, object]:
    return {
        "name": name,
        "args": {"file_path": file_path, "content": "secret"},
        "id": call_id,
        "type": "tool_call",
    }


class TestToolPolicy:
    def test_defaults(self):
        policy = ToolPolicy(allowed=frozenset({"read_file"}))
        assert policy.allowed == frozenset({"read_file"})
        assert policy.max_risk == RiskLevel.EXECUTE  # permissive default

    def test_frozen(self):
        policy = ToolPolicy(allowed=frozenset({"read_file"}))
        from pydantic import ValidationError

        with pytest.raises((AttributeError, TypeError, ValidationError)):
            policy.allowed = frozenset({"write_file"})  # type: ignore[misc]


async def test_policy_vetoes_write_file_and_prevents_disk_write(tmp_path):
    """A denied write_file call must return an error ToolMessage AND write nothing.

    This is the spec's observable acceptance test: it asserts the side effect
    (file on disk) never happens, not just that the middleware short-circuited.
    """
    target = tmp_path / "out.txt"
    assert not target.exists()

    app = _build_app(ToolPolicy(allowed=frozenset({"read_file"}), max_risk=RiskLevel.READ_ONLY))
    result = await app.ainvoke({"messages": [AIMessage(content="", tool_calls=[_call("write_file", str(target), "c1")])]})

    msg = result["messages"][-1]
    assert isinstance(msg, ToolMessage)
    assert msg.status == "error"
    assert "denied" in msg.content.lower()
    assert msg.tool_call_id == "c1"

    # THE OBSERVABLE CONSEQUENCE: the file was never written.
    assert not target.exists(), "write_file side effect happened despite veto"


async def test_policy_risk_ceiling_vetoes_high_risk(tmp_path):
    """An allowed tool whose risk exceeds the ceiling is still vetoed."""
    target = tmp_path / "out.txt"

    # write_file is permitted by name but the ceiling is READ_ONLY while
    # write_file is WRITE risk -> must be denied on risk grounds.
    app = _build_app(ToolPolicy(allowed=frozenset({"write_file"}), max_risk=RiskLevel.READ_ONLY))
    result = await app.ainvoke({"messages": [AIMessage(content="", tool_calls=[_call("write_file", str(target), "c2")])]})

    msg = result["messages"][-1]
    assert msg.status == "error"
    assert "risk" in msg.content.lower() or "ceiling" in msg.content.lower()
    assert not target.exists()


async def test_policy_allows_permitted_tool_runs_handler(tmp_path):
    """A permitted, in-budget tool call must run and produce its real effect."""
    target = tmp_path / "ok.txt"

    app = _build_app(ToolPolicy(allowed=frozenset({"write_file"}), max_risk=RiskLevel.WRITE))
    await app.ainvoke({"messages": [AIMessage(content="", tool_calls=[_call("write_file", str(target), "c3")])]})

    # THE OBSERVABLE CONSEQUENCE: the file WAS written (handler executed).
    assert target.exists()
    assert target.read_text() == "secret"


async def test_policy_normalizes_cli_tool_name_aliases(tmp_path):
    """A tool call using a CLI alias (e.g. 'Write') is normalized before the check.

    Driven directly against ``awrap_tool_call`` because a bare ToolNode resolves
    tools by exact name before dispatch; the middleware's job is to normalize for
    the *policy* decision, which is what we assert here: an alias for an allowed
    tool is permitted (handler invoked), while an alias for a disallowed tool is
    denied.
    """
    from langgraph.prebuilt.tool_node import ToolCallRequest

    permitted = ToolPolicy(allowed=frozenset({"write_file"}), max_risk=RiskLevel.WRITE)
    mw = ToolPolicyMiddleware(policy=permitted)

    invoked: list[str] = []

    async def handler(_req: ToolCallRequest) -> ToolMessage:
        invoked.append("yes")
        return ToolMessage(content="ok", tool_call_id="c4")

    request = ToolCallRequest(
        tool_call={"name": "Write", "args": {}, "id": "c4", "type": "tool_call"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )
    result = await mw.awrap_tool_call(request, handler)
    assert invoked == ["yes"], "alias for an allowed tool should reach the handler"
    assert result.content == "ok"

    # And the inverse: an alias for a tool NOT in the policy is denied.
    denied = ToolPolicy(allowed=frozenset({"read_file"}), max_risk=RiskLevel.READ_ONLY)
    mw2 = ToolPolicyMiddleware(policy=denied)

    async def handler2(_req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="should-not-run", tool_call_id="c5")

    request2 = ToolCallRequest(
        tool_call={"name": "Bash", "args": {}, "id": "c5", "type": "tool_call"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )
    result2 = await mw2.awrap_tool_call(request2, handler2)
    assert result2.status == "error"
    assert "denied" in result2.content.lower()


@pytest.mark.asyncio
async def test_policy_denies_unregistered_tool_in_allowed_set():
    """A tool name in the allowed set but missing from the registry is denied.

    Defense-in-depth: an unregistered tool has no risk metadata, so the policy
    must refuse to forward it to the handler rather than silently executing it.
    """
    from langgraph.prebuilt.tool_node import ToolCallRequest

    policy = ToolPolicy(allowed=frozenset({"nonexistent_tool"}), max_risk=RiskLevel.EXECUTE)
    mw = ToolPolicyMiddleware(policy=policy)

    async def handler(_req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="should-not-run", tool_call_id="c6")

    request = ToolCallRequest(
        tool_call={"name": "nonexistent_tool", "args": {}, "id": "c6", "type": "tool_call"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )
    result = await mw.awrap_tool_call(request, handler)
    assert result.status == "error"
    assert "not registered" in result.content.lower()


@pytest.mark.parametrize("scaffold", ["ls", "write_todos", "task"])
async def test_policy_permits_registered_scaffolding_tools_when_allowed(scaffold):
    """deepagents scaffolding tools are permitted via registry allow-set entries."""
    from langgraph.prebuilt.tool_node import ToolCallRequest

    policy = ToolPolicy(allowed=frozenset({scaffold}), max_risk=RiskLevel.EXECUTE)
    mw = ToolPolicyMiddleware(policy=policy)

    invoked: list[str] = []

    async def handler(_req: ToolCallRequest) -> ToolMessage:
        invoked.append("yes")
        return ToolMessage(content="ok", tool_call_id="c7")

    request = ToolCallRequest(
        tool_call={"name": scaffold, "args": {}, "id": "c7", "type": "tool_call"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )
    result = await mw.awrap_tool_call(request, handler)
    assert invoked == ["yes"], f"registered scaffolding tool {scaffold!r} must reach handler"
    assert result.content == "ok"
