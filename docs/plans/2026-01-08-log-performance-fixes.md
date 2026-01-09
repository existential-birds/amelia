# Log Performance Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix infinite loading state and improve frontend/backend performance for large log volumes (100-node workflows producing tens of thousands of events).

**Architecture:** Three-layer fix: (1) Add pagination to backend event backfill to prevent memory exhaustion, (2) Add API request timeouts to prevent infinite loading, (3) Batch frontend store updates to reduce React re-renders and GC pressure.

**Tech Stack:** Python/FastAPI (backend), TypeScript/React/Zustand (frontend), Vitest/pytest (testing)

---

## Task 1: Add Pagination to Backend Event Backfill

**Files:**
- Modify: `amelia/server/database/repository.py:447-483`
- Modify: `amelia/server/routes/websocket.py:46-72`
- Test: `tests/unit/server/routes/test_websocket_routes.py`

### Step 1.1: Write failing test for backfill limit

```python
# Add to tests/unit/server/routes/test_websocket_routes.py

async def test_websocket_backfill_respects_limit(
    self, mock_connection_manager, mock_repository, mock_websocket
) -> None:
    """WebSocket backfill should be limited to prevent memory exhaustion."""
    # Create 1500 mock events (exceeds 1000 limit)
    many_events = [
        WorkflowEvent(
            id=f"evt-{i}",
            workflow_id="wf-123",
            sequence=i,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.CLAUDE_TOOL_CALL,
            message=f"Event {i}",
        )
        for i in range(2, 1502)
    ]
    mock_repository.get_events_after.return_value = many_events

    mock_websocket.receive_json.side_effect = Exception("disconnect")

    with patch("amelia.server.routes.websocket.connection_manager", mock_connection_manager):
        await websocket_endpoint(mock_websocket, since="evt-1")

    # Should request with limit
    mock_repository.get_events_after.assert_awaited_once_with("evt-1", limit=1000)
```

### Step 1.2: Run test to verify it fails

Run: `uv run pytest tests/unit/server/routes/test_websocket_routes.py::TestWebSocketEndpoint::test_websocket_backfill_respects_limit -v`
Expected: FAIL - `get_events_after()` called with wrong arguments (missing limit)

### Step 1.3: Add limit parameter to `get_events_after`

```python
# In amelia/server/database/repository.py, modify get_events_after (line 447)

async def get_events_after(
    self, since_event_id: str, limit: int = 1000
) -> list[WorkflowEvent]:
    """Get events after a specific event (for backfill on reconnect).

    Args:
        since_event_id: The event ID to start after.
        limit: Maximum number of events to return (default 1000).

    Returns:
        List of events after the given event, ordered by sequence.

    Raises:
        ValueError: If the since_event_id doesn't exist.
    """
    # First, get the workflow_id and sequence of the since event
    row = await self._db.fetch_one(
        "SELECT workflow_id, sequence FROM events WHERE id = ?",
        (since_event_id,),
    )

    if row is None:
        raise ValueError(f"Event {since_event_id} not found")

    workflow_id, since_sequence = row["workflow_id"], row["sequence"]

    # Get events from same workflow with higher sequence, limited
    rows = await self._db.fetch_all(
        """
        SELECT id, workflow_id, sequence, timestamp, agent, event_type,
               level, message, data_json, correlation_id,
               tool_name, tool_input_json, is_error, trace_id, parent_id
        FROM events
        WHERE workflow_id = ? AND sequence > ?
        ORDER BY sequence ASC
        LIMIT ?
        """,
        (workflow_id, since_sequence, limit),
    )

    return [self._row_to_event(row) for row in rows]
```

### Step 1.4: Update websocket route to pass limit

```python
# In amelia/server/routes/websocket.py, modify line 52

events = await repository.get_events_after(since, limit=1000)
```

### Step 1.5: Run test to verify it passes

Run: `uv run pytest tests/unit/server/routes/test_websocket_routes.py::TestWebSocketEndpoint::test_websocket_backfill_respects_limit -v`
Expected: PASS

### Step 1.6: Run all websocket tests to check for regressions

Run: `uv run pytest tests/unit/server/routes/test_websocket_routes.py -v`
Expected: All tests pass

### Step 1.7: Commit

