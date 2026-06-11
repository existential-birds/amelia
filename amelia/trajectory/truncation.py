"""Presentation-only string truncation for event and summary payloads.

Truncation never touches recorded trajectory files; it keeps display strings
and event-bus payloads small. Both the server's stream emitter and the
trajectory projection apply this same policy.
"""
from typing import Any


# Truncate strings to ~500 chars: long enough to be useful for debugging,
# short enough to avoid bloating event payloads.
MAX_SUMMARY_STRING_LENGTH = 500


def truncate_nested(value: Any) -> Any:
    """Recursively truncate long strings in nested structures.

    Args:
        value: Any value that may contain nested strings.

    Returns:
        A copy with all long strings truncated.
    """
    if isinstance(value, str):
        if len(value) > MAX_SUMMARY_STRING_LENGTH:
            return value[:MAX_SUMMARY_STRING_LENGTH] + "… [truncated]"
        return value
    if isinstance(value, dict):
        return {k: truncate_nested(v) for k, v in value.items()}
    if isinstance(value, list):
        return [truncate_nested(item) for item in value]
    return value
