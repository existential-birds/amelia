"""Pure helpers for orchestrator stream event emission.

These functions contain no orchestrator state — they are pure mappings over
stream chunks and node output. Keeping them here lets the emission seam be
tested in isolation from the service.
"""

from typing import Any


# Nodes that emit stage events
STAGE_NODES: frozenset[str] = frozenset({
    "architect_node",
    "plan_validator_node",
    "human_approval_node",
    "developer_node",
    "reviewer_node",
    "evaluation_node",
})


# Truncate strings in workflow summaries to ~500 chars: long enough to be useful
# for debugging, short enough to avoid bloating PostgreSQL JSONB storage.
_MAX_SUMMARY_STRING_LENGTH = 500


def _truncate_nested(value: Any) -> Any:
    """Recursively truncate long strings in nested structures.

    Args:
        value: Any value that may contain nested strings.

    Returns:
        A copy with all long strings truncated.
    """
    if isinstance(value, str):
        if len(value) > _MAX_SUMMARY_STRING_LENGTH:
            return value[:_MAX_SUMMARY_STRING_LENGTH] + "… [truncated]"
        return value
    if isinstance(value, dict):
        return {k: _truncate_nested(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate_nested(item) for item in value]
    return value


def summarize_stage_output(output: dict[str, Any] | None) -> dict[str, Any] | None:
    """Summarize node output for STAGE_COMPLETED events.

    Replaces large lists (tool_calls, tool_results) with counts and truncates
    long strings (including in nested structures) to avoid exceeding PostgreSQL's
    JSONB size limit.

    Args:
        output: Raw node output dictionary.

    Returns:
        A summarized copy of the output, or None if input is None.
    """
    if output is None:
        return None

    result: dict[str, Any] = {}
    for key, value in output.items():
        if key in ("tool_calls", "tool_results") and isinstance(value, list):
            result[f"{key}_count"] = len(value)
        else:
            result[key] = _truncate_nested(value)
    return result


def is_interrupt_chunk(chunk: tuple[str, Any] | dict[str, Any]) -> bool:
    """Check if a stream chunk represents an interrupt.

    Works with both combined mode (tuple) and single mode (dict).

    Args:
        chunk: Stream chunk from astream().

    Returns:
        True if this chunk contains an interrupt signal.
    """
    if isinstance(chunk, tuple):
        mode, data = chunk
        if mode == "updates" and isinstance(data, dict):
            return "__interrupt__" in data
        return False
    # Single mode (dict)
    return "__interrupt__" in chunk
