# Planning Status Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add explicit `planning` status to workflow state machine so the frontend can distinguish between queued and actively-planning workflows.

**Architecture:** Introduce `planning` as a new status value in both backend (Python) and frontend (TypeScript). The `queue_and_plan_workflow` method transitions to `planning` immediately, then to `blocked` on success. The frontend shows `PlanningIndicator` for `planning` status instead of `PendingWorkflowControls`.

**Tech Stack:** Python/Pydantic (backend state model), TypeScript/React (frontend types + components), pytest + vitest (tests)

---

### Task 1: Backend - Add `planning` to WorkflowStatus

**Files:**
- Modify: `amelia/server/models/state.py:12-30`
- Test: `tests/unit/server/models/test_state.py`

**Step 1: Write the failing tests**

Add tests for the new `planning` status transitions in `tests/unit/server/models/test_state.py`:

```python
# Add to TestStateTransitions class, inside the valid_transitions parametrize list
("pending", "planning"),
("planning", "blocked"),
("planning", "failed"),
("planning", "cancelled"),
```

```python
# Add to TestStateTransitions class, inside the invalid_transitions parametrize list
("planning", "pending"),
("planning", "completed"),
("planning", "in_progress"),
```

```python
# Update the terminal_states_cannot_transition test's all_states list to include "planning"
all_states: list[WorkflowStatus] = [
    "pending",
    "planning",
    "in_progress",
    "blocked",
    "completed",
    "failed",
    "cancelled",
]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/models/test_state.py -v -k "test_valid_transitions or test_invalid_transitions or test_terminal"`
Expected: FAIL with KeyError or assertion errors for `planning` status

**Step 3: Implement the changes**

In `amelia/server/models/state.py`, update `WorkflowStatus`:

```python
WorkflowStatus = Literal[
    "pending",  # Not yet started
    "planning",  # Architect generating plan (NEW)
    "in_progress",  # Currently executing
    "blocked",  # Awaiting human approval
    "completed",  # Successfully finished
    "failed",  # Error occurred
    "cancelled",  # Explicitly cancelled
]
```

Update `VALID_TRANSITIONS`:

```python
VALID_TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    "pending": {"planning", "in_progress", "cancelled", "failed"},
    "planning": {"blocked", "failed", "cancelled"},  # NEW
    "in_progress": {"blocked", "completed", "failed", "cancelled"},
    "blocked": {"in_progress", "failed", "cancelled"},
    "completed": set(),  # Terminal state
    "failed": set(),  # Terminal state
    "cancelled": set(),  # Terminal state
}
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/models/test_state.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/models/state.py tests/unit/server/models/test_state.py
git commit -m "$(cat <<'EOF'
feat(state): add planning status to workflow state machine

Introduces `planning` as an explicit status for workflows that are
actively running the Architect agent. This makes the planning phase
visible in the state machine rather than hidden in _planning_tasks.

Closes #266

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Backend - Update orchestrator to use planning status

**Files:**
- Modify: `amelia/server/orchestrator/service.py:2203-2278` (queue_and_plan_workflow)
- Modify: `amelia/server/orchestrator/service.py:2085-2201` (_run_planning_task)
- Modify: `amelia/server/orchestrator/service.py:806` (cancel_workflow cancellable_states)
- Test: `tests/unit/server/orchestrator/test_queue_and_plan.py`

**Step 1: Write the failing tests**

Update existing tests in `tests/unit/server/orchestrator/test_queue_and_plan.py`:

```python
# In test_queue_and_plan_runs_architect, update assertion:
# Change: assert updated_state.workflow_status == "pending"
# To:
assert updated_state.workflow_status == "blocked"

