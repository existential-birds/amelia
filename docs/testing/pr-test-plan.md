# Claude Agent SDK Migration Manual Testing Plan

**Branch:** `ka/sdk-migration`
**Feature:** Migration from pydantic-ai to Claude Agent SDK and DeepAgents for driver layer

## Overview

This PR migrates the driver layer to use official SDKs:
- **CLI Driver** (`cli:claude`): Now uses `claude-agent-sdk` package
- **API Driver** (`api:openrouter`): Now uses `deepagents` (LangGraph-based)
- **New Evaluator Agent**: Evaluates review feedback with decision matrix
- **Dashboard Simplification**: Removed batch execution UI

---

## Test Environment

**Test Repository:** `/Users/ka/github/anderskev-dot-com`
**Test Issue:** Issue #2
**Profile:** `dev` (cli:claude driver with github tracker)

---

## Test Scenarios

### TC-01: Plan Generation

**Objective:** Verify the SDK-based CLI driver generates implementation plans

**Steps:**
```bash
cd /Users/ka/github/anderskev-dot-com
uv run amelia plan 2
```

**Expected Result:**
- Plan markdown created in `docs/plans/`
- Goal extracted and displayed
- Key files identified
- No errors or JSON parsing issues

**Verify:**
```bash
ls docs/plans/
cat docs/plans/*.md | head -50
```

---

### TC-02: Full Workflow - Start to Approval

**Objective:** Verify complete workflow from start through plan approval

**Steps:**
```bash
# 1. Start the server (in separate terminal)
cd /Users/ka/github/existential-birds/amelia
uv run amelia server

# 2. Start workflow
cd /Users/ka/github/anderskev-dot-com
uv run amelia start 2

# 3. Check status
uv run amelia status

# 4. Open dashboard
open http://localhost:8420
```

**Expected Result:**
- Workflow appears in dashboard with "Planning" status
- Architect generates plan
- Status changes to "Awaiting Approval"
- Plan is visible in dashboard

---

### TC-03: Plan Approval via CLI

**Objective:** Verify CLI approval triggers developer execution

**Steps:**
```bash
cd /Users/ka/github/anderskev-dot-com

# Wait for workflow to reach approval state, then:
uv run amelia approve
```

**Expected Result:**
- Approval message displayed
- Developer agent starts executing
- Tool calls visible in dashboard activity log
- Status shows "Executing"

---

### TC-04: Plan Approval via Dashboard

**Objective:** Verify dashboard approval works

**Steps:**
1. Start a new workflow: `uv run amelia start 2`
2. Open dashboard: `open http://localhost:8420`
3. Navigate to workflow detail page
4. Click "Approve" button when plan is ready

**Expected Result:**
- Approval controls visible when blocked
- Click triggers workflow resume
- Real-time status update in dashboard

---

### TC-05: Plan Rejection

**Objective:** Verify plan rejection with feedback

**Steps:**
```bash
cd /Users/ka/github/anderskev-dot-com

# Start workflow and wait for approval state
uv run amelia start 2

# Reject with feedback
uv run amelia reject "Focus on performance optimization instead of adding new features"
```

**Expected Result:**
- Rejection message displayed
- Feedback sent to architect
- (If re-planning supported) New plan generated incorporating feedback

---

### TC-06: Developer Agentic Execution

**Objective:** Verify developer agent executes autonomously with tool use

**Steps:**
1. Complete TC-03 (approve a plan)
2. Watch dashboard activity log
3. Monitor tool calls in real-time

**Expected Result:**
- Developer makes autonomous decisions
- Tool calls captured (Read, Edit, Bash, Glob, Grep)
- Tool results displayed
- Final response summarizes changes
- Files actually modified in repository

**Verify:**
```bash
cd /Users/ka/github/anderskev-dot-com
git status
git diff
```

---

### TC-07: Review Loop

**Objective:** Verify reviewer analyzes changes and loops if needed

**Steps:**
1. Let developer complete execution
2. Watch for reviewer activation
3. Check review results in dashboard

**Expected Result:**
- Reviewer analyzes code changes
- Issues categorized by severity
- If issues found, loops back to developer
- If approved, workflow completes

