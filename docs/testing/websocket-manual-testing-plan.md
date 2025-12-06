# WebSocket Events Manual Testing Plan

**Branch:** `feature/websocket-events`
**Feature:** Real-time WebSocket event streaming with subscription filtering and reconnect backfill

## Overview

This plan tests the WebSocket endpoint at `/ws/events` which provides:
- Real-time workflow event streaming
- Subscription-based filtering (per-workflow or all workflows)
- Reconnect backfill via `?since=<event_id>` parameter
- Concurrent broadcast with 5-second timeout for slow clients
- Heartbeat ping/pong mechanism (30-second interval)

---

## Prerequisites

### Environment Setup

```bash
# 1. Install dependencies
cd /Users/ka/github/amelia
uv sync

# 2. Start the server in a terminal
uv run amelia-server start --reload

# 3. In another terminal, verify server is running
curl http://localhost:8000/health
```

### Testing Tools

Use `websocat` for WebSocket testing:
```bash
# Install websocat (macOS)
brew install websocat

# Alternative: use wscat
pnpm add -g wscat
```

---

## Test Scenarios

### TC-01: Basic Connection Establishment

**Objective:** Verify WebSocket connection can be established and accepted.

**Steps:**
1. Start the server: `uv run amelia-server start`
2. Connect via WebSocket: `websocat ws://localhost:8000/ws/events`
3. Connection should remain open without errors

**Expected Result:**
- Connection is accepted (no error messages)
- Server logs: `websocket_connected` with `active_connections=1`
- Connection stays open until client disconnects

**Verification Command:**
```bash
# Connect and observe - press Ctrl+C to disconnect
websocat ws://localhost:8000/ws/events
```

---

### TC-02: Subscribe to Specific Workflow

**Objective:** Verify subscription message is accepted.

**Steps:**
1. Connect to WebSocket
2. Send subscribe message: `{"type": "subscribe", "workflow_id": "wf-test-123"}`
3. Observe server logs

**Expected Result:**
- No error response from server
- Server logs: `subscription_added` with `workflow_id=wf-test-123`

**Verification Commands:**
```bash
# Connect and send subscribe message
echo '{"type": "subscribe", "workflow_id": "wf-test-123"}' | websocat ws://localhost:8000/ws/events
```

---

### TC-03: Unsubscribe from Workflow

**Objective:** Verify unsubscribe removes workflow from filter set.

**Steps:**
1. Connect to WebSocket
2. Send subscribe: `{"type": "subscribe", "workflow_id": "wf-test-123"}`
3. Send unsubscribe: `{"type": "unsubscribe", "workflow_id": "wf-test-123"}`
4. Observe server logs

**Expected Result:**
- Server logs both `subscription_added` then `subscription_removed`

**Verification Commands:**
```bash
# Interactive session - paste messages one at a time
websocat ws://localhost:8000/ws/events
# Then paste: {"type": "subscribe", "workflow_id": "wf-test-123"}
# Then paste: {"type": "unsubscribe", "workflow_id": "wf-test-123"}
```

---

### TC-04: Subscribe to All Workflows

**Objective:** Verify subscribe_all clears subscription filters.

**Steps:**
1. Connect to WebSocket
2. Send subscribe: `{"type": "subscribe", "workflow_id": "wf-test-123"}`
3. Send subscribe_all: `{"type": "subscribe_all"}`
4. Observe server logs

**Expected Result:**
- Server logs `subscribed_to_all`
- Client should now receive events for ALL workflows, not just wf-test-123

---

### TC-05: Heartbeat Ping/Pong

**Objective:** Verify server sends periodic ping messages and accepts pong responses.

**Steps:**
1. Connect to WebSocket
2. Wait 30+ seconds
3. Observe incoming ping message
4. Send pong response: `{"type": "pong"}`

**Expected Result:**
- After ~30 seconds, receive: `{"type": "ping"}`
- Server logs `heartbeat_ping_sent`
- After sending pong, server logs `heartbeat_pong_received`

**Note:** This test requires patience - ping is sent every 30 seconds.

---

### TC-06: Event Broadcast (requires workflow trigger)

