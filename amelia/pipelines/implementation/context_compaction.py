"""Deterministic context compaction for implementation workflows."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, TypeVar
from uuid import uuid4

from amelia.core.agentic_state import ToolCall, ToolResult
from amelia.server.models.events import EventLevel, EventType, WorkflowEvent


if TYPE_CHECKING:
    from amelia.pipelines.implementation.state import ImplementationState

T = TypeVar("T")

COMPACTION_MARKER_TOOL_NAME = "context_compaction"
COMPACTION_MARKER_CALL_ID_PREFIX = "context-compaction-marker"
DEFAULT_KEEP_LAST_N_TURNS = 6
DEFAULT_COMPACTION_THRESHOLD = 0.85


class ReplaceList(list[T]):
    """List wrapper that tells LangGraph reducers to replace instead of append.

    ImplementationState tool_calls/tool_results are reducer-backed append-only
    lists. Returning a normal shorter list from a graph node would be appended
    to the prior state instead of pruning it. Wrapping the compacted value in
    ReplaceList lets the custom reducer distinguish intentional state rewrites
    from normal incremental appends.
    """


def compacting_list_reducer(left: Sequence[T], right: Sequence[T]) -> list[T]:
    """Append normal updates, but allow explicit compaction rewrites."""
    if isinstance(right, ReplaceList):
        return list(right)
    return [*left, *right]


def _marker_id(existing_calls: Sequence[ToolCall]) -> str:
    return f"{COMPACTION_MARKER_CALL_ID_PREFIX}-{sum(1 for c in existing_calls if c.tool_name == COMPACTION_MARKER_TOOL_NAME) + 1}"


def _aggregate_prior_markers(
    omitted_calls: Sequence[ToolCall],
) -> tuple[int, str | None, str | None]:
    """Sum omitted_turns from prior compaction markers in ``omitted_calls``.

    Returns ``(total_omitted_turns, first_real_call_id, last_real_call_id)``.
    Real call IDs skip marker calls; ``None`` is returned when no real calls
    exist in the range.
    """
    total = 0
    first_real: str | None = None
    last_real: str | None = None
    for call in omitted_calls:
        if call.tool_name == COMPACTION_MARKER_TOOL_NAME:
            prior = call.tool_input.get("omitted_turns")
            if isinstance(prior, int):
                total += prior
            prior_first = call.tool_input.get("first_omitted_call_id")
            if isinstance(prior_first, str) and first_real is None:
                first_real = prior_first
            prior_last = call.tool_input.get("last_omitted_call_id")
            if isinstance(prior_last, str):
                last_real = prior_last
        else:
            if first_real is None:
                first_real = call.id
            last_real = call.id
            total += 1
    return total, first_real, last_real


def _build_marker_output(
    omitted_calls: Sequence[ToolCall],
    omitted_results: Sequence[ToolResult],
    *,
    reason: str | None,
    total_omitted_turns: int,
    first_call_id: str,
    last_call_id: str,
) -> str:
    names = ", ".join(dict.fromkeys(call.tool_name for call in omitted_calls[:10]))
    result_tokens = sum(len(result.output.split()) for result in omitted_results)
    reason_text = f" Reason: {reason}." if reason else ""
    return (
        "[CONTEXT COMPACTED] "
        f"Omitted {total_omitted_turns} middle tool turn(s) to keep the workflow within "
        f"the model context window.{reason_text} "
        f"Protected first turn and the most recent turns are preserved. "
        f"Omitted range: {first_call_id}..{last_call_id}. "
        f"Tool names seen: {names or 'unknown'}. "
        f"Approx omitted result words: {result_tokens}."
    )


def _split_for_compaction(
    calls: Sequence[ToolCall],
    results: Sequence[ToolResult],
    keep_last_n_turns: int,
) -> tuple[
    list[ToolCall],
    list[ToolResult],
    list[ToolCall],
    list[ToolResult],
    list[ToolCall],
    list[ToolResult],
]:
    keep_last = max(1, keep_last_n_turns)
    protected_count = 1
    tail_start = max(protected_count, len(calls) - keep_last)
    return (
        list(calls[:protected_count]),
        list(results[:protected_count]),
        list(calls[protected_count:tail_start]),
        list(results[protected_count:tail_start]),
        list(calls[tail_start:]),
        list(results[tail_start:]),
    )


def compact_implementation_context(
    state: ImplementationState,
    *,
    keep_last_n_turns: int = DEFAULT_KEEP_LAST_N_TURNS,
    reason: str | None = None,
) -> tuple[ImplementationState, WorkflowEvent | None]:
    """Compact middle implementation tool history while preserving continuity.

    The first tool turn is protected as setup context, the most recent N turns
    remain verbatim for continuation, and the omitted middle is represented by a
    transparent marker in both calls and results.
    """
    if len(state.tool_calls) != len(state.tool_results):
        paired_turns = min(len(state.tool_calls), len(state.tool_results))
        calls = state.tool_calls[:paired_turns]
        results = state.tool_results[:paired_turns]
    else:
        calls = state.tool_calls
        results = state.tool_results

    if len(calls) <= keep_last_n_turns + 2:
        return state, None

    protected_calls, protected_results, omitted_calls, omitted_results, tail_calls, tail_results = (
        _split_for_compaction(calls, results, keep_last_n_turns)
    )
    if not omitted_calls:
        return state, None

    total_omitted, first_call_id, last_call_id = _aggregate_prior_markers(omitted_calls)
    if first_call_id is None:
        first_call_id = "unknown"
    if last_call_id is None:
        last_call_id = "unknown"

    marker_id = _marker_id(calls)
    marker_call = ToolCall(
        id=marker_id,
        tool_name=COMPACTION_MARKER_TOOL_NAME,
        tool_input={
            "omitted_turns": total_omitted,
            "first_omitted_call_id": first_call_id,
            "last_omitted_call_id": last_call_id,
        },
    )
    marker_result = ToolResult(
        call_id=marker_id,
        tool_name=COMPACTION_MARKER_TOOL_NAME,
        output=_build_marker_output(
            omitted_calls,
            omitted_results,
            reason=reason,
            total_omitted_turns=total_omitted,
            first_call_id=first_call_id,
            last_call_id=last_call_id,
        ),
        success=True,
    )

    compacted_calls: list[ToolCall] = [*protected_calls, marker_call, *tail_calls]
    compacted_results: list[ToolResult] = [*protected_results, marker_result, *tail_results]
    compacted_state = state.model_copy(update={
        "tool_calls": ReplaceList(compacted_calls),
        "tool_results": ReplaceList(compacted_results),
    })

    event = WorkflowEvent(
        id=uuid4(),
        workflow_id=state.workflow_id,
        sequence=0,
        timestamp=datetime.now(UTC),
        agent="developer",
        event_type=EventType.CONTEXT_COMPACTED,
        level=EventLevel.INFO,
        message=(
            f"Compacted workflow context: omitted {total_omitted} middle tool turn(s), "
            f"kept first turn and last {len(tail_calls)} turn(s)."
        ),
        data={
            "omitted_turns": total_omitted,
            "kept_first_turns": len(protected_calls),
            "kept_recent_turns": len(tail_calls),
            "first_omitted_call_id": first_call_id,
            "last_omitted_call_id": last_call_id,
            "reason": reason,
        },
    )
    return compacted_state, event


def should_compact_context(
    state: ImplementationState,
    *,
    context_utilization: float | None,
    threshold: float = DEFAULT_COMPACTION_THRESHOLD,
    keep_last_n_turns: int = DEFAULT_KEEP_LAST_N_TURNS,
) -> bool:
    """Return whether context metadata says this state should be compacted."""
    if not isinstance(context_utilization, int | float):
        return False
    if context_utilization is None or context_utilization < threshold:
        return False
    return len(state.tool_calls) > keep_last_n_turns + 2
