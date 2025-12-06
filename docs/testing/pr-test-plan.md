# LangGraph Execution Bridge Manual Testing Plan

**Branch:** `feat/langgraph-execution-bridge`
**Feature:** Server-side LangGraph execution with interrupt/resume for human approval

## Overview

This PR implements the LangGraph execution bridge that enables:
- **Interrupt-based approval flow**: Workflow pauses at `human_approval_node` via LangGraph's `interrupt_before` mechanism
- **Checkpoint persistence**: Workflow state saved to SQLite via `langgraph-checkpoint-sqlite`
- **Server-mode execution**: Distinct from CLI mode - approval happens via API, not blocking prompt
- **State resumption**: After approval, graph resumes with `human_approved=True` in state
- **Event emission**: `APPROVAL_REQUIRED`, `APPROVAL_GRANTED`, `STAGE_STARTED`, `STAGE_COMPLETED` events

Manual testing is needed because:
1. LangGraph checkpoint/resume behavior requires real SQLite integration
2. Async task lifecycle and cleanup need verification
3. Event bus integration and timing need end-to-end verification

---

## Prerequisites

### Environment Setup

```bash
# 1. Navigate to project
cd /Users/ka/github/amelia-langgraph-bridge

# 2. Install dependencies (includes langgraph-checkpoint-sqlite)
uv sync

# 3. Verify dependencies
uv run python -c "from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver; print('OK')"
```

### Testing Tools

- `curl` or `httpie` for API requests
- `sqlite3` for checkpoint database inspection
- Second terminal for monitoring logs

---

## Test Scenarios

### TC-01: Workflow Starts and Pauses at Approval

**Objective:** Verify workflow execution pauses at `human_approval_node` and emits `APPROVAL_REQUIRED` event.

**Steps:**
1. Start the server with logging enabled
2. Start a workflow via API
3. Monitor events for `APPROVAL_REQUIRED`
4. Verify workflow status is `blocked`

**Expected Result:**
- Workflow status transitions: `pending` -> `in_progress` -> `blocked`
- `WORKFLOW_STARTED` event emitted
- `STAGE_STARTED` event for `architect_node`
- `APPROVAL_REQUIRED` event emitted with `paused_at: human_approval_node`

**Verification Commands:**
```bash
# Start server (terminal 1)
uv run amelia server --reload

# Start workflow (terminal 2)
curl -X POST http://localhost:8420/api/workflows \
  -H "Content-Type: application/json" \
  -d '{"issue_id": "30", "worktree_path": "/tmp/test-wt"}'

# Check workflow status
curl http://localhost:8420/api/workflows/{workflow_id}
# Expected: {"workflow_status": "blocked", ...}

# Check events
curl http://localhost:8420/api/workflows/{workflow_id}/events
# Expected: WORKFLOW_STARTED, STAGE_STARTED, APPROVAL_REQUIRED events
```

---

### TC-02: Approve Workflow Resumes Execution

**Objective:** Verify `approve_workflow` updates state and resumes LangGraph execution.

**Steps:**
1. Start a workflow and wait for `blocked` status
2. Call approve endpoint
3. Monitor events for `APPROVAL_GRANTED` and subsequent stages
4. Verify final status is `completed`

**Expected Result:**
- `APPROVAL_GRANTED` event emitted
- Status transitions: `blocked` -> `in_progress` -> `completed`
- Graph state updated with `human_approved=True`
- Developer and reviewer nodes execute

**Verification Commands:**
```bash
# Approve the blocked workflow
curl -X POST http://localhost:8420/api/workflows/{workflow_id}/approve

# Monitor status
curl http://localhost:8420/api/workflows/{workflow_id}
# Expected: {"workflow_status": "completed", ...} (after execution)

# Check events include all stages
curl http://localhost:8420/api/workflows/{workflow_id}/events
# Expected: APPROVAL_GRANTED, STAGE_STARTED (developer), STAGE_COMPLETED, etc.
```

