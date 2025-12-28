# Agentic-Only Execution Migration Manual Testing Plan

**Branch:** `feat/deepagents-driver`
**Feature:** Complete removal of structured execution (batches, blockers, steps) and migration to agentic-only execution model

## Overview

This PR represents a major architectural refactoring that:

1. **Removes structured execution** - Deletes all PlanStep, ExecutionBatch, BatchResult, StepResult, BlockerReport models and related code
2. **Simplifies the orchestrator** - Removes batch/blocker nodes, streamlines the LangGraph state machine
3. **Adds multi-provider API support** - OpenAI and OpenRouter providers with prefix syntax (`openai:gpt-4o`, `openrouter:anthropic/claude-3.5-sonnet`)
4. **Preserves markdown planning** - Architect still generates rich markdown plans for agentic execution
5. **Updates the dashboard** - Removes batch/step visualization components, simplifies workflow display

Manual testing is needed because:
- The CLI commands have been significantly refactored
- The API endpoints have changed (batch/blocker endpoints removed)
- The dashboard UI has been simplified (batch visualization removed)
- The `amelia plan` command now calls Architect directly instead of going through the workflow API

---

## Prerequisites

### Environment Setup

```bash
# 1. Install Python dependencies
cd /Users/ka/github/existential-birds/amelia
uv sync

# 2. Verify environment variables for API testing
# Set at least one of these for provider tests:
export OPENAI_API_KEY="your-key"        # For openai: prefix
export OPENROUTER_API_KEY="your-key"    # For openrouter: prefix

# 3. Start the backend server
uv run amelia server --reload
# Server runs on http://localhost:8420 by default

# 4. For dashboard testing (general usage - no frontend changes)
# Dashboard is served at localhost:8420 by the backend server above

# 5. Verify setup
uv run amelia --version
curl http://localhost:8420/health
```

### Testing Tools

- `curl` for API endpoint testing
- Web browser for dashboard UI testing
- Terminal for CLI command testing

---

## Test Scenarios

### TC-01: CLI Plan Command (Direct Architect Call)

**Objective:** Verify the `amelia plan` command generates markdown plans by calling Architect directly (not through workflow API)

**Preconditions:**
- A valid `settings.amelia.yaml` exists in the test worktree
- A GitHub issue tracker is configured (or use `noop` tracker)

**Steps:**
1. Navigate to a worktree with Amelia configured
2. Run the plan command with a test issue ID
3. Verify plan file is created in `docs/plans/`

**Expected Result:**
- Command prints "Generating plan for {issue_id}..."
- Command prints "Plan generated successfully!"
- Command shows goal, saved path, and key files
- A markdown file exists at `docs/plans/YYYY-MM-DD-{issue-id}.md`
- Plan contains implementation guidance (not structured PlanStep data)

**Verification Commands:**
```bash
cd /path/to/worktree
uv run amelia plan TEST-123 --profile work
ls -la docs/plans/
cat docs/plans/2025-12-*-TEST-123.md | head -50
```

---

### TC-02: Workflow Creation (Agentic Mode)

**Objective:** Verify the workflow API creates agentic workflows without batch/blocker fields

**Steps:**
1. Start the Amelia server
2. Create a workflow via POST /workflows
3. Verify response contains agentic fields (goal, status)
4. Verify response does NOT contain structured fields (execution_plan, batch_results)

**Expected Result:**
- Response has status 201
- Response includes `id`, `status`, `message`
- No `execution_plan`, `current_batch_index`, `batch_results` fields

**Verification Commands:**
```bash
curl -X POST http://localhost:8420/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "issue_id": "TEST-123",
    "worktree_path": "/tmp/test-worktree",
    "worktree_name": "test"
  }' | jq .
```

---

### TC-03: Workflow Detail Endpoint (Agentic Fields)

**Objective:** Verify GET /workflows/{id} returns agentic-style response

**Steps:**
1. Create a workflow (TC-02)
2. Fetch workflow details via GET
3. Verify response structure matches agentic model

**Expected Result:**
- Response includes `goal`, `plan_markdown`, `plan_path`
- Response includes `current_stage`, `status`
- Response does NOT include `execution_plan`, `batch_results`, `developer_status`

**Verification Commands:**
```bash
# Get workflow ID from TC-02
WORKFLOW_ID="<id-from-tc02>"
curl http://localhost:8420/workflows/$WORKFLOW_ID | jq .
```

---

### TC-04: Removed Endpoints Return 404

**Objective:** Verify batch/blocker endpoints have been removed

**Steps:**
1. Try to POST to batch approval endpoint
2. Try to POST to blocker resolution endpoint

**Expected Result:**
- Both endpoints return 404 Not Found

**Verification Commands:**
```bash
# These should return 404
curl -X POST http://localhost:8420/workflows/test-id/batches/0/approve \
  -H "Content-Type: application/json" \
  -d '{"approved": true}'

curl -X POST http://localhost:8420/workflows/test-id/blockers/resolve \
  -H "Content-Type: application/json" \
  -d '{"action": "skip"}'
```

---

### TC-05: Dashboard Workflow List Page

**Objective:** Verify workflows list page loads without errors

**Steps:**
1. Open http://localhost:8420 in browser
2. Navigate to workflows list
3. Verify page loads without console errors

**Expected Result:**
- Page renders without JavaScript errors
- Workflow list displays (may be empty)
- No references to batch/step components in UI

**Verification Commands:**
```bash
# Open in browser and check console
open http://localhost:8420
# Check browser developer console for errors
```

---

### TC-06: Dashboard Workflow Detail Page

**Objective:** Verify workflow detail page shows agentic execution view