**Objective:** Verify events are broadcast to connected clients.

**Precondition:** Need a way to trigger workflow events. Options:
- Start a workflow via CLI: `uv run amelia start TEST-123`
- Or use the event bus directly via test script

**Steps:**
1. Connect to WebSocket in one terminal: `websocat ws://localhost:8000/ws/events`
2. In another terminal, trigger a workflow
3. Observe events arriving on WebSocket

**Expected Result:**
- Receive messages like:
```json
{"type": "event", "payload": {"id": "...", "workflow_id": "...", "event_type": "workflow_started", ...}}
```

---

### TC-07: Subscription Filtering (events filtered by workflow)

**Objective:** Verify clients only receive events for subscribed workflows.

**Steps:**
1. Connect Client A, subscribe to `wf-aaa`: `{"type": "subscribe", "workflow_id": "wf-aaa"}`
2. Connect Client B, subscribe to `wf-bbb`: `{"type": "subscribe", "workflow_id": "wf-bbb"}`
3. Trigger event for workflow `wf-aaa`
4. Verify only Client A receives the event

**Expected Result:**
- Client A receives event for wf-aaa
- Client B receives nothing (filtered out)

---

### TC-08: Multiple Concurrent Connections

**Objective:** Verify server handles multiple simultaneous WebSocket connections.

**Steps:**
1. Open 3+ WebSocket connections in parallel
2. Verify each connection stays active
3. Check server logs for connection count

**Verification Commands:**
```bash
# Terminal 1
websocat ws://localhost:8000/ws/events &

# Terminal 2
websocat ws://localhost:8000/ws/events &

# Terminal 3
websocat ws://localhost:8000/ws/events

# Check server logs for active_connections=3
```

**Expected Result:**
- All connections remain open
- Server logs show `active_connections` incrementing with each connection

---

### TC-09: Backfill on Reconnect (with ?since parameter)

**Objective:** Verify reconnect backfill replays missed events.

**Precondition:** Database must have events. Run a workflow first or seed events.

**Steps:**
1. Connect and receive some events, note the `id` of one event
2. Disconnect
3. (Optional) Trigger more events while disconnected
4. Reconnect with `?since=<event_id>`: `websocat "ws://localhost:8000/ws/events?since=<event_id>"`
5. Observe backfilled events

**Expected Result:**
- Receive all events that occurred AFTER the specified event
- Finally receive: `{"type": "backfill_complete", "count": N}`

---

### TC-10: Backfill Expired (event no longer exists)

**Objective:** Verify proper handling when requested event was cleaned up.

**Steps:**
1. Connect with a non-existent event ID: `websocat "ws://localhost:8000/ws/events?since=evt-does-not-exist"`

**Expected Result:**
- Receive: `{"type": "backfill_expired", "message": "Requested event no longer exists. Full refresh required."}`
- Server logs `backfill_expired`

---

### TC-11: Graceful Disconnect Handling

**Objective:** Verify server cleans up when client disconnects.

**Steps:**
1. Connect to WebSocket
2. Note initial connection count in logs
3. Disconnect (Ctrl+C)
4. Verify cleanup in logs

**Expected Result:**
- Server logs `websocket_disconnected`
- Server logs `websocket_cleanup` with decremented `active_connections`
- No errors or exceptions

---

### TC-12: Graceful Server Shutdown

**Objective:** Verify WebSocket connections close gracefully on server shutdown.

**Steps:**
1. Connect multiple WebSocket clients
2. Stop the server (Ctrl+C on server process)
3. Observe client-side disconnect

**Expected Result:**
- Clients receive close frame (code 1001 = Going Away)
- Server logs indicate graceful shutdown
- No hanging connections

---

### TC-13: Slow Client Timeout (5-second broadcast timeout)

**Objective:** Verify slow/hung clients are disconnected to prevent blocking others.

**Note:** This is difficult to test manually without a custom client that delays acknowledgment. The behavior is:
- Broadcast uses `asyncio.wait_for` with 5-second timeout
- Clients that don't receive within 5 seconds are disconnected

