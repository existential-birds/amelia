# StreamEvent UUID Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a unique UUID `id` field to `StreamEvent` for stable React list rendering keys.

**Architecture:** Add auto-generated UUID field to both Python Pydantic model and TypeScript interface. Update React components to use `event.id` as key instead of composite timestamp/index keys.

**Tech Stack:** Python (Pydantic, uuid4), TypeScript, React

---

## Task 1: Add UUID Test for Python StreamEvent

**Files:**
- Modify: `tests/unit/core/test_stream_types.py`

**Step 1: Write the failing test**

Add to `TestStreamEvent` class in `tests/unit/core/test_stream_types.py`:

```python
def test_id_auto_generated(self) -> None:
    """StreamEvent should auto-generate a unique UUID id."""
    now = datetime.now(UTC)
    event1 = StreamEvent(
        type=StreamEventType.CLAUDE_THINKING,
        timestamp=now,
        agent="architect",
        workflow_id="workflow-123",
    )
    event2 = StreamEvent(
        type=StreamEventType.CLAUDE_THINKING,
        timestamp=now,
        agent="architect",
        workflow_id="workflow-123",
    )
    # Each event has an id
    assert event1.id is not None
    assert event2.id is not None
    # IDs are unique
    assert event1.id != event2.id
    # ID is a valid UUID string (36 chars with hyphens)
    assert len(event1.id) == 36
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_stream_types.py::TestStreamEvent::test_id_auto_generated -v`

Expected: FAIL with `AttributeError: 'StreamEvent' object has no attribute 'id'`

**Step 3: Commit failing test**

```bash
git add tests/unit/core/test_stream_types.py
git commit -m "test: add failing test for StreamEvent UUID id field"
```

---

## Task 2: Implement UUID Field in Python StreamEvent

**Files:**
- Modify: `amelia/core/types.py:137-155`

**Step 1: Add import and field**

Add to imports at top of `amelia/core/types.py`:
```python
from uuid import uuid4
```

Update `StreamEvent` class to add the `id` field as the first field:

```python
class StreamEvent(BaseModel):
    """Real-time streaming event from agent execution.

    Attributes:
        id: Unique identifier for this event.
        type: Type of streaming event.
        content: Event content (optional).
        timestamp: When the event occurred.
        agent: Agent name (architect, developer, reviewer).
        workflow_id: Unique workflow identifier.
        tool_name: Name of tool being called/returning (optional).
        tool_input: Input parameters for tool call (optional).
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: StreamEventType
    content: str | None = None
    timestamp: datetime
    agent: str
    workflow_id: str
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_stream_types.py::TestStreamEvent::test_id_auto_generated -v`

Expected: PASS

**Step 3: Run all StreamEvent tests**

Run: `uv run pytest tests/unit/core/test_stream_types.py -v`

Expected: All tests PASS

**Step 4: Commit**

```bash
git add amelia/core/types.py tests/unit/core/test_stream_types.py
git commit -m "feat: add auto-generated UUID id field to StreamEvent"
```

---

## Task 3: Update TypeScript StreamEvent Interface

**Files:**
- Modify: `dashboard/src/types/index.ts:545-566`

**Step 1: Add id field to StreamEvent interface**

Update the `StreamEvent` interface:

```typescript
export interface StreamEvent {
  /** Unique identifier for this event (UUID). */
  id: string;

  /** Subtype of stream event (uses subtype to avoid collision with message type). */
  subtype: StreamEventType;

  /** Text content for thinking/output events, null for tool calls. */
  content: string | null;

  /** ISO 8601 timestamp when the event was emitted. */
  timestamp: string;

  /** Name of the agent that emitted this event (e.g., 'architect', 'developer'). */
  agent: string;

  /** ID of the workflow this event belongs to. */
  workflow_id: string;

  /** Name of the tool being called, null for non-tool events. */
  tool_name: string | null;

  /** Input parameters for the tool call, null for non-tool events. */
  tool_input: Record<string, unknown> | null;
}
```

**Step 2: Run TypeScript type check**

Run: `cd dashboard && pnpm type-check`

Expected: Type errors in fixtures and components that don't provide `id`

**Step 3: Commit (with type errors - will fix next)**

```bash
git add dashboard/src/types/index.ts
git commit -m "feat: add id field to TypeScript StreamEvent interface"
```

---

## Task 4: Update Test Fixtures

**Files:**
- Modify: `dashboard/src/__tests__/fixtures.ts:94-107`

**Step 1: Update createMockStreamEvent factory**

