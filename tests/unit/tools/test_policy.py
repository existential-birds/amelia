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

from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventType
from amelia.tools.registry.policy import (
    HighRiskDecision,
    ToolPolicy,
    ToolPolicyAuditDecision,
    ToolPolicyMiddleware,
    ToolValidationResult,
)
from amelia.tools.registry.spec import Permission, RiskLevel


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


def _make_sync_write_tool() -> StructuredTool:
    """Build a sync StructuredTool that writes to disk (for sync invoke() tests)."""

    def _write(*, file_path: str, content: str) -> str:
        Path(file_path).write_text(content, encoding="utf-8")
        return f"wrote {file_path}"

    return StructuredTool.from_function(
        func=_write,
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


def _build_sync_app(policy: ToolPolicy) -> Any:
    """Compile a graph using the sync wrap_tool_call hook, driven via invoke()."""
    mw = ToolPolicyMiddleware(policy=policy)
    node = ToolNode(tools=[_make_sync_write_tool()], wrap_tool_call=mw.wrap_tool_call)
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


def _direct_request(name: str, args: dict[str, object] | None = None, call_id: str = "c"):
    from langgraph.prebuilt.tool_node import ToolCallRequest

    return ToolCallRequest(
        tool_call={"name": name, "args": args or {}, "id": call_id, "type": "tool_call"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )


def _collecting_bus() -> tuple[EventBus, list[Any]]:
    bus = EventBus()
    events: list[Any] = []
    bus.subscribe(events.append)
    return bus, events


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


async def test_policy_denies_destructive_tool_and_emits_audit_event():
    """High-risk decisions are deterministic and auditable."""
    bus, events = _collecting_bus()
    policy = ToolPolicy(
        allowed=frozenset({"execute"}),
        max_risk=RiskLevel.DESTRUCTIVE,
        high_risk_decision=HighRiskDecision.CONFIRM,
        permissions=frozenset({Permission.SHELL_EXEC}),
    )
    mw = ToolPolicyMiddleware(policy=policy, event_bus=bus)
    invoked: list[str] = []

    async def handler(_req: Any) -> ToolMessage:
        invoked.append("yes")
        return ToolMessage(content="should-not-run", tool_call_id="destructive")

    result = await mw.awrap_tool_call(
        _direct_request("execute", {"cmd": "rm -rf ."}, "destructive"), handler
    )

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "confirmation" in result.content.lower()
    assert invoked == []
    assert events
    event = events[-1]
    assert event.event_type == EventType.TOOL_POLICY_DECISION
    assert event.data["decision"] == ToolPolicyAuditDecision.DENIED
    assert event.data["reason"] == "confirmation_required"


async def test_policy_allows_permitted_tool_runs_handler(tmp_path):
    """A permitted, in-budget tool call must run and produce its real effect."""
    target = tmp_path / "ok.txt"

    app = _build_app(ToolPolicy(allowed=frozenset({"write_file"}), max_risk=RiskLevel.WRITE))
    await app.ainvoke({"messages": [AIMessage(content="", tool_calls=[_call("write_file", str(target), "c3")])]})

    # THE OBSERVABLE CONSEQUENCE: the file WAS written (handler executed).
    assert target.exists()
    assert target.read_text() == "secret"


async def test_policy_allows_low_risk_tool_and_emits_allow_and_result_audit_events():
    bus, events = _collecting_bus()
    policy = ToolPolicy(
        allowed=frozenset({"read_file"}),
        max_risk=RiskLevel.READ_ONLY,
        permissions=frozenset({Permission.FS_READ}),
    )
    mw = ToolPolicyMiddleware(policy=policy, event_bus=bus)

    async def handler(_req: Any) -> ToolMessage:
        return ToolMessage(content="ok", tool_call_id="read")

    result = await mw.awrap_tool_call(
        _direct_request("read_file", {"file_path": "README.md"}, "read"), handler
    )

    assert isinstance(result, ToolMessage)
    assert result.content == "ok"
    assert [event.data["decision"] for event in events] == [
        ToolPolicyAuditDecision.ALLOWED,
        ToolPolicyAuditDecision.RESULT,
    ]
    assert all(event.event_type == EventType.TOOL_POLICY_DECISION for event in events)


async def test_policy_pre_validator_blocks_parameters_without_handler_execution():
    bus, events = _collecting_bus()
    invoked: list[str] = []

    def block_absolute_path(ctx: Any) -> ToolValidationResult:
        if str(ctx.args.get("file_path", "")).startswith("/"):
            return ToolValidationResult.deny("absolute paths are not allowed")
        return ToolValidationResult.allow()

    policy = ToolPolicy(
        allowed=frozenset({"write_file"}),
        max_risk=RiskLevel.WRITE,
        permissions=frozenset({Permission.FS_WRITE}),
        pre_exec_validators=(block_absolute_path,),
    )
    mw = ToolPolicyMiddleware(policy=policy, event_bus=bus)

    async def handler(_req: Any) -> ToolMessage:
        invoked.append("yes")
        return ToolMessage(content="should-not-run", tool_call_id="pre")

    result = await mw.awrap_tool_call(
        _direct_request("write_file", {"file_path": "/tmp/x"}, "pre"), handler
    )

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "absolute paths" in result.content
    assert invoked == []
    assert events[-1].data["reason"] == "pre_validator"


async def test_policy_post_validator_can_transform_tool_message_result():
    def redact_result(ctx: Any) -> ToolValidationResult:
        assert isinstance(ctx.result, ToolMessage)
        return ToolValidationResult.replace(
            ToolMessage(content="redacted", tool_call_id=ctx.result.tool_call_id)
        )

    policy = ToolPolicy(
        allowed=frozenset({"read_file"}),
        max_risk=RiskLevel.READ_ONLY,
        permissions=frozenset({Permission.FS_READ}),
        post_exec_validators=(redact_result,),
    )
    mw = ToolPolicyMiddleware(policy=policy)

    async def handler(_req: Any) -> ToolMessage:
        return ToolMessage(content="secret", tool_call_id="post")

    result = await mw.awrap_tool_call(
        _direct_request("read_file", {"file_path": "x"}, "post"), handler
    )

    assert isinstance(result, ToolMessage)
    assert result.content == "redacted"


async def test_policy_required_permission_mismatch_denies_with_useful_message():
    policy = ToolPolicy(
        allowed=frozenset({"write_file"}),
        max_risk=RiskLevel.WRITE,
        permissions=frozenset({Permission.FS_READ}),
    )
    mw = ToolPolicyMiddleware(policy=policy)

    async def handler(_req: Any) -> ToolMessage:
        return ToolMessage(content="should-not-run", tool_call_id="perm")

    result = await mw.awrap_tool_call(_direct_request("write_file", {}, "perm"), handler)

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "missing required permission" in result.content.lower()
    assert "fs.write" in result.content


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


def test_sync_wrap_tool_call_vetoes_without_running_handler(tmp_path):
    """The sync middleware hook must prevent the guarded side effect.

    Enters through the production graph entrypoint (compiled StateGraph driven
    via invoke()) with wrap_tool_call wired into ToolNode — the same path a real
    sync agent uses.  The observable consequence is the assertion: the file was
    never written to disk.
    """
    target = tmp_path / "out_sync.txt"
    assert not target.exists()

    app = _build_sync_app(ToolPolicy(allowed=frozenset({"read_file"}), max_risk=RiskLevel.READ_ONLY))
    result = app.invoke({"messages": [AIMessage(content="", tool_calls=[_call("write_file", str(target), "c_sync")])]})

    msg = result["messages"][-1]
    assert isinstance(msg, ToolMessage)
    assert msg.status == "error"
    assert "denied" in msg.content.lower()

    # THE OBSERVABLE CONSEQUENCE: the file was never written.
    assert not target.exists(), "write_file side effect happened despite sync veto"


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