**Verification:**
- Review code at `connection_manager.py:109` for `timeout=5.0`
- Unit tests cover this scenario

---

### TC-14: Invalid Message Handling

**Objective:** Verify server handles malformed messages gracefully.

**Steps:**
1. Connect to WebSocket
2. Send invalid JSON: `not json at all`
3. Send valid JSON with unknown type: `{"type": "unknown_command"}`

**Expected Result:**
- Server should not crash
- Connection may close on invalid JSON
- Unknown types are ignored (no error sent to client)

---

### TC-15: Connection Count Accuracy

**Objective:** Verify `active_connections` count is accurate.

**Steps:**
1. Start with no connections, verify count = 0
2. Connect 3 clients, verify count = 3
3. Disconnect 1 client, verify count = 2
4. Disconnect remaining, verify count = 0

**Verification:**
- Check server logs for `active_connections` values
- Use health endpoint or server metrics if available

---

## Test Environment Cleanup

After testing:
```bash
# Stop the server
# Ctrl+C on the server terminal

# Clean up any background websocat processes
pkill websocat
```

---

## Test Result Template

| Test ID | Description | Status | Notes |
|---------|-------------|--------|-------|
| TC-01 | Basic Connection | [ ] Pass / [ ] Fail | |
| TC-02 | Subscribe Workflow | [ ] Pass / [ ] Fail | |
| TC-03 | Unsubscribe Workflow | [ ] Pass / [ ] Fail | |
| TC-04 | Subscribe All | [ ] Pass / [ ] Fail | |
| TC-05 | Heartbeat Ping/Pong | [ ] Pass / [ ] Fail | |
| TC-06 | Event Broadcast | [ ] Pass / [ ] Fail | |
| TC-07 | Subscription Filtering | [ ] Pass / [ ] Fail | |
| TC-08 | Concurrent Connections | [ ] Pass / [ ] Fail | |
| TC-09 | Backfill on Reconnect | [ ] Pass / [ ] Fail | |
| TC-10 | Backfill Expired | [ ] Pass / [ ] Fail | |
| TC-11 | Graceful Disconnect | [ ] Pass / [ ] Fail | |
| TC-12 | Graceful Shutdown | [ ] Pass / [ ] Fail | |
| TC-13 | Slow Client Timeout | [ ] Pass / [ ] Fail | (Unit test verification) |
| TC-14 | Invalid Message | [ ] Pass / [ ] Fail | |
| TC-15 | Connection Count | [ ] Pass / [ ] Fail | |

---

## Agent Execution Notes

### For LLM Agent Executing This Plan:

1. **Start server first** - Run `uv run amelia-server start` in background
2. **Check server health** - Verify `curl http://localhost:8000/health` returns 200
3. **Execute tests sequentially** - Some tests depend on server state
4. **Capture logs** - Server logs contain important verification data
5. **Use websocat or Python** - For WebSocket testing
6. **Mark results** - Update the result template after each test
7. **Report issues** - Note any failures with exact error messages

### Python Alternative for WebSocket Testing:

```python
import asyncio
import websockets
import json

async def test_connection():
    uri = "ws://localhost:8000/ws/events"
    async with websockets.connect(uri) as ws:
        # Send subscribe
        await ws.send(json.dumps({"type": "subscribe", "workflow_id": "wf-test"}))

        # Wait for messages
        try:
            async for message in ws:
                print(f"Received: {message}")
        except websockets.ConnectionClosed:
            print("Connection closed")

asyncio.run(test_connection())
```

---

## Key Changes in This Branch

The following changes should be verified through testing:

1. **Concurrent broadcast** (`connection_manager.py`):
   - Changed from sequential to concurrent sends via `asyncio.gather()`
   - Added 5-second timeout per client

2. **Backfill error handling** (`websocket.py`):
   - Changed from `event_exists()` check to try/except on `get_events_after()`
   - `ValueError` from repository triggers `backfill_expired` message

3. **Protocol messages** (`models/websocket.py`):
   - Client messages: subscribe, unsubscribe, subscribe_all, pong
   - Server messages: event, ping, backfill_complete, backfill_expired
