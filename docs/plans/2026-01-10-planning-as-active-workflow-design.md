# Planning Status for Workflow State Machine

**Issue:** #266 - Start button enabled during Architect planning phase
**Date:** 2026-01-10
**Status:** Approved

## Problem

When using Quick Shot with `plan_now=True`, the Architect runs in the background but the workflow stays in `pending` status. This creates a hidden state problem:

1. Backend tracks planning in `_planning_tasks[workflow_id]` (shadow state)
2. Workflow status remains `pending`
3. Frontend shows Start button as enabled
4. User could click Start while Architect is already running

## Solution

Introduce a new `planning` status to make the Architect phase visible in the state machine.

### State Machine

**Before (broken):**
```
pending (Architect in _planning_tasks - HIDDEN) → pending (plan ready) → in_progress
```

**After (fixed):**
```
pending → planning → blocked → in_progress → completed
           ↑           ↑            ↑
     (plan_now=true)  (plan ready) (execution starts, worktree blocked)
```

### Status Definitions

| Status | Meaning | Worktree Blocked? |
|--------|---------|-------------------|
| `pending` | Queued, waiting to start | No |
| `planning` | Architect generating plan | No |
| `blocked` | Plan ready, awaiting approval | No |
| `in_progress` | Execution running (Developer/Reviewer) | **Yes** |
| `completed` | Finished successfully | No |
| `failed` | Error occurred | No |
| `cancelled` | Explicitly cancelled | No |

**Key insight:** Planning is read-only (Architect analyzes codebase), so it doesn't need to block the worktree. This enables future concurrent planning (#268).

## Implementation

### 1. Backend: State Model (`amelia/server/models/state.py`)

Add `"planning"` to `WorkflowStatus`:
```python
WorkflowStatus = Literal[
    "pending",
    "planning",  # NEW
    "in_progress",
    "blocked",
    "completed",
    "failed",
    "cancelled",
]
```

Update `VALID_TRANSITIONS`:
```python
VALID_TRANSITIONS = {
    "pending": {"planning", "in_progress", "cancelled", "failed"},
    "planning": {"blocked", "failed", "cancelled"},  # NEW
    "in_progress": {"blocked", "completed", "failed", "cancelled"},
    "blocked": {"in_progress", "failed", "cancelled"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}
```

### 2. Backend: Orchestrator Service (`amelia/server/orchestrator/service.py`)

**`queue_and_plan_workflow`:**
- Set `workflow_status = "planning"` (not `pending`)
- Set `current_stage = "architect"`
- Keep workflow in `_planning_tasks` (not `_active_tasks`)

**`_run_planning_task`:**
- On success: transition `planning → blocked`, emit `APPROVAL_REQUIRED`
- On failure: transition `planning → failed`
- On cancel: transition `planning → cancelled`

### 3. Frontend: Workflow Controls

**`WorkflowsPage.tsx`:**
- Show `PendingWorkflowControls` only when `status === 'pending'`
- Show new `PlanningIndicator` when `status === 'planning'`
- Show `ApprovalControls` when `status === 'blocked'`

**`PendingWorkflowControls.tsx`:**
- No changes needed (only shown for `pending` status)

**`worktreeHasActiveWorkflow` check:**
- Remains `status === 'in_progress'` (only execution blocks worktree)

### 4. New Component: Planning Indicator

Simple component showing "Planning in progress..." with spinner:
- Read-only display (no actions)
- Shows elapsed time since planning started
- Cancel button to abort planning

## Benefits

1. **Visible state:** Planning phase is explicit in status, not hidden in `_planning_tasks`
2. **Start button disabled:** Frontend sees `status !== 'pending'`, disables Start
3. **Non-blocking:** Planning doesn't block worktree, enabling future concurrent planning (#268)
4. **Clean path to #268:** No refactoring needed for non-blocking plan generation

## Test Cases

1. Quick Shot with `plan_now=true` → status transitions to `planning`
2. Start button disabled when status is `planning`
3. Worktree NOT blocked during planning (another workflow can execute)
4. Planning success → status transitions to `blocked`
5. Planning failure → status transitions to `failed`
6. Cancel during planning → status transitions to `cancelled`

## Future: #268 Compatibility

This design explicitly supports #268 (non-blocking plan generation):

- Multiple workflows can be in `planning` status on the same worktree
- Only `in_progress` status blocks the worktree
- Plan re-runs: transition `blocked → planning` when user requests replan