```typescript
/**
 * Creates a mock StreamEvent with sensible defaults.
 * Uses `subtype` (not `type`) to match the WebSocket payload format.
 * @param overrides - Optional partial object to override default values
 */
export function createMockStreamEvent(
  overrides?: Partial<StreamEvent>
): StreamEvent {
  return {
    id: `stream-${crypto.randomUUID()}`,
    subtype: StreamEventType.CLAUDE_THINKING,
    content: 'Test thinking content',
    timestamp: '2025-12-13T10:00:00Z',
    agent: 'architect',
    workflow_id: 'wf-test-123',
    tool_name: null,
    tool_input: null,
    ...overrides,
  };
}
```

**Step 2: Run type check**

Run: `cd dashboard && pnpm type-check`

Expected: Still some errors in components (will fix next)

**Step 3: Run fixture-related tests**

Run: `cd dashboard && pnpm test:run`

Expected: Some tests may fail due to missing `id` in inline fixtures

**Step 4: Commit**

```bash
git add dashboard/src/__tests__/fixtures.ts
git commit -m "fix: add id field to createMockStreamEvent fixture"
```

---

## Task 5: Update LogsPage Component Key

**Files:**
- Modify: `dashboard/src/pages/LogsPage.tsx:185`

**Step 1: Update key to use event.id**

Change line 185 from:
```tsx
key={`${event.workflow_id}-${event.timestamp}-${index}`}
```

To:
```tsx
key={event.id}
```

**Step 2: Run type check**

Run: `cd dashboard && pnpm type-check`

Expected: PASS (or remaining errors from other files)

**Step 3: Commit**

```bash
git add dashboard/src/pages/LogsPage.tsx
git commit -m "refactor: use event.id as React key in LogsPage"
```

---

## Task 6: Update ActivityLog Component Key

**Files:**
- Modify: `dashboard/src/components/ActivityLog.tsx:182`

**Step 1: Update key to use event.id**

Change line 182 from:
```tsx
<StreamLogEntry key={`stream-${entry.event.timestamp}-${index}`} event={entry.event} />
```

To:
```tsx
<StreamLogEntry key={entry.event.id} event={entry.event} />
```

**Step 2: Run type check**

Run: `cd dashboard && pnpm type-check`

Expected: PASS

**Step 3: Commit**

```bash
git add dashboard/src/components/ActivityLog.tsx
git commit -m "refactor: use event.id as React key in ActivityLog"
```

---

## Task 7: Fix Any Remaining Test Fixtures

**Files:**
- May need to update inline fixtures in test files

**Step 1: Run all frontend tests**

Run: `cd dashboard && pnpm test:run`

**Step 2: Fix any failures**

If tests fail due to missing `id` in inline `StreamEvent` objects, add `id: 'test-id-N'` to each.

Check these files if they have inline StreamEvent objects:
- `dashboard/src/hooks/__tests__/useWebSocket.test.tsx`
- `dashboard/src/pages/__tests__/LogsPage.test.tsx`
- `dashboard/src/store/__tests__/stream-store.test.ts`
- `dashboard/src/components/ActivityLog.test.tsx`

**Step 3: Verify all tests pass**

Run: `cd dashboard && pnpm test:run`

Expected: All PASS

**Step 4: Commit fixes**

```bash
git add -A
git commit -m "fix: add id field to all StreamEvent test fixtures"
```

---

## Task 8: Run Full Validation

**Step 1: Run Python tests**

Run: `uv run pytest tests/unit/core/test_stream_types.py -v`

Expected: All PASS

**Step 2: Run frontend lint and type check**

Run: `cd dashboard && pnpm lint && pnpm type-check`

Expected: No errors

**Step 3: Run frontend tests**

Run: `cd dashboard && pnpm test:run`

Expected: All PASS

**Step 4: Run Python lint and type check**

Run: `uv run ruff check amelia && uv run mypy amelia`

Expected: No errors

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Write failing test for UUID | `tests/unit/core/test_stream_types.py` |
| 2 | Implement UUID in Python | `amelia/core/types.py` |
| 3 | Add id to TS interface | `dashboard/src/types/index.ts` |
| 4 | Update test fixtures | `dashboard/src/__tests__/fixtures.ts` |
| 5 | Update LogsPage key | `dashboard/src/pages/LogsPage.tsx` |
| 6 | Update ActivityLog key | `dashboard/src/components/ActivityLog.tsx` |
| 7 | Fix remaining test fixtures | Various test files |
| 8 | Full validation | N/A |
