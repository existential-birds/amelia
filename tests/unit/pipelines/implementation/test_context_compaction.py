"""Tests for implementation context compaction."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from amelia.core.agentic_state import ToolCall, ToolResult
from amelia.pipelines.implementation.context_compaction import (
    COMPACTION_MARKER_CALL_ID_PREFIX,
    COMPACTION_MARKER_TOOL_NAME,
    ReplaceList,
    _aggregate_prior_markers,
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


def test_re_compaction_flattens_prior_marker_and_uses_real_call_ids() -> None:
    """Re-compacting already-compacted history sums prior marker turns.

    After the first compaction the omitted range is represented by a single
    marker call. A second compaction must not report just "1 turn omitted"
    or point its omitted range at the marker id; it aggregates the prior
    marker's omitted_turns and uses the original real call ids.
    """
    state = _state_with_turns(8)
    first, _ = compact_implementation_context(state, keep_last_n_turns=2, reason="round 1")

    second, event = compact_implementation_context(first, keep_last_n_turns=1, reason="round 2")
    assert event is not None
    assert event.data is not None

    marker_calls = [c for c in second.tool_calls if c.tool_name == COMPACTION_MARKER_TOOL_NAME]
    assert len(marker_calls) == 1
    new_marker = marker_calls[0]

    assert new_marker.id == f"{COMPACTION_MARKER_CALL_ID_PREFIX}-2"
    # omitted = 5 (from prior marker) + 1 (real call-6) = 6
    assert new_marker.tool_input["omitted_turns"] == 6
    assert new_marker.tool_input["first_omitted_call_id"] == "call-1"
    assert new_marker.tool_input["last_omitted_call_id"] == "call-6"
    assert event.data["omitted_turns"] == 6
    assert event.data["first_omitted_call_id"] == "call-1"
    assert event.data["last_omitted_call_id"] == "call-6"


def test_aggregate_prior_markers_sums_marker_and_real_turns() -> None:
    calls = [
        ToolCall(
            id=f"{COMPACTION_MARKER_CALL_ID_PREFIX}-1",
            tool_name=COMPACTION_MARKER_TOOL_NAME,
            tool_input={
                "omitted_turns": 4,
                "first_omitted_call_id": "real-1",
                "last_omitted_call_id": "real-4",
            },
        ),
        ToolCall(id="real-5", tool_name="read_file", tool_input={}),
        ToolCall(id="real-6", tool_name="read_file", tool_input={}),
    ]
    total, first, last = _aggregate_prior_markers(calls)
    assert total == 6
    assert first == "real-1"
    assert last == "real-6"


def test_aggregate_prior_markers_only_markers_uses_marker_metadata() -> None:
    calls = [
        ToolCall(
            id=f"{COMPACTION_MARKER_CALL_ID_PREFIX}-1",
            tool_name=COMPACTION_MARKER_TOOL_NAME,
            tool_input={
                "omitted_turns": 3,
                "first_omitted_call_id": "a",
                "last_omitted_call_id": "c",
            },
        ),
    ]
    total, first, last = _aggregate_prior_markers(calls)
    assert total == 3
    assert first == "a"
    assert last == "c"
