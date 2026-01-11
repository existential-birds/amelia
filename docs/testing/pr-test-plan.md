# Planning Status Manual Testing Plan

**Branch:** `fix/start-button-during-planning`
**Feature:** Add "planning" status to workflow state machine

## Overview

This PR introduces a new "planning" workflow status that shows when the Architect agent is analyzing an issue and generating an implementation plan. Previously, workflows jumped directly from "pending" to "in_progress" or "blocked" - now they transition through "planning" first.

Key changes:
1. **State machine** - Added `planning` as a valid workflow status with transitions: `pending → planning → blocked`
2. **Orchestrator** - New workflows now start in `planning` status while the Architect runs
3. **Dashboard** - New `PlanningIndicator` component shows planning progress with elapsed time and cancel button
4. **StatusBadge** - Added "PLANNING" status with pulsing animation

This enables users to see that work is happening (Architect running) rather than the workflow appearing stuck in "pending".

---

## Prerequisites

### Environment Setup

```bash
# 1. Install Python dependencies
cd /path/to/amelia
uv sync

# 2. Start the backend server
uv run amelia server --reload
# Server runs on http://localhost:8420 by default

# 3. For dashboard testing
# Dashboard is served at localhost:8420 by the backend server
# Open http://localhost:8420 in browser

# 4. Verify setup
curl http://localhost:8420/api/health
# Should return {"status": "ok"}
```

### Testing Tools

- Browser with DevTools (Chrome/Firefox/Edge)
- Terminal for running CLI commands
- A test issue ID (can use `test-123` for local testing)
- Test repository: `/Users/ka/github/anderskev-dot-com`

---

## Test Scenarios

### TC-01: New Workflow Enters Planning Status

**Objective:** Verify that creating a new workflow immediately shows "planning" status

**Steps:**
1. Open the dashboard at http://localhost:8420
2. Create a new workflow via API:
   ```bash
   curl -X POST http://localhost:8420/api/workflows \
     -H "Content-Type: application/json" \
     -d '{"issue_id": "TEST-001", "profile": "dev_api", "worktree_path": "/Users/ka/github/anderskev-dot-com", "start": false, "plan_now": true}'
   ```
3. Immediately check the workflow status in the dashboard

**Expected Result:**
- Workflow appears in the job queue with "PLANNING" badge (pulsing animation)
- Status badge shows yellow/amber color with pulse animation
- PlanningIndicator component is visible when workflow is selected

**Verification Commands:**
```bash
# Check workflow status via API
curl http://localhost:8420/api/workflows | jq '.[] | select(.issue_id == "TEST-001") | .status'
# Should return "planning"
```

---

### TC-02: PlanningIndicator Component Displays Correctly

**Objective:** Verify the PlanningIndicator UI shows all expected elements

**Steps:**
1. Create a workflow that enters planning status (TC-01)
2. Select the workflow in the dashboard
3. Observe the PlanningIndicator component below the canvas

**Expected Result:**
- "PLANNING" heading visible in yellow/amber color
- Elapsed time counter updating every second (e.g., "15s", "1m 30s")
- Animated loader spinner visible
- Message: "Architect is analyzing the issue and generating an implementation plan..."
- Red "Cancel" button visible

---

### TC-03: Elapsed Time Updates in Real-Time

**Objective:** Verify the elapsed time counter updates correctly

**Steps:**
1. Create a workflow that enters planning status
2. Select the workflow in dashboard
3. Watch the elapsed time for 60+ seconds

**Expected Result:**
- Time updates every second
- Format transitions correctly:
  - `0s` → `30s` → `59s` → `1m` → `1m 30s` → `2m`
- If planning takes over an hour: `1h 0m`, `1h 30m`

---

### TC-04: Cancel Button During Planning

**Objective:** Verify that cancelling a workflow during planning works correctly

**Steps:**
1. Create a workflow that enters planning status
2. Click the "Cancel" button in the PlanningIndicator
3. Observe the workflow status change

**Expected Result:**
- Cancel button shows loading spinner while cancelling
- Toast notification: "Planning cancelled"
- Workflow status changes to "cancelled"
- StatusBadge updates to show "CANCELLED"
- PlanningIndicator disappears, replaced by cancelled state

**Verification Commands:**
```bash
# Check workflow was cancelled
curl http://localhost:8420/api/workflows | jq '.[] | select(.issue_id == "TEST-001") | .status'
# Should return "cancelled"
```

---

### TC-05: StatusBadge Shows Planning State

**Objective:** Verify StatusBadge correctly displays planning status

**Steps:**
1. Create a workflow that enters planning status
2. Observe the StatusBadge in:
   - Page header (top right)
   - Job queue list

**Expected Result:**
- Badge shows "PLANNING" text
- Yellow/amber color scheme (same as pending)
- Pulsing animation active on the badge
- Data attribute: `data-status="planning"`

---

### TC-06: Planning to Blocked Transition

**Objective:** Verify workflow transitions correctly from planning to blocked (awaiting approval)

**Steps:**
1. Create a workflow with a real issue or mock the Architect response
2. Wait for the Architect to complete plan generation
3. Observe the workflow status change

**Expected Result:**
- Status transitions: `planning` → `blocked`
- StatusBadge updates to "BLOCKED" (orange color)
- PlanningIndicator disappears
- ApprovalControls component appears with the generated plan
- `planned_at` timestamp is set on the workflow

**Verification Commands:**
```bash
# Check workflow transitioned to blocked with plan
curl http://localhost:8420/api/workflows/WORKFLOW_ID | jq '{status, planned_at, goal}'
```

---

### TC-07: Planning Does Not Block Worktree

**Objective:** Verify a workflow in planning status does not prevent starting another workflow in the same worktree