# In test_queue_and_plan_stays_pending, rename to test_queue_and_plan_transitions_to_blocked
# and update the assertion:
# The test verifies workflow transitions properly - it should end up blocked after planning
```

Add new test:

```python
@pytest.mark.asyncio
async def test_queue_and_plan_sets_planning_status_immediately(
    self,
    orchestrator: OrchestratorService,
    mock_repository: MagicMock,
    valid_worktree: str,
) -> None:
    """Workflow status is 'planning' immediately after queue_and_plan_workflow."""
    request = CreateWorkflowRequest(
        issue_id="ISSUE-123",
        worktree_path=valid_worktree,
        start=False,
        plan_now=True,
    )

    # Use an event to block planning indefinitely
    planning_started = asyncio.Event()

    mock_architect = MagicMock()

    async def blocking_plan_gen(*args, **kwargs):
        """Mock async generator that blocks forever."""
        planning_started.set()
        await asyncio.sleep(1000)  # Block indefinitely
        yield None, None

    mock_architect.plan = blocking_plan_gen

    with patch.object(
        orchestrator, "_create_architect_for_planning", return_value=mock_architect
    ):
        workflow_id = await orchestrator.queue_and_plan_workflow(request)

        # Wait for planning to start
        await asyncio.wait_for(planning_started.wait(), timeout=1.0)

        # Check the created state has planning status
        created_state = mock_repository.create.call_args[0][0]
        assert created_state.workflow_status == "planning"
        assert created_state.current_stage == "architect"

        # Cancel the background task
        if workflow_id in orchestrator._planning_tasks:
            orchestrator._planning_tasks[workflow_id].cancel()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/orchestrator/test_queue_and_plan.py -v`
Expected: FAIL because current code sets `pending` status

**Step 3: Implement the changes**

In `amelia/server/orchestrator/service.py`, update `queue_and_plan_workflow`:

```python
# Around line 2239, change:
# workflow_status="pending",
# To:
workflow_status="planning",
current_stage="architect",
```

Update `_run_planning_task` success path (around line 2143):

```python
# After: fresh.planned_at = datetime.now(UTC)
# Add:
fresh.workflow_status = "blocked"
fresh.current_stage = None  # Clear stage, waiting for approval
```

Update `_run_planning_task` status check (around line 2134):

```python
# Change: if fresh.workflow_status != "pending":
# To:
if fresh.workflow_status != "planning":
```

Update `_run_planning_task` failure handling (around line 2179):

```python
# Change: if fresh is not None and fresh.workflow_status == "pending":
# To:
if fresh is not None and fresh.workflow_status == "planning":
```

Update `cancel_workflow` cancellable_states (around line 806):

```python
# Change: cancellable_states = {"pending", "in_progress", "blocked"}
# To:
cancellable_states = {"pending", "planning", "in_progress", "blocked"}
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/orchestrator/test_queue_and_plan.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/orchestrator/service.py tests/unit/server/orchestrator/test_queue_and_plan.py
git commit -m "$(cat <<'EOF'
feat(orchestrator): use planning status during architect phase

queue_and_plan_workflow now sets status to 'planning' immediately
and transitions to 'blocked' when the plan is ready. This makes the
planning phase visible in the workflow status instead of hidden.

Also updates cancel_workflow to allow cancelling workflows in
'planning' status.

Closes #266

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Frontend - Add `planning` to WorkflowStatus type

**Files:**
- Modify: `dashboard/src/types/index.ts:25-31`
- Test: `dashboard/src/types/__tests__/index.test.ts` (if exists, otherwise skip)

**Step 1: Write the type update**

In `dashboard/src/types/index.ts`, update `WorkflowStatus`:

```typescript
export type WorkflowStatus =
  | 'pending'
  | 'planning'  // NEW: Architect generating plan
  | 'in_progress'
  | 'blocked'
  | 'completed'
  | 'failed'
  | 'cancelled';
```

**Step 2: Run type check to verify**

Run: `cd dashboard && pnpm type-check`
Expected: May show errors in components that need updating (StatusBadge, etc.)

**Step 3: Commit**

```bash
git add dashboard/src/types/index.ts
git commit -m "$(cat <<'EOF'
feat(dashboard): add planning status type

Adds 'planning' to WorkflowStatus type to match backend changes.
Components will be updated in subsequent commits.

Closes #266

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Frontend - Update StatusBadge for planning status

**Files:**
- Modify: `dashboard/src/components/StatusBadge.tsx:13-59`
- Test: `dashboard/src/components/StatusBadge.test.tsx`

**Step 1: Write the failing test**

Add to `dashboard/src/components/StatusBadge.test.tsx`:

```typescript
it('renders PLANNING for planning status', () => {
  render(<StatusBadge status="planning" />);
  expect(screen.getByText('PLANNING')).toBeInTheDocument();
});

