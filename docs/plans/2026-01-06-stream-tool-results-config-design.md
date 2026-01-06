# Stream Tool Results Configuration

**Date:** 2026-01-06
**Status:** Approved

## Problem

The dashboard frontend struggles with the volume of streaming logs. Tool result events are particularly problematic because they can be large (file contents, command output) and are rarely needed during normal operation.

## Solution

Add a server environment variable `AMELIA_STREAM_TOOL_RESULTS` that controls whether tool result events are broadcast over WebSocket. Default to `false` (filtered out), with the option to enable for debugging.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AMELIA_STREAM_TOOL_RESULTS` | `false` | Stream tool result events to dashboard. Enable for debugging. |

**Behavior:**
- `false` (default): Tool result events are silently dropped before WebSocket broadcast
- `true`: All stream events broadcast (full debugging visibility)

## Implementation

Filter in `EventBus.emit_stream()` - the single point where all stream events are broadcast:

```python
# amelia/server/events/bus.py

def emit_stream(self, event: StreamEvent) -> None:
    """Broadcast ephemeral stream event to WebSocket clients."""
    if event.subtype == StreamEventType.CLAUDE_TOOL_RESULT and not settings.stream_tool_results:
        return  # Suppress tool results when disabled

    # ... existing broadcast logic
```

**Why this location:**
- Single choke point - all stream events flow through `emit_stream()`
- No changes needed to agents, connection manager, or WebSocket protocol
- Event is never queued, so zero overhead when filtered

## Files Changed

1. `amelia/server/settings.py` - Add `stream_tool_results` setting
2. `amelia/server/events/bus.py` - Add filter check in `emit_stream()`
3. `CLAUDE.md` - Document the env var in server configuration table

## Testing

Unit test in `tests/unit/server/events/test_bus.py`:
- Verify `emit_stream()` skips tool results when `stream_tool_results=False`
- Verify other event types still broadcast
- Verify tool results broadcast when `stream_tool_results=True`