```bash
git add amelia/server/database/repository.py amelia/server/routes/websocket.py tests/unit/server/routes/test_websocket_routes.py
git commit -m "$(cat <<'EOF'
fix(backend): add pagination limit to event backfill

Prevents memory exhaustion when reconnecting after long disconnection.
The get_events_after() query now defaults to 1000 events max.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add API Request Timeout to Frontend

**Files:**
- Modify: `dashboard/src/api/client.ts:69-91`
- Test: `dashboard/src/api/__tests__/client.test.ts`

### Step 2.1: Write failing test for request timeout

```typescript
// Add to dashboard/src/api/__tests__/client.test.ts

describe('request timeout', () => {
  it('should abort request after timeout', async () => {
    vi.useFakeTimers();

    // Mock fetch that never resolves
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementationOnce(
      () => new Promise(() => {}) // Never resolves
    );

    const promise = api.getWorkflows();

    // Advance past timeout (30 seconds)
    vi.advanceTimersByTime(30001);

    await expect(promise).rejects.toThrow('Request timeout');

    vi.useRealTimers();
  });

  it('should pass AbortSignal to fetch', async () => {
    mockFetchSuccess({ workflows: [], total: 0, has_more: false });

    await api.getWorkflows();

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/workflows/active',
      expect.objectContaining({
        signal: expect.any(AbortSignal),
      })
    );
  });
});
```

### Step 2.2: Run test to verify it fails

Run: `cd dashboard && pnpm test -- src/api/__tests__/client.test.ts --run`
Expected: FAIL - fetch not called with signal, timeout not implemented

### Step 2.3: Implement timeout wrapper in API client

```typescript
// In dashboard/src/api/client.ts, add after line 19 (after API_BASE_URL)

/**
 * Default timeout for API requests in milliseconds (30 seconds).
 */
const DEFAULT_TIMEOUT_MS = 30000;

/**
 * Creates an AbortSignal that triggers after the specified timeout.
 *
 * @param timeoutMs - Timeout duration in milliseconds.
 * @returns An AbortSignal that will abort after the timeout.
 */
function createTimeoutSignal(timeoutMs: number = DEFAULT_TIMEOUT_MS): AbortSignal {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), timeoutMs);
  return controller.signal;
}

/**
 * Wraps fetch with timeout support.
 *
 * @param url - The URL to fetch.
 * @param options - Fetch options (method, headers, body, etc.).
 * @returns The fetch Response.
 * @throws {ApiError} When the request times out or fails.
 */
async function fetchWithTimeout(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const signal = createTimeoutSignal();

  try {
    return await fetch(url, { ...options, signal });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new ApiError('Request timeout', 'TIMEOUT', 408);
    }
    throw error;
  }
}
```

### Step 2.4: Update all fetch calls to use fetchWithTimeout

Replace all `fetch(` with `fetchWithTimeout(` in the api object methods:

```typescript
// Line 115 (getWorkflows)
const response = await fetchWithTimeout(`${API_BASE_URL}/workflows/active`);

// Line 137 (getWorkflow)
const response = await fetchWithTimeout(`${API_BASE_URL}/workflows/${id}`);

// Line 158-161 (approveWorkflow)
const response = await fetchWithTimeout(`${API_BASE_URL}/workflows/${id}/approve`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
});

// Line 183-187 (rejectWorkflow)
const response = await fetchWithTimeout(`${API_BASE_URL}/workflows/${id}/reject`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ feedback }),
});

// Line 208-211 (cancelWorkflow)
const response = await fetchWithTimeout(`${API_BASE_URL}/workflows/${id}/cancel`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
});

// Line 236 (inside getWorkflowHistory map)
const response = await fetchWithTimeout(`${API_BASE_URL}/workflows?status=${status}`);

// Line 268 (getPrompts)
const response = await fetchWithTimeout(`${API_BASE_URL}/prompts`);

// Line 287 (getPrompt)
const response = await fetchWithTimeout(`${API_BASE_URL}/prompts/${id}`);

// Line 305 (getPromptVersions)
const response = await fetchWithTimeout(`${API_BASE_URL}/prompts/${promptId}/versions`);

// Line 328-330 (getPromptVersion)
const response = await fetchWithTimeout(
  `${API_BASE_URL}/prompts/${promptId}/versions/${versionId}`
);