it('has correct data-status attribute for planning', () => {
  render(<StatusBadge status="planning" />);
  const badge = screen.getByRole('status');
  expect(badge).toHaveAttribute('data-status', 'planning');
});
```

**Step 2: Run tests to verify they fail**

Run: `cd dashboard && pnpm test -- StatusBadge.test.tsx`
Expected: FAIL with missing 'PLANNING' text

**Step 3: Implement the changes**

In `dashboard/src/components/StatusBadge.tsx`:

Add to `statusBadgeVariants` variants.status:
```typescript
planning: 'bg-status-pending/20 text-status-pending border border-status-pending/30 animate-pulse',
```

Add to `statusLabels`:
```typescript
planning: 'PLANNING',
```

Update `IndicatorStatus` type:
```typescript
type IndicatorStatus = 'pending' | 'planning' | 'running' | 'completed' | 'failed' | 'blocked' | 'cancelled';
```

Add to `statusMapping`:
```typescript
planning: 'planning',
```

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm test -- StatusBadge.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/StatusBadge.tsx dashboard/src/components/StatusBadge.test.tsx
git commit -m "$(cat <<'EOF'
feat(dashboard): add planning status to StatusBadge

Shows 'PLANNING' badge with pulsing animation for workflows
in the planning status. Uses the pending color scheme.

Closes #266

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Frontend - Create PlanningIndicator component

**Files:**
- Create: `dashboard/src/components/PlanningIndicator.tsx`
- Create: `dashboard/src/components/PlanningIndicator.test.tsx`

**Step 1: Write the failing test**

Create `dashboard/src/components/PlanningIndicator.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlanningIndicator } from './PlanningIndicator';

// Mock the api client
vi.mock('@/api/client', () => ({
  api: {
    cancelWorkflow: vi.fn().mockResolvedValue(undefined),
  },
}));

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  useRevalidator: () => ({ revalidate: vi.fn() }),
}));

