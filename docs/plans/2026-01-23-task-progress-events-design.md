# Task Progress Events Design

**Issue:** #246 - Display task progress in workflow detail view
**Date:** 2026-01-23
**Status:** Approved

## Summary

Add visibility into task-based execution progress by emitting task events that appear in the dashboard activity log.

## Background

PR #245 implemented task-based execution where each task in an Architect's plan runs in a fresh Developer session. The backend tracks task transitions internally, but the dashboard has no visibility into task progress.

## Design Decisions

### What We're Building

Task events emitted by the backend that flow through the existing activity log:

- `task_started`: "Starting Task 2/5: Implement authentication middleware"
- `task_completed`: "Completed Task 2/5"
- `task_failed`: "Task 2/5 failed after 5 review iterations"

### What We're NOT Building

- No header badge or separate progress indicator (activity log is sufficient)
- No API response changes (events carry all task info)
- No task grouping in activity log (events appear inline chronologically)

### Legacy Mode

When `total_tasks` is null (single-task legacy mode), no task events are emitted. The UI behaves exactly as before.

## Implementation

### Backend Changes

**File: `amelia/pipelines/implementation/nodes.py`**

1. **Emit `TASK_STARTED`** when entering a task:
   - Location: Developer node entry point, when `total_tasks` is set
   - Payload: `task_index`, `total_tasks`, `task_title` (extracted from plan)
   - Message format: "Starting Task {index+1}/{total}: {title}"

2. **Emit `TASK_COMPLETED`** when advancing to next task:
   - Location: `next_task_node` function
   - Payload: `task_index`, `total_tasks`
   - Message format: "Completed Task {index+1}/{total}"

3. **Emit `TASK_FAILED`** when max iterations reached:
   - Location: Routing logic when task exceeds max review iterations
   - Payload: `task_index`, `total_tasks`, `iterations`
   - Message format: "Task {index+1}/{total} failed after {iterations} review iterations"

**Event types already defined** in `amelia/server/models/events.py`:
- `TASK_STARTED = "task_started"`
- `TASK_COMPLETED = "task_completed"`
- `TASK_FAILED = "task_failed"`

### Frontend Changes

**None required.**

- Event types already defined in `dashboard/src/types/index.ts`
- Events flow through existing WebSocket → Zustand → ActivityLog pipeline
- Task events appear as timeline entries with their message text

## Testing

### Backend Tests

- Verify `TASK_STARTED` emitted when developer starts a task (task-based mode)
- Verify `TASK_COMPLETED` emitted when `next_task_node` advances
- Verify `TASK_FAILED` emitted when max iterations exceeded
- Verify no task events emitted in legacy mode (`total_tasks` is null)

### Manual Testing

- Run a multi-task workflow and observe task events in activity log
- Run a legacy single-task workflow and verify no task events appear
- Trigger a task failure and verify the failed event appears

## Files to Modify

| File | Change |
|------|--------|
| `amelia/pipelines/implementation/nodes.py` | Emit task events |
| `amelia/pipelines/implementation/routing.py` | Emit `TASK_FAILED` on max iterations |
| `tests/unit/pipelines/implementation/test_nodes.py` | Add task event tests |