---

### TC-08: Local Review Command

**Objective:** Verify review of uncommitted local changes

**Steps:**
```bash
cd /Users/ka/github/anderskev-dot-com

# Make a test change
echo "// TODO: fix this" >> src/pages/index.js

# Run local review
uv run amelia review --local

# Clean up
git checkout src/pages/index.js
```

**Expected Result:**
- Review workflow created
- Stream events display in terminal
- Reviewer analyzes the diff
- Issues reported with severity

---

### TC-09: Dashboard Real-Time Updates

**Objective:** Verify WebSocket streaming works

**Steps:**
1. Open dashboard: `open http://localhost:8420`
2. Start a workflow in terminal
3. Watch dashboard for real-time updates

**Expected Result:**
- Activity log updates in real-time
- Agent progress bar advances through stages
- No page refresh needed
- Events include agent_start, tool_use, tool_result, agent_end

---

### TC-10: Workflow Cancellation

**Objective:** Verify workflow can be cancelled

**Steps:**
```bash
cd /Users/ka/github/anderskev-dot-com

# Start a workflow
uv run amelia start 2

# Cancel it
uv run amelia cancel
```

**Expected Result:**
- Cancellation confirmed
- Workflow status shows cancelled
- No orphaned processes

---

### TC-11: Error Recovery

**Objective:** Verify graceful handling of errors

**Steps:**
```bash
# Test without server running
pkill -f "amelia server" || true
cd /Users/ka/github/anderskev-dot-com
uv run amelia start 2
```

**Expected Result:**
- Clear error message: "Server not reachable"
- Helpful guidance: "Start the server: amelia server"
- Clean exit (no stack traces)

---

### TC-12: Status Command

**Objective:** Verify status display

**Steps:**
```bash
cd /Users/ka/github/anderskev-dot-com

# Check current worktree status
uv run amelia status

# Check all worktrees
uv run amelia status --all
```

**Expected Result:**
- Table shows workflow ID, issue, status, elapsed time
- Current worktree filter works
- --all flag shows all workflows

---

## Test Environment Cleanup

After testing:
```bash
# Stop server
pkill -f "amelia server"

# Reset test repo changes
cd /Users/ka/github/anderskev-dot-com
git checkout -- .
rm -rf docs/plans/

# Clean up any test branches
git branch -D test-* 2>/dev/null || true
```

---

## Test Result Template

| Test ID | Description | Status | Notes |
|---------|-------------|--------|-------|
| TC-01 | Plan Generation | [ ] Pass / [ ] Fail | |
| TC-02 | Full Workflow - Start to Approval | [ ] Pass / [ ] Fail | |
| TC-03 | Plan Approval via CLI | [ ] Pass / [ ] Fail | |
| TC-04 | Plan Approval via Dashboard | [ ] Pass / [ ] Fail | |
| TC-05 | Plan Rejection | [ ] Pass / [ ] Fail | |
| TC-06 | Developer Agentic Execution | [ ] Pass / [ ] Fail | |
| TC-07 | Review Loop | [ ] Pass / [ ] Fail | |
| TC-08 | Local Review Command | [ ] Pass / [ ] Fail | |
| TC-09 | Dashboard Real-Time Updates | [ ] Pass / [ ] Fail | |
| TC-10 | Workflow Cancellation | [ ] Pass / [ ] Fail | |
| TC-11 | Error Recovery | [ ] Pass / [ ] Fail | |
| TC-12 | Status Command | [ ] Pass / [ ] Fail | |

---

## Key Changes Being Tested

1. **CLI Driver** (`amelia/drivers/cli/claude.py`): Uses `claude-agent-sdk` with `ClaudeSDKClient`
2. **API Driver** (`amelia/drivers/api/deepagents.py`): Uses `deepagents` with LangChain
3. **Evaluator Agent** (`amelia/agents/evaluator.py`): New decision matrix evaluation
4. **Orchestrator** (`amelia/core/orchestrator.py`): Simplified graph flow
5. **Dashboard**: Removed batch execution components, simplified UI