// Line 358-362 (createPromptVersion)
const response = await fetchWithTimeout(`${API_BASE_URL}/prompts/${promptId}/versions`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ content, change_note: changeNote }),
});

// Line 380-383 (resetPromptToDefault)
const response = await fetchWithTimeout(`${API_BASE_URL}/prompts/${promptId}/reset`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
});

// Line 401 (getPromptDefault)
const response = await fetchWithTimeout(`${API_BASE_URL}/prompts/${promptId}/default`);
```

### Step 2.5: Run test to verify it passes

Run: `cd dashboard && pnpm test -- src/api/__tests__/client.test.ts --run`
Expected: PASS

### Step 2.6: Run all API client tests

Run: `cd dashboard && pnpm test -- src/api/__tests__/ --run`
Expected: All tests pass

### Step 2.7: Commit

```bash
git add dashboard/src/api/client.ts dashboard/src/api/__tests__/client.test.ts
git commit -m "$(cat <<'EOF'
fix(dashboard): add 30-second timeout to API requests

Prevents infinite loading state when backend is slow or unresponsive.
All fetch calls now use fetchWithTimeout() which throws ApiError
with code 'TIMEOUT' after 30 seconds.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Batch Frontend Store Updates

**Files:**
- Modify: `dashboard/src/store/workflowStore.ts`
- Test: `dashboard/src/store/__tests__/workflowStore.test.ts`

### Step 3.1: Write failing test for batched event processing

```typescript
// Add to dashboard/src/store/__tests__/workflowStore.test.ts

describe('batched event processing', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should batch multiple events into single state update', () => {
    const store = useWorkflowStore.getState();
    const setStateSpy = vi.spyOn(useWorkflowStore, 'setState');

    // Add 100 events rapidly
    for (let i = 0; i < 100; i++) {
      store.addEvent({
        id: `evt-${i}`,
        workflow_id: 'wf-1',
        sequence: i,
        timestamp: '2026-01-08T10:00:00Z',
        agent: 'system',
        event_type: 'stage_started',
        level: 'info',
        message: `Event ${i}`,
      });
    }

    // Before flush, state shouldn't have all events applied yet
    // (batching defers the actual state update)

    // Flush the batch
    vi.advanceTimersByTime(100);

    // After flush, all events should be in store
    const state = useWorkflowStore.getState();
    expect(state.eventsByWorkflow['wf-1']).toHaveLength(100);

    // setState should have been called much fewer times than 100
    // (batching reduces calls)
    expect(setStateSpy.mock.calls.length).toBeLessThan(10);
  });

  it('should flush batch immediately when reaching batch size limit', () => {
    const store = useWorkflowStore.getState();

    // Add events up to batch limit (50)
    for (let i = 0; i < 50; i++) {
      store.addEvent({
        id: `evt-${i}`,
        workflow_id: 'wf-1',
        sequence: i,
        timestamp: '2026-01-08T10:00:00Z',
        agent: 'system',
        event_type: 'stage_started',
        level: 'info',
        message: `Event ${i}`,
      });
    }

    // Should flush immediately without waiting for timer
    const state = useWorkflowStore.getState();
    expect(state.eventsByWorkflow['wf-1']).toHaveLength(50);
  });
});
```

### Step 3.2: Run test to verify it fails

Run: `cd dashboard && pnpm test -- src/store/__tests__/workflowStore.test.ts --run`
Expected: FAIL - Current implementation updates state on every addEvent call

### Step 3.3: Implement batched event processing

