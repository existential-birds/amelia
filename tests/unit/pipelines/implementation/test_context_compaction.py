"""Tests for implementation context compaction."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from amelia.core.agentic_state import ToolCall, ToolResult
from amelia.pipelines.implementation.context_compaction import (
    COMPACTION_MARKER_TOOL_NAME,
    ReplaceList,
    compact_implementation_context,
    compacting_list_reducer,
    should_compact_context,
)
from amelia.pipelines.implementation.state import ImplementationState


def _state_with_turns(count: int) -> ImplementationState:
    return ImplementationState(
        workflow_id=uuid4(),
        profile_id="test-profile",
        created_at=datetime.now(UTC),
        status="running",
        goal="implement context compaction",
        plan_markdown="# Plan",
        tool_calls=[
            ToolCall(id=f"call-{i}", tool_name="read_file", tool_input={"path": f"file-{i}.py"})
            for i in range(count)
        ],
        tool_results=[
            ToolResult(
                call_id=f"call-{i}",
                tool_name="read_file",
                output=f"result {i}",
                success=True,
            )
            for i in range(count)
        ],
    )


def test_compaction_preserves_first_turn_recent_turns_and_marker() -> None:
    state = _state_with_turns(8)

    compacted, event = compact_implementation_context(
        state,
        keep_last_n_turns=2,
        reason="test threshold crossed",
    )

    assert [call.id for call in compacted.tool_calls] == [
        "call-0",
        "context-compaction-marker-1",
        "call-6",
        "call-7",
    ]
    assert [result.call_id for result in compacted.tool_results] == [
        "call-0",
        "context-compaction-marker-1",
        "call-6",
        "call-7",
    ]
    marker = compacted.tool_results[1]
    assert marker.tool_name == COMPACTION_MARKER_TOOL_NAME
    assert "Omitted 5 middle tool turn(s)" in marker.output
    assert "call-1" in marker.output
    assert "call-5" in marker.output
    assert event is not None
    assert event.data is not None
    assert event.data["omitted_turns"] == 5


def test_compaction_reducer_can_replace_append_only_state() -> None:
    existing = _state_with_turns(5).tool_results
    compacted, _ = compact_implementation_context(_state_with_turns(5), keep_last_n_turns=1)

    merged = compacting_list_reducer(existing, ReplaceList(compacted.tool_results))

    assert merged == compacted.tool_results
    assert len(merged) < len(existing)
    assert any(result.tool_name == COMPACTION_MARKER_TOOL_NAME for result in merged)


def test_should_compact_context_uses_context_utilization_threshold() -> None:
    state = _state_with_turns(4)

    assert should_compact_context(
        state,
        context_utilization=0.91,
        threshold=0.9,
        keep_last_n_turns=1,
    )
    assert not should_compact_context(state, context_utilization=0.5, threshold=0.9)
    assert not should_compact_context(_state_with_turns(2), context_utilization=0.91, threshold=0.9)