**Steps:**
1. Create a workflow (via CLI or API)
2. Navigate to workflow detail page in browser
3. Verify page renders without batch visualization

**Expected Result:**
- Page shows workflow header with issue ID, status, elapsed time
- Page shows agent progress bar (pm -> architect -> developer -> reviewer)
- Page shows workflow canvas with simplified nodes
- No batch/step/blocker UI elements visible
- No console errors

**Verification Commands:**
```bash
# Navigate to a specific workflow
open http://localhost:8420/workflows/<workflow-id>
```

---

### TC-07: API Driver Provider Validation

**Objective:** Verify API driver correctly validates provider prefixes

**Steps:**
1. Test that openai: prefix is accepted
2. Test that openrouter: prefix is accepted
3. Test that invalid prefix is rejected

**Expected Result:**
- `openai:gpt-4o` creates driver successfully
- `openrouter:anthropic/claude-3.5-sonnet` creates driver successfully
- `gemini:pro` raises ValueError with "Unsupported provider"

**Verification Commands:**
```bash
# Run unit tests for provider validation
uv run pytest tests/unit/test_api_driver_providers.py -v
```

---

### TC-08: Review Workflow (Local)

**Objective:** Verify the review workflow works with agentic execution

**Steps:**
1. Make some uncommitted changes in a worktree
2. Run `amelia review --local`
3. Verify review workflow starts successfully

**Expected Result:**
- Review workflow is created
- Workflow analyzes uncommitted changes
- Reviewer agent provides feedback
- No batch/blocker concepts in output

**Verification Commands:**
```bash
cd /path/to/worktree
# Make a test change
echo "test" > test-file.txt
uv run amelia review --local
```

---

### TC-09: Approval/Rejection Flow

**Objective:** Verify plan approval and rejection still work

**Steps:**
1. Create a workflow that pauses for approval
2. Test approve command
3. Test reject command

**Expected Result:**
- Workflow pauses at `blocked` status awaiting approval
- `amelia approve` allows workflow to continue
- `amelia reject "reason"` cancels workflow with reason

**Verification Commands:**
```bash
# When a workflow is in blocked state:
uv run amelia approve
# OR
uv run amelia reject "Plan doesn't match requirements"
```

---

### TC-10: Full Workflow End-to-End

**Objective:** Verify complete workflow executes through all stages

**Steps:**
1. Start the server
2. Create a workflow for a simple issue
3. Approve the plan when prompted
4. Monitor progress through developer and reviewer stages
5. Verify workflow completes

**Expected Result:**
- Workflow progresses: pending -> in_progress -> blocked (approval) -> in_progress -> completed
- Dashboard shows progress through stages
- No errors in server logs
- Final status is `completed` or `failed` (not stuck)

**Verification Commands:**
```bash
# Start server in one terminal
uv run amelia server

# In another terminal
uv run amelia start TEST-123 --profile work

# Monitor via API
watch -n 2 "curl -s http://localhost:8420/workflows/active | jq ."
```

---

## Test Environment Cleanup

After testing:
```bash
# Stop the server
# (Ctrl+C in server terminal)

# Clean up test files
rm -f test-file.txt
rm -rf docs/plans/2025-12-*-TEST-*.md
```

---

## Test Result Template

| Test ID | Description | Status | Notes |
|---------|-------------|--------|-------|
| TC-01 | CLI plan command generates markdown | [ ] Pass / [ ] Fail | |
| TC-02 | Workflow creation returns agentic response | [ ] Pass / [ ] Fail | |
| TC-03 | Workflow detail has agentic fields | [ ] Pass / [ ] Fail | |
| TC-04 | Removed endpoints return 404 | [ ] Pass / [ ] Fail | |
| TC-05 | Dashboard list page loads | [ ] Pass / [ ] Fail | |
| TC-06 | Dashboard detail page shows agentic UI | [ ] Pass / [ ] Fail | |
| TC-07 | API driver provider validation | [ ] Pass / [ ] Fail | |
| TC-08 | Review workflow works | [ ] Pass / [ ] Fail | |
| TC-09 | Approval/rejection flow | [ ] Pass / [ ] Fail | |
| TC-10 | Full workflow E2E | [ ] Pass / [ ] Fail | |

---

## Agent Execution Notes

### For LLM Agent Executing This Plan:

1. **Start server first** - Many tests require the Amelia server running
2. **Execute tests sequentially** - Some tests depend on workflow state from previous tests
3. **Capture output** - Log curl responses and CLI output for verification
4. **Check console** - Browser developer console for dashboard tests
5. **Report issues** - Note any failures with exact error messages

### Key Files Changed in This Branch

1. **CLI changes** (`amelia/client/cli.py`):
   - `plan_command` now calls Architect directly (not through workflow API)
   - No `plan_only` parameter in workflow creation

2. **Server changes** (`amelia/server/`):
   - Removed batch approval endpoint
   - Removed blocker resolution endpoint
   - Response models simplified for agentic execution

3. **Dashboard changes** (`dashboard/src/`):
   - Deleted BatchNode, StepNode, CheckpointMarker components
   - Deleted BlockerResolutionDialog, CancelStepDialog
   - WorkflowDetailPage simplified

4. **Core changes** (`amelia/core/`):
   - `orchestrator.py` - Simplified graph without batch/blocker nodes
   - `state.py` - Removed structured execution models
   - `types.py` - Removed ExecutionMode, TrustLevel, DeveloperStatus

5. **Agent changes** (`amelia/agents/`):
   - `developer.py` - Rewritten for agentic execution
   - `architect.py` - Simplified to only generate markdown plans