---

### TC-03: Reject Workflow Sets Failed State

**Objective:** Verify `reject_workflow` cancels execution and updates LangGraph state.

**Steps:**
1. Start a workflow and wait for `blocked` status
2. Call reject endpoint with feedback
3. Verify status is `failed` with rejection reason

**Expected Result:**
- `APPROVAL_REJECTED` event emitted
- Status set to `failed`
- `failure_reason` contains rejection feedback
- Graph state updated with `human_approved=False`

**Verification Commands:**
```bash
# Reject the blocked workflow
curl -X POST http://localhost:8420/api/workflows/{workflow_id}/reject \
  -H "Content-Type: application/json" \
  -d '{"feedback": "Plan needs more detail"}'

# Verify status
curl http://localhost:8420/api/workflows/{workflow_id}
# Expected: {"workflow_status": "failed", "failure_reason": "Plan needs more detail"}
```

---

### TC-04: Checkpoint Persistence Survives Server Restart

**Objective:** Verify checkpoint state is persisted to SQLite and survives restarts.

**Steps:**
1. Start workflow and pause at approval
2. Stop the server
3. Inspect checkpoint database
4. Restart server
5. Verify workflow can be recovered or shows correct state

**Expected Result:**
- Checkpoint database (`~/.amelia/checkpoints.db`) contains workflow state
- State includes graph position at `human_approval_node`

**Verification Commands:**
```bash
# After workflow is blocked, stop server (Ctrl+C)

# Inspect checkpoint database
sqlite3 ~/.amelia/checkpoints.db ".tables"
# Expected: checkpoints table exists

sqlite3 ~/.amelia/checkpoints.db "SELECT thread_id FROM checkpoints;"
# Expected: workflow_id from blocked workflow

# Restart server and check workflow state
uv run amelia server --reload
curl http://localhost:8420/api/workflows/{workflow_id}
```

---

### TC-05: Approve Non-Blocked Workflow Returns Error

**Objective:** Verify approve/reject only work on blocked workflows.

**Steps:**
1. Try to approve a workflow that is not blocked
2. Verify appropriate error response

**Expected Result:**
- HTTP 400 or 409 error
- Error message indicates invalid state

**Verification Commands:**
```bash
# Try to approve a completed or non-existent workflow
curl -X POST http://localhost:8420/api/workflows/non-existent/approve
# Expected: 404 WorkflowNotFoundError

# Try to approve already-completed workflow
curl -X POST http://localhost:8420/api/workflows/{completed_id}/approve
# Expected: 400/409 InvalidStateError
```

---

### TC-06: Event Mapping Emits Stage Events

**Objective:** Verify LangGraph events are correctly mapped to workflow events.

**Steps:**
1. Start and approve a workflow
2. Check all stage events are emitted correctly

**Expected Result:**
- `STAGE_STARTED` events for: `architect_node`, `human_approval_node`, `developer_node`, `reviewer_node`
- `STAGE_COMPLETED` events for each stage
- Events have correct `stage` field in data

**Verification Commands:**
```bash
# After workflow completes
curl http://localhost:8420/api/workflows/{workflow_id}/events | jq '.[] | select(.event_type | contains("STAGE"))'
# Expected: Paired STAGE_STARTED/STAGE_COMPLETED for each node
```

---

### TC-07: Concurrent Workflow Isolation

**Objective:** Verify multiple workflows don't interfere with each other.

**Steps:**
1. Start workflow A on worktree `/tmp/wt-a`
2. Start workflow B on worktree `/tmp/wt-b`
3. Approve workflow A
4. Verify workflow B still blocked
5. Approve workflow B

**Expected Result:**
- Each workflow has independent checkpoint
- Approving one doesn't affect the other
- Both complete successfully