```typescript
// Replace dashboard/src/store/workflowStore.ts entirely

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { WorkflowEvent } from '../types';

/**
 * Maximum number of events to retain per workflow in the store.
 */
const MAX_EVENTS_PER_WORKFLOW = 500;

/**
 * Batch configuration for event processing.
 */
const BATCH_FLUSH_INTERVAL_MS = 100;
const BATCH_SIZE_LIMIT = 50;

/**
 * Pending events waiting to be flushed to state.
 */
let pendingEvents: WorkflowEvent[] = [];
let flushTimeoutId: ReturnType<typeof setTimeout> | null = null;

/**
 * Zustand store state for real-time WebSocket events and connection state.
 */
interface WorkflowState {
  eventsByWorkflow: Record<string, WorkflowEvent[]>;
  eventIdsByWorkflow: Record<string, Set<string>>;
  lastEventId: string | null;
  isConnected: boolean;
  connectionError: string | null;
  pendingActions: string[];
  addEvent: (event: WorkflowEvent) => void;
  setLastEventId: (id: string | null) => void;
  setConnected: (connected: boolean, error?: string) => void;
  addPendingAction: (actionId: string) => void;
  removePendingAction: (actionId: string) => void;
}

/**
 * Apply a batch of events to the current state.
 * This is the core logic extracted for batching.
 */
function applyEventBatch(
  state: WorkflowState,
  events: WorkflowEvent[]
): Partial<WorkflowState> {
  if (events.length === 0) return {};

  const newEventsByWorkflow = { ...state.eventsByWorkflow };
  const newEventIdsByWorkflow = { ...state.eventIdsByWorkflow };
  let lastEventId = state.lastEventId;

  for (const event of events) {
    const workflowId = event.workflow_id;
    const existingIds = newEventIdsByWorkflow[workflowId] ?? new Set<string>();

    // Skip duplicates
    if (existingIds.has(event.id)) {
      continue;
    }

    const existing = newEventsByWorkflow[workflowId] ?? [];
    const updated = [...existing, event];

    // Trim if needed
    const needsTrim = updated.length > MAX_EVENTS_PER_WORKFLOW;
    const trimmed = needsTrim
      ? updated.slice(-MAX_EVENTS_PER_WORKFLOW)
      : updated;

    // Update IDs set
    const newIds = needsTrim
      ? new Set(trimmed.map((e) => e.id))
      : new Set(existingIds).add(event.id);

    newEventsByWorkflow[workflowId] = trimmed;
    newEventIdsByWorkflow[workflowId] = newIds;
    lastEventId = event.id;
  }

  return {
    eventsByWorkflow: newEventsByWorkflow,
    eventIdsByWorkflow: newEventIdsByWorkflow,
    lastEventId,
  };
}

/**
 * Flush pending events to state.
 */
function flushPendingEvents(): void {
  if (pendingEvents.length === 0) return;

  const eventsToFlush = pendingEvents;
  pendingEvents = [];

  if (flushTimeoutId !== null) {
    clearTimeout(flushTimeoutId);
    flushTimeoutId = null;
  }

  useWorkflowStore.setState((state) => applyEventBatch(state, eventsToFlush));
}

/**
 * Schedule a flush if not already scheduled.
 */
function scheduleFlush(): void {
  if (flushTimeoutId === null) {
    flushTimeoutId = setTimeout(flushPendingEvents, BATCH_FLUSH_INTERVAL_MS);
  }
}

export const useWorkflowStore = create<WorkflowState>()(
  persist(
    (set) => ({
      eventsByWorkflow: {},
      eventIdsByWorkflow: {},
      lastEventId: null,
      isConnected: false,
      connectionError: null,
      pendingActions: [],

      addEvent: (event) => {
        pendingEvents.push(event);

        // Flush immediately if batch is full
        if (pendingEvents.length >= BATCH_SIZE_LIMIT) {
          flushPendingEvents();
        } else {
          scheduleFlush();
        }
      },

      setLastEventId: (id) => set({ lastEventId: id }),

      setConnected: (connected, error) =>
        set({
          isConnected: connected,
          connectionError: connected ? null : (error ?? null),
        }),

      addPendingAction: (actionId) =>
        set((state) => {
          if (state.pendingActions.includes(actionId)) {
            return state;
          }
          return {
            pendingActions: [...state.pendingActions, actionId],
          };
        }),

      removePendingAction: (actionId) =>
        set((state) => ({
          pendingActions: state.pendingActions.filter((id) => id !== actionId),
        })),
    }),
    {
      name: 'amelia-workflow-state',
      storage: {
        getItem: (name) => {
          const value = sessionStorage.getItem(name);
          return value ? JSON.parse(value) : null;
        },
        setItem: (name, value) => {
          sessionStorage.setItem(name, JSON.stringify(value));
        },
        removeItem: (name) => {
          sessionStorage.removeItem(name);
        },
      },
      partialize: (state) => ({
        lastEventId: state.lastEventId,
      }) as unknown as WorkflowState,
    }
  )
);
```

### Step 3.4: Run test to verify it passes

Run: `cd dashboard && pnpm test -- src/store/__tests__/workflowStore.test.ts --run`
Expected: PASS