**Steps:**
1. Create workflow A for worktree `/Users/ka/github/anderskev-dot-com`
2. While workflow A is in "planning" status, create workflow B for the same worktree
3. Observe if workflow B is created successfully

**Expected Result:**
- Workflow B should be created successfully
- The planning status should NOT block the worktree (only `in_progress` blocks it)
- Both workflows can exist in planning/pending states for the same worktree

**Note:** This is a key behavioral change - previously starting a workflow immediately blocked the worktree, now planning workflows don't block.

---

### TC-08: Planning Failure Handling

**Objective:** Verify graceful handling when planning fails

**Steps:**
1. Create a workflow that will fail during planning (e.g., invalid issue, driver error)
2. Observe the workflow status

**Expected Result:**
- Workflow status transitions to "failed"
- `failure_reason` contains "Planning failed: <error message>"
- StatusBadge shows "FAILED" (red color)
- PlanningIndicator disappears

---

### TC-09: Multiple Concurrent Planning Workflows

**Objective:** Verify multiple workflows can be planning simultaneously

**Steps:**
1. Create workflow A for worktree `/Users/ka/github/anderskev-dot-com`
2. Immediately create workflow B for a different worktree (e.g., `/Users/ka/github/existential-birds/amelia`)
3. Observe both workflows in the dashboard

**Expected Result:**
- Both workflows show "PLANNING" status
- Both have their own PlanningIndicator when selected
- Elapsed times are independent
- Each can be cancelled independently

---

### TC-10: State Machine Validates Planning Transitions

**Objective:** Verify invalid state transitions from planning are rejected

**Steps:**
1. Attempt to transition a planning workflow directly to `in_progress` via API
2. Attempt to transition a planning workflow directly to `completed`

**Expected Result:**
- Transitions to `in_progress` from `planning` should be rejected
- Transitions to `completed` from `planning` should be rejected
- Only valid transitions: `planning` → `blocked`, `planning` → `failed`, `planning` → `cancelled`

---

## Test Environment Cleanup

After testing:
```bash
# Cancel any running workflows
curl http://localhost:8420/api/workflows | jq -r '.[].id' | xargs -I {} curl -X DELETE http://localhost:8420/api/workflows/{}

# Stop the server
# Ctrl+C in the server terminal
```

---

## Test Result Template

| Test ID | Description | Status | Notes |
|---------|-------------|--------|-------|
| TC-01 | New workflow enters planning status | [ ] Pass / [ ] Fail | |
| TC-02 | PlanningIndicator displays correctly | [ ] Pass / [ ] Fail | |
| TC-03 | Elapsed time updates in real-time | [ ] Pass / [ ] Fail | |
| TC-04 | Cancel button during planning | [ ] Pass / [ ] Fail | |
| TC-05 | StatusBadge shows planning state | [ ] Pass / [ ] Fail | |
| TC-06 | Planning to blocked transition | [ ] Pass / [ ] Fail | |
| TC-07 | Planning does not block worktree | [ ] Pass / [ ] Fail | |
| TC-08 | Planning failure handling | [ ] Pass / [ ] Fail | |
| TC-09 | Multiple concurrent planning workflows | [ ] Pass / [ ] Fail | |
| TC-10 | State machine validates transitions | [ ] Pass / [ ] Fail | |

---

## Agent Execution Notes

### For LLM Agent Executing This Plan:

1. **Start the server** - Run `uv run amelia server --reload` and verify it's running
2. **Use Chrome DevTools MCP** - Navigate to http://localhost:8420 and use take_snapshot/click tools
3. **Execute tests sequentially** - Some tests depend on workflows being in specific states
4. **Capture screenshots** - Take screenshots of key states (planning indicator, status badges)
5. **Log API responses** - Capture workflow JSON to verify field values
6. **Mark results** - Update the result template after each test

### Programmatic Testing Example:

```python
import httpx
import asyncio

async def test_planning_status():
    async with httpx.AsyncClient(base_url="http://localhost:8420") as client:
        # Create workflow
        resp = await client.post("/api/workflows", json={
            "issue_id": "TEST-PLAN-001",
            "profile": "dev_api",
            "worktree_path": "/Users/ka/github/anderskev-dot-com",
            "start": False,
            "plan_now": True,
        })
        workflow_id = resp.json()["id"]

        # Check it's in planning
        resp = await client.get(f"/api/workflows/{workflow_id}")
        assert resp.json()["status"] == "planning"

        # Cancel it
        await client.delete(f"/api/workflows/{workflow_id}")

        resp = await client.get(f"/api/workflows/{workflow_id}")
        assert resp.json()["status"] == "cancelled"
```

---

## Key Changes in This Branch

The following changes should be verified through testing:

1. **State machine** (`amelia/server/models/state.py`):
   - Added `planning` to `WorkflowStatus` type
   - Added valid transitions: `pending → planning`, `planning → blocked/failed/cancelled`
   - Added `planned_at` timestamp field

2. **Orchestrator** (`amelia/server/orchestrator/service.py`):
   - Workflows now start in `planning` status instead of `pending`
   - Planning runs as background task via `_run_planning_task()`
   - Planning tasks tracked in `_planning_tasks` dict

3. **PlanningIndicator** (`dashboard/src/components/PlanningIndicator.tsx`):
   - New component showing planning progress
   - Elapsed time with real-time updates
   - Cancel button with API integration

4. **StatusBadge** (`dashboard/src/components/StatusBadge.tsx`):
   - Added `planning` variant with pulse animation
   - Maps to "PLANNING" label

5. **WorkflowsPage** (`dashboard/src/pages/WorkflowsPage.tsx`):
   - Shows PlanningIndicator when `status === 'planning'`