**Verification Commands:**
```bash
# Start two workflows
curl -X POST http://localhost:8420/api/workflows \
  -d '{"issue_id": "TEST-A", "worktree_path": "/tmp/wt-a"}'
# Note workflow_id_a

curl -X POST http://localhost:8420/api/workflows \
  -d '{"issue_id": "TEST-B", "worktree_path": "/tmp/wt-b"}'
# Note workflow_id_b

# Approve A
curl -X POST http://localhost:8420/api/workflows/{workflow_id_a}/approve

# Check B is still blocked
curl http://localhost:8420/api/workflows/{workflow_id_b}
# Expected: {"workflow_status": "blocked"}
```

---

## Test Environment Cleanup

After testing:
```bash
# Stop the server
# Ctrl+C in server terminal

# Clean up test worktrees
rm -rf /tmp/wt-a /tmp/wt-b /tmp/test-wt

# Optionally remove checkpoint database
rm -f ~/.amelia/checkpoints.db
```

---

## Test Result Template

| Test ID | Description | Status | Notes |
|---------|-------------|--------|-------|
| TC-01 | Workflow pauses at approval | [ ] Pass / [ ] Fail | |
| TC-02 | Approve resumes execution | [ ] Pass / [ ] Fail | |
| TC-03 | Reject sets failed state | [ ] Pass / [ ] Fail | |
| TC-04 | Checkpoint survives restart | [ ] Pass / [ ] Fail | |
| TC-05 | Error on approve non-blocked | [ ] Pass / [ ] Fail | |
| TC-06 | Stage events emitted correctly | [ ] Pass / [ ] Fail | |
| TC-07 | Concurrent workflow isolation | [ ] Pass / [ ] Fail | |

---

## Agent Execution Notes

### For LLM Agent Executing This Plan:

1. **Start server first** - All tests require a running server
2. **Execute tests sequentially** - TC-01 through TC-03 follow a workflow lifecycle
3. **Capture workflow IDs** - Store IDs from POST responses for subsequent requests
4. **Monitor logs** - Server logs will show LangGraph execution details
5. **Check checkpoint DB** - Use sqlite3 to verify persistence

### Programmatic Test Execution

```python
import httpx
import asyncio

async def test_approval_flow():
    async with httpx.AsyncClient(base_url="http://localhost:8420") as client:
        # Start workflow
        resp = await client.post("/api/workflows", json={
            "issue_id": "30",
            "worktree_path": "/tmp/test-wt"
        })
        workflow_id = resp.json()["id"]

        # Poll until blocked
        for _ in range(30):
            status = await client.get(f"/api/workflows/{workflow_id}")
            if status.json()["workflow_status"] == "blocked":
                break
            await asyncio.sleep(1)

        # Approve
        await client.post(f"/api/workflows/{workflow_id}/approve")

        # Poll until completed
        for _ in range(60):
            status = await client.get(f"/api/workflows/{workflow_id}")
            if status.json()["workflow_status"] in ("completed", "failed"):
                print(f"Final status: {status.json()['workflow_status']}")
                break
            await asyncio.sleep(1)
```

---

## Key Changes in This Branch

The following changes should be verified through testing:

1. **Orchestrator interrupt support** (`amelia/core/orchestrator.py`):
   - `create_orchestrator_graph()` accepts `interrupt_before` parameter
   - `human_approval_node` returns state unchanged in server mode

2. **Server execution bridge** (`amelia/server/orchestrator/service.py`):
   - `_run_workflow()` creates graph with `interrupt_before=["human_approval_node"]`
   - `_run_workflow()` converts `ExecutionState` to JSON-serializable dict using `model_dump(mode="json")` before passing to LangGraph (required for SQLite checkpoint persistence)
   - `approve_workflow()` uses `graph.aupdate_state()` and resumes execution
   - `reject_workflow()` updates state with `human_approved=False`
   - Event mapping via `_handle_graph_event()` and `STAGE_NODES`

3. **State composition** (`amelia/server/models/state.py`):
   - `ServerExecutionState.execution_state` holds core state for LangGraph
