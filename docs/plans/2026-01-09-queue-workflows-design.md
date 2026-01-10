# Queue Workflows Design

## Problem

Users cannot create workflows in advance without immediately executing them. `amelia start` both creates and runs atomically. There's no way to:
- Queue multiple workflows and start them later
- Review a generated plan before committing to execution
- Batch workflow creation separately from execution timing

## Solution

Allow workflows to remain in `pending` state until explicitly started. Support two queueing modes:
1. **Queue without plan** - Store config, defer planning to start time
2. **Plan & Queue** - Run Architect immediately, store plan, wait to execute

Manual start only (no scheduling). Users can start individually or in batch.

## State Model

Use existing `pending` status. A workflow is "queued" when:
- `workflow_status = "pending"`
- `started_at = None`

New field on `ServerExecutionState`:
- `planned_at: datetime | None` - When Architect completed (if plan was generated)

Distinguish queue variants by checking `execution_state.plan`:
- `plan = None` → planning deferred
- `plan = {...}` → plan ready, waiting to execute

### Worktree Rules

- Multiple `pending` workflows per worktree allowed
- Only one `in_progress` or `blocked` workflow per worktree
- Conflict check happens at start time, not queue time

## API Changes

### Modify `POST /api/workflows`

Add optional parameters (backward compatible defaults):

```python
class CreateWorkflowRequest(BaseModel):
    issue_id: str
    worktree_path: str
    profile: str | None = None
    task_title: str | None = None
    task_description: str | None = None
    start: bool = True          # False = queue without starting
    plan_now: bool = False      # If not starting, run Architect first
```

Behavior matrix:
| `start` | `plan_now` | Result |
|---------|------------|--------|
| `True`  | (ignored)  | Current behavior - workflow begins immediately |
| `False` | `False`    | Create in `pending`, no planning |
| `False` | `True`     | Run Architect, store plan, remain `pending` |

### New `POST /api/workflows/{id}/start`

Start a pending workflow.

**Response:** `202 Accepted` with workflow summary

**Errors:**
- `404` - Workflow not found
- `409` - Workflow not in `pending` state
- `409` - Worktree already has active workflow

### New `POST /api/workflows/start-batch`

Start multiple pending workflows.

```python
class BatchStartRequest(BaseModel):
    workflow_ids: list[str] | None = None  # Specific IDs, or None for all
    worktree_path: str | None = None       # Filter by worktree
```

**Response:**
```python
class BatchStartResponse(BaseModel):
    started: list[str]           # Successfully started workflow IDs
    errors: dict[str, str]       # workflow_id → error message
```

Starts sequentially, respects `AMELIA_MAX_CONCURRENT`. Partial success is possible.

## CLI Changes

### Modify `amelia start`

Add `--queue` and `--plan` flags:

```bash
# Current behavior (unchanged)
amelia start ISSUE-123

# Queue without planning
amelia start ISSUE-123 --queue

# Queue with planning
amelia start ISSUE-123 --queue --plan
```

`--plan` without `--queue` is an error.

### New `amelia run` command

```bash
# Start specific workflow
amelia run <workflow-id>

# Start all pending
amelia run --all

# Start all pending for worktree
amelia run --all --worktree /path/to/repo
```

### `amelia status` output

Shows pending workflows with queue context:

```
wf-abc123  ISSUE-123  pending  (queued 2h ago, no plan)
wf-def456  ISSUE-456  pending  (queued 1h ago, plan ready)
wf-ghi789  ISSUE-789  in_progress  (running for 10m)
```

## Dashboard Changes

### Quick Shot Modal

Three action buttons in footer:

```
[Cancel]  [Queue]  [Plan & Queue]  [Start]
```

- **Start** (primary style) → `start=True`
- **Plan & Queue** (secondary) → `start=False, plan_now=True`
- **Queue** (secondary) → `start=False, plan_now=False`

### Active Jobs Page

Pending workflows appear with:
- "Queued" badge (muted styling, distinct from active states)
- "queued 2h ago" timestamp (not elapsed runtime)
- "Plan ready" or "No plan" indicator
- Row actions: **Start**, **Cancel**

## Error Handling

### Plan & Queue Failures

If Architect fails during "Plan & Queue":
- Workflow is saved with `status = "failed"`
- `failure_reason` contains the error
- User can see what went wrong, cancel, and retry

### Stale Workflows

No automatic cleanup for pending workflows. If a queued workflow becomes stale (issue closed, worktree deleted):
- User explicitly cancels or attempts to start
- Starting a stale workflow fails naturally with appropriate error
- `amelia status` could warn if worktree path doesn't exist

### Batch Start Errors

- Sequential execution respects concurrency limits
- Partial success: some workflows start, others fail
- Response includes both `started` IDs and `errors` map

## Implementation Files

### Backend

| File | Change |
|------|--------|
| `amelia/server/models/state.py` | Add `planned_at` field |
| `amelia/server/models/requests.py` | Add `start`, `plan_now` fields; new `BatchStartRequest` |
| `amelia/server/routes/workflows.py` | Modify POST, add start endpoints |
| `amelia/server/orchestrator/service.py` | Add queue/start methods |
| `amelia/client/cli.py` | Add flags to `start`; new `run` command |

### Frontend

| File | Change |
|------|--------|
| `dashboard/src/types/index.ts` | Update request types |
| `dashboard/src/api/client.ts` | Add `startWorkflow()`, `startBatch()` |
| `dashboard/src/components/QuickShotModal.tsx` | Add Queue and Plan & Queue buttons |
| `dashboard/src/pages/WorkflowsPage.tsx` | Add Start/Cancel for pending rows |
| `dashboard/src/components/StatusBadge.tsx` | Style "pending" as "Queued" |

## Future Considerations

Not in scope, but could be added later:
- **Scheduled execution** - Start at specific time or after delay
- **Recurring workflows** - Cron-style patterns
- **Workflow templates** - Save common configurations for quick re-queue