### Step 3.5: Run all store tests

Run: `cd dashboard && pnpm test -- src/store/ --run`
Expected: All tests pass

### Step 3.6: Run all frontend tests to check for regressions

Run: `cd dashboard && pnpm test --run`
Expected: All tests pass

### Step 3.7: Commit

```bash
git add dashboard/src/store/workflowStore.ts dashboard/src/store/__tests__/workflowStore.test.ts
git commit -m "$(cat <<'EOF'
perf(dashboard): batch event store updates to reduce re-renders

Events are now batched and flushed every 100ms or when 50 events
accumulate, whichever comes first. This reduces React re-renders
and GC pressure when processing high-volume event streams.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add Loading Timeout UI Feedback

**Files:**
- Create: `dashboard/src/components/LoadingTimeout.tsx`
- Modify: `dashboard/src/components/GlobalLoadingSpinner.tsx`
- Test: `dashboard/src/components/__tests__/LoadingTimeout.test.tsx`

### Step 4.1: Write failing test for loading timeout component

```typescript
// Create dashboard/src/components/__tests__/LoadingTimeout.test.tsx

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LoadingTimeout } from '../LoadingTimeout';

describe('LoadingTimeout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should show loading spinner initially', () => {
    render(<LoadingTimeout />);

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByText(/taking longer/i)).not.toBeInTheDocument();
  });

  it('should show timeout message after 10 seconds', () => {
    render(<LoadingTimeout />);

    vi.advanceTimersByTime(10001);

    expect(screen.getByText(/taking longer than expected/i)).toBeInTheDocument();
  });

  it('should show connection hint after 30 seconds', () => {
    render(<LoadingTimeout />);

    vi.advanceTimersByTime(30001);

    expect(screen.getByText(/check your connection/i)).toBeInTheDocument();
  });
});
```

### Step 4.2: Run test to verify it fails

Run: `cd dashboard && pnpm test -- src/components/__tests__/LoadingTimeout.test.tsx --run`
Expected: FAIL - Component doesn't exist

### Step 4.3: Implement LoadingTimeout component

```typescript
// Create dashboard/src/components/LoadingTimeout.tsx