describe('PlanningIndicator', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders planning in progress message', () => {
    render(<PlanningIndicator workflowId="wf-123" />);
    expect(screen.getByText('PLANNING')).toBeInTheDocument();
    expect(screen.getByText(/Architect is analyzing/)).toBeInTheDocument();
  });

  it('shows elapsed time', () => {
    const startedAt = new Date(Date.now() - 30000).toISOString(); // 30 seconds ago
    render(<PlanningIndicator workflowId="wf-123" startedAt={startedAt} />);
    expect(screen.getByText(/30s/)).toBeInTheDocument();
  });

  it('has cancel button', () => {
    render(<PlanningIndicator workflowId="wf-123" />);
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
  });

  it('calls cancel API when cancel button clicked', async () => {
    const { api } = await import('@/api/client');
    render(<PlanningIndicator workflowId="wf-123" />);

    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    fireEvent.click(cancelButton);

    expect(api.cancelWorkflow).toHaveBeenCalledWith('wf-123');
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd dashboard && pnpm test -- PlanningIndicator.test.tsx`
Expected: FAIL because component doesn't exist

**Step 3: Implement the component**

Create `dashboard/src/components/PlanningIndicator.tsx`:

```typescript
/**
 * @fileoverview Indicator component for workflows in planning status.
 *
 * Shows that the Architect is actively generating a plan, with
 * elapsed time and a cancel button.
 */
import { useState, useCallback, useEffect } from 'react';
import { useRevalidator } from 'react-router-dom';
import { Brain, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Loader } from '@/components/ai-elements/loader';
import { success, error as toastError } from '@/components/Toast';
import { api } from '@/api/client';
import { cn } from '@/lib/utils';

/**
 * Props for the PlanningIndicator component.
 */
interface PlanningIndicatorProps {
  workflowId: string;
  startedAt?: string | null;
  className?: string;
}

/**
 * Formats elapsed seconds as "Xs", "Xm Ys", or "Xh Ym".
 */
function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (minutes < 60) return `${minutes}m ${secs}s`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hours}h ${mins}m`;
}

/**
 * Displays planning status for workflows where Architect is generating a plan.
 *
 * Shows:
 * - "PLANNING" header with brain icon
 * - Explanation that Architect is analyzing codebase
 * - Elapsed time since planning started
 * - Cancel button to abort planning
 */
export function PlanningIndicator({
  workflowId,
  startedAt,
  className,
}: PlanningIndicatorProps) {
  const revalidator = useRevalidator();
  const [isCancelling, setIsCancelling] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  // Update elapsed time every second
  useEffect(() => {
    if (!startedAt) return;

    const updateElapsed = () => {
      const start = new Date(startedAt).getTime();
      const now = Date.now();
      setElapsed(Math.floor((now - start) / 1000));
    };

    updateElapsed();
    const interval = setInterval(updateElapsed, 1000);
    return () => clearInterval(interval);
  }, [startedAt]);

  const handleCancel = useCallback(async () => {
    setIsCancelling(true);
    try {
      await api.cancelWorkflow(workflowId);
      success('Planning cancelled');
      revalidator.revalidate();
    } catch (err) {
      toastError('Failed to cancel planning');
      console.error('Failed to cancel planning:', err);
    } finally {
      setIsCancelling(false);
    }
  }, [workflowId, revalidator]);

  return (
    <div
      data-slot="planning-indicator"
      className={cn(
        'p-4 border border-status-pending/30 rounded-lg bg-status-pending/5 flex flex-col gap-3',
        className
      )}
    >
      <div className="flex items-center gap-2">
        <Brain className="w-4 h-4 text-status-pending animate-pulse" />
        <h4 className="font-heading text-xs font-semibold tracking-widest text-status-pending">
          PLANNING
        </h4>
        {startedAt && (
          <span className="text-xs text-muted-foreground ml-auto">
            {formatElapsed(elapsed)}
          </span>
        )}
      </div>

      <p className="text-sm text-muted-foreground">
        Architect is analyzing the codebase and generating an implementation plan.
      </p>

      <div className="flex items-center gap-3">
        <Loader className="w-4 h-4 text-status-pending" />
        <span className="text-sm text-muted-foreground">Planning in progress...</span>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleCancel}
          disabled={isCancelling}
          className="ml-auto border-destructive text-destructive hover:bg-destructive hover:text-foreground"
        >
          {isCancelling ? (
            <Loader className="w-3 h-3 mr-1" />
          ) : (
            <X className="w-3 h-3 mr-1" />
          )}
          Cancel
        </Button>
      </div>
    </div>
  );
}
```

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm test -- PlanningIndicator.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/PlanningIndicator.tsx dashboard/src/components/PlanningIndicator.test.tsx
git commit -m "$(cat <<'EOF'
feat(dashboard): add PlanningIndicator component

New component displays when a workflow is in 'planning' status.
Shows elapsed time, explanation text, and a cancel button.

Closes #266

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Frontend - Update WorkflowsPage to show PlanningIndicator

**Files:**
- Modify: `dashboard/src/pages/WorkflowsPage.tsx:131-157`
- Test: `dashboard/src/pages/__tests__/WorkflowsPage.test.tsx`

**Step 1: Write the failing test**

Add to `dashboard/src/pages/__tests__/WorkflowsPage.test.tsx` (create if needed):

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import WorkflowsPage from '../WorkflowsPage';

// Create test router helper
function renderWithRouter(loaderData: any) {
  const router = createMemoryRouter(
    [
      {
        path: '/workflows',
        element: <WorkflowsPage />,
        loader: () => loaderData,
      },
    ],
    { initialEntries: ['/workflows'] }
  );
  return render(<RouterProvider router={router} />);
}

describe('WorkflowsPage', () => {
  it('shows PlanningIndicator when status is planning', async () => {
    renderWithRouter({
      workflows: [{ id: 'wf-1', status: 'planning', issue_id: 'ISSUE-1', worktree_path: '/repo' }],
      detail: {
        id: 'wf-1',
        status: 'planning',
        issue_id: 'ISSUE-1',
        worktree_path: '/repo',
        created_at: new Date().toISOString(),
        recent_events: [],
      },
      detailError: null,
    });

    expect(await screen.findByText('PLANNING')).toBeInTheDocument();
    expect(screen.getByText(/Architect is analyzing/)).toBeInTheDocument();
  });

  it('shows PendingWorkflowControls when status is pending', async () => {
    renderWithRouter({
      workflows: [{ id: 'wf-1', status: 'pending', issue_id: 'ISSUE-1', worktree_path: '/repo' }],
      detail: {
        id: 'wf-1',
        status: 'pending',
        issue_id: 'ISSUE-1',
        worktree_path: '/repo',
        created_at: new Date().toISOString(),
        recent_events: [],
      },
      detailError: null,
    });

    expect(await screen.findByText('QUEUED WORKFLOW')).toBeInTheDocument();
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd dashboard && pnpm test -- WorkflowsPage.test.tsx`
Expected: FAIL because PlanningIndicator is not rendered for planning status

**Step 3: Implement the changes**

In `dashboard/src/pages/WorkflowsPage.tsx`:

Add import at top:
```typescript
import { PlanningIndicator } from '@/components/PlanningIndicator';
```

Add new conditional block after the `ApprovalControls` block (around line 140) and update the pending block:

```typescript
{/* Planning Indicator - shown when Architect is generating plan */}
{detail?.status === 'planning' && (
  <div className="px-4 pt-4">
    <PlanningIndicator
      workflowId={detail.id}
      startedAt={detail.created_at}
    />
  </div>
)}

{/* Pending Workflow Controls - shown when workflow is queued (not planning) */}
{detail?.status === 'pending' && (
  <div className="px-4 pt-4">
    <PendingWorkflowControls
      workflowId={detail.id}
      createdAt={detail.created_at}
      hasPlan={!!detail.plan_markdown}
      worktreeHasActiveWorkflow={workflows.some(
        (w) =>
          w.id !== detail.id &&
          w.worktree_path === detail.worktree_path &&
          w.status === 'in_progress'
      )}
    />
  </div>
)}
```

**Step 4: Run tests to verify they pass**

Run: `cd dashboard && pnpm test -- WorkflowsPage.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/pages/WorkflowsPage.tsx dashboard/src/pages/__tests__/WorkflowsPage.test.tsx
git commit -m "$(cat <<'EOF'
feat(dashboard): show PlanningIndicator for planning status

WorkflowsPage now shows PlanningIndicator when workflow status is
'planning', and PendingWorkflowControls only for 'pending' status.

This prevents the Start button from appearing during planning.

Closes #266

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Frontend - Update worktree blocking logic

**Files:**
- Modify: `dashboard/src/pages/WorkflowsPage.tsx:149-154`
- Existing test coverage should be sufficient

**Step 1: Verify current behavior**

The `worktreeHasActiveWorkflow` check already uses `status === 'in_progress'`, which is correct. Planning status does NOT block the worktree (per design doc). No changes needed to this logic.

**Step 2: Add explicit test for planning not blocking**

Add to `dashboard/src/pages/__tests__/WorkflowsPage.test.tsx`:

```typescript
it('does not block worktree for planning workflows', async () => {
  renderWithRouter({
    workflows: [
      { id: 'wf-1', status: 'planning', issue_id: 'ISSUE-1', worktree_path: '/repo' },
      { id: 'wf-2', status: 'pending', issue_id: 'ISSUE-2', worktree_path: '/repo' },
    ],
    detail: {
      id: 'wf-2',
      status: 'pending',
      issue_id: 'ISSUE-2',
      worktree_path: '/repo',
      created_at: new Date().toISOString(),
      recent_events: [],
    },
    detailError: null,
  });

  // Start button should be enabled (planning doesn't block)
  const startButton = await screen.findByRole('button', { name: /start/i });
  expect(startButton).not.toBeDisabled();
});
```

**Step 3: Run tests**

Run: `cd dashboard && pnpm test -- WorkflowsPage.test.tsx`
Expected: PASS

**Step 4: Commit**

```bash
git add dashboard/src/pages/__tests__/WorkflowsPage.test.tsx
git commit -m "$(cat <<'EOF'
test(dashboard): verify planning status does not block worktree

Adds test confirming that workflows in 'planning' status don't block
other workflows from starting on the same worktree.

Closes #266

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Run full test suite and verify

**Step 1: Run backend tests**

Run: `uv run pytest tests/unit/server/models/test_state.py tests/unit/server/orchestrator/test_queue_and_plan.py -v`
Expected: PASS

**Step 2: Run frontend tests**

Run: `cd dashboard && pnpm test:run`
Expected: PASS

**Step 3: Run type checks**

Run: `uv run mypy amelia && cd dashboard && pnpm type-check`
Expected: No errors

**Step 4: Run linting**

Run: `uv run ruff check amelia tests && cd dashboard && pnpm lint`
Expected: No errors

**Step 5: Manual smoke test**

1. Start the server: `uv run amelia dev`
2. Create a Quick Shot workflow with `plan_now=true`
3. Verify dashboard shows "PLANNING" badge
4. Verify PlanningIndicator is displayed (not Start button)
5. Wait for plan to complete
6. Verify status transitions to "BLOCKED" with ApprovalControls

---

### Task 9: Final commit and push

**Step 1: Squash or rebase if needed**

If commits are clean, skip this step. Otherwise:
```bash
git rebase -i main
```

**Step 2: Push to remote**

Run: `git push -u origin fix/start-button-during-planning`

**Step 3: Create PR**

```bash
gh pr create --title "feat: add planning status to workflow state machine" --body "$(cat <<'EOF'
## Summary
- Adds explicit `planning` status to workflow state machine
- Frontend shows `PlanningIndicator` instead of Start button during planning
- Planning status does not block the worktree (enables future concurrent planning)

## Test plan
- [x] Backend: `test_queue_and_plan_sets_planning_status_immediately` passes
- [x] Frontend: `PlanningIndicator` renders for planning status
- [x] Frontend: Start button not shown during planning
- [x] Manual: Quick Shot with plan_now shows planning indicator

Closes #266

Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