import { useState, useEffect } from 'react';
import { Loader2, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Time thresholds for loading feedback messages (in milliseconds).
 */
const SLOW_THRESHOLD_MS = 10000;
const VERY_SLOW_THRESHOLD_MS = 30000;

/**
 * Loading spinner with progressive timeout feedback.
 *
 * Shows a standard spinner initially, then displays helpful messages
 * if loading takes longer than expected:
 * - After 10s: "Taking longer than expected..."
 * - After 30s: "Check your connection or try refreshing"
 *
 * @param props - Component props
 * @param props.className - Optional additional CSS classes
 * @returns React element with spinner and optional timeout messages
 */
export function LoadingTimeout({ className }: { className?: string }) {
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    const startTime = Date.now();
    const interval = setInterval(() => {
      setElapsedMs(Date.now() - startTime);
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  const isSlow = elapsedMs > SLOW_THRESHOLD_MS;
  const isVerySlow = elapsedMs > VERY_SLOW_THRESHOLD_MS;

  return (
    <div
      role="status"
      className={cn(
        'flex flex-col items-center justify-center gap-4',
        className
      )}
    >
      <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />

      {isSlow && !isVerySlow && (
        <p className="text-sm text-muted-foreground animate-in fade-in">
          Taking longer than expected...
        </p>
      )}

      {isVerySlow && (
        <div className="flex flex-col items-center gap-2 animate-in fade-in">
          <div className="flex items-center gap-2 text-yellow-500">
            <AlertCircle className="w-4 h-4" />
            <span className="text-sm font-medium">
              Taking longer than expected...
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Check your connection or try refreshing the page
          </p>
        </div>
      )}

      <span className="sr-only">Loading</span>
    </div>
  );
}
```

### Step 4.4: Run test to verify it passes

Run: `cd dashboard && pnpm test -- src/components/__tests__/LoadingTimeout.test.tsx --run`
Expected: PASS

### Step 4.5: Update GlobalLoadingSpinner to use LoadingTimeout

First, find the GlobalLoadingSpinner:

```bash
grep -r "GlobalLoadingSpinner" dashboard/src --include="*.tsx"
```

Then update it to use LoadingTimeout (implementation depends on current structure).

### Step 4.6: Run all component tests

Run: `cd dashboard && pnpm test -- src/components/ --run`
Expected: All tests pass

### Step 4.7: Commit

```bash
git add dashboard/src/components/LoadingTimeout.tsx dashboard/src/components/__tests__/LoadingTimeout.test.tsx dashboard/src/components/GlobalLoadingSpinner.tsx
git commit -m "$(cat <<'EOF'
feat(dashboard): add progressive loading timeout feedback

Shows helpful messages when loading takes longer than expected:
- After 10s: "Taking longer than expected..."
- After 30s: "Check your connection or try refreshing"

Helps users understand when something is wrong vs just slow.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Clean Up Backend Approval Events

**Files:**
- Modify: `amelia/server/orchestrator/service.py`
- Test: `tests/unit/server/test_orchestrator_service.py`

### Step 5.1: Write failing test for approval event cleanup

```python
# Add to tests/unit/server/test_orchestrator_service.py (or create if needed)

async def test_approval_events_cleaned_on_workflow_complete() -> None:
    """Approval events dict should be cleaned when workflow completes."""
    # Setup orchestrator with mock dependencies
    orchestrator = OrchestratorService(...)

    # Start a workflow that will need approval
    workflow_id = "wf-test"
    orchestrator._approval_events[workflow_id] = asyncio.Event()

    # Simulate workflow completion
    await orchestrator._cleanup_workflow(workflow_id)

    # Approval event should be removed
    assert workflow_id not in orchestrator._approval_events
```

### Step 5.2: Run test to verify it fails

Run: `uv run pytest tests/unit/server/test_orchestrator_service.py::test_approval_events_cleaned_on_workflow_complete -v`
Expected: FAIL - `_cleanup_workflow` doesn't clean `_approval_events`

### Step 5.3: Add cleanup for approval events

Find the cleanup callback in `service.py` (around line 494-507) and add:

```python
# Add to the cleanup_task function or wherever workflow cleanup happens
self._approval_events.pop(workflow_id, None)
```

### Step 5.4: Run test to verify it passes

Run: `uv run pytest tests/unit/server/test_orchestrator_service.py::test_approval_events_cleaned_on_workflow_complete -v`
Expected: PASS

### Step 5.5: Run all orchestrator tests

Run: `uv run pytest tests/unit/server/ -k orchestrator -v`
Expected: All tests pass

### Step 5.6: Commit

```bash
git add amelia/server/orchestrator/service.py tests/unit/server/test_orchestrator_service.py
git commit -m "$(cat <<'EOF'
fix(backend): clean up approval events when workflow completes

Prevents memory leak from _approval_events dict accumulating entries
for completed workflows. Now properly cleaned in workflow cleanup.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Final Integration Verification

### Step 6.1: Run full backend test suite

Run: `uv run pytest tests/ -v`
Expected: All tests pass

### Step 6.2: Run full frontend test suite

Run: `cd dashboard && pnpm test --run`
Expected: All tests pass

### Step 6.3: Run type checks

Run: `uv run mypy amelia && cd dashboard && pnpm type-check`
Expected: No type errors

### Step 6.4: Run linting

Run: `uv run ruff check amelia tests && cd dashboard && pnpm lint`
Expected: No lint errors

### Step 6.5: Manual smoke test

1. Start the server: `uv run amelia dev`
2. Open dashboard at `http://localhost:8420`
3. Start a workflow with many tasks
4. Verify:
   - Logs page remains responsive
   - No infinite loading state
   - WebSocket reconnects cleanly after disconnect
   - Console shows batched event processing

### Step 6.6: Commit any fixes from integration testing

```bash
git add -A
git commit -m "$(cat <<'EOF'
test: integration verification for log performance fixes

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

| Task | Impact | Risk |
|------|--------|------|
| 1. Backend backfill pagination | Prevents OOM on reconnect | Low - additive change |
| 2. API request timeout | Fixes infinite loading | Low - graceful degradation |
| 3. Batched store updates | Reduces re-renders by 10x+ | Medium - timing-sensitive |
| 4. Loading timeout UI | Better UX feedback | Low - UI only |
| 5. Approval event cleanup | Prevents memory leak | Low - cleanup code |
