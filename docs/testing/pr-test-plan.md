# Token Usage Tracking Manual Testing Plan

**Branch:** `feat/token-usage-tracking`
**Feature:** Persist and display token usage, cost, and duration data from CLI driver executions

## Overview

This PR implements token usage tracking for Amelia workflows. The changes include:
1. **Backend**: TokenUsage model with `duration_ms` and `num_turns`, database schema updates, repository methods for save/get/summarize
2. **API**: Updated response models to include token summaries in workflow detail and list endpoints
3. **Frontend**: UsageCard component on workflow detail page, and Duration/Tokens/Cost columns on history page

Manual testing is needed to verify the complete data flow from CLI driver execution through database persistence to dashboard display.

---

## Test Environment

**Test Repository:** `/Users/ka/github/anderskev-dot-com`
**Test Issue:** GitHub Issue #4
**Profile:** `dev` (cli:claude driver with github tracker)

---

## Prerequisites

### Environment Setup

```bash
# 1. Install Python dependencies
cd /Users/ka/github/existential-birds/amelia-feature
uv sync

# 2. Delete existing database (schema changed)
rm -f ~/.amelia/amelia.db

# 3. Start the backend server
uv run amelia server --reload
# Server runs on http://localhost:8420 by default

# 4. Build and verify dashboard (served by backend)
cd dashboard
pnpm install
pnpm build
cd ..

# 5. Verify setup - server should be accessible
curl http://localhost:8420/api/health

# 6. Navigate to test repository
cd /Users/ka/github/anderskev-dot-com
```

### Testing Tools

- `curl` or a REST client (Postman, HTTPie) for API testing
- Web browser for dashboard testing
- SQLite CLI (`sqlite3`) for direct database verification

---

## Test Scenarios

### TC-01: Run Full Workflow and Verify Token Capture

**Objective:** Verify token usage is captured from CLI driver during a complete workflow execution

**Steps:**
1. Navigate to the test repository
2. Start a workflow using the CLI with the `cli:claude` driver for GitHub issue #4
3. Wait for the workflow to complete (approve the plan when prompted)
4. Check the database for token usage records

**Expected Result:**
- Token usage records exist in `token_usage` table for each agent (architect, developer, reviewer)
- Each record contains non-zero values for `input_tokens`, `output_tokens`, `cost_usd`, `duration_ms`
- `num_turns` reflects the actual conversation turns

**Verification Commands:**
```bash
# Navigate to test repository
cd /Users/ka/github/anderskev-dot-com

# Start a workflow for GitHub issue #4
uv run amelia start 4

# After completion, verify database records
sqlite3 ~/.amelia/amelia.db "SELECT agent, input_tokens, output_tokens, cost_usd, duration_ms, num_turns FROM token_usage ORDER BY timestamp"
```

---

### TC-02: Verify API Returns Token Summary in Workflow Detail

**Objective:** Verify `/workflows/{id}` endpoint includes `token_usage` field with correct aggregated data

**Steps:**
1. Complete a workflow (use result from TC-01 or create new one)
2. Get the workflow ID from the database
3. Call the workflow detail endpoint
4. Verify response includes `token_usage` with correct totals and breakdown

**Expected Result:**
- Response contains `token_usage` object with:
  - `total_input_tokens`, `total_output_tokens`, `total_cache_read_tokens`
  - `total_cost_usd`, `total_duration_ms`, `total_turns`
  - `breakdown` array with per-agent TokenUsage records

**Verification Commands:**
```bash
# Get workflow ID
WORKFLOW_ID=$(sqlite3 ~/.amelia/amelia.db "SELECT id FROM workflows ORDER BY started_at DESC LIMIT 1")

# Fetch workflow detail
curl -s "http://localhost:8420/api/workflows/$WORKFLOW_ID" | jq '.token_usage'
```

---

### TC-03: Verify API Returns Token Data in Workflow List

**Objective:** Verify `/workflows` endpoint includes token summary fields for each workflow

**Steps:**
1. Ensure at least one workflow exists with token data
2. Call the workflow list endpoint
3. Verify each workflow includes `total_cost_usd`, `total_tokens`, `total_duration_ms`

**Expected Result:**
- Response workflows array includes for each workflow:
  - `total_cost_usd`: number (sum of all agent costs)
  - `total_tokens`: number (sum of input + output tokens)
  - `total_duration_ms`: number (sum of agent durations)
- All values are non-null for workflows with token data

**Verification Commands:**
```bash
curl -s "http://localhost:8420/api/workflows" | jq '.workflows[] | {issue_id, total_cost_usd, total_tokens, total_duration_ms}'
```

---

### TC-04: Verify History Page Displays Token Columns

**Objective:** Verify the History page shows Duration, Tokens, and Cost columns

**Steps:**
1. Open the dashboard in a browser (http://localhost:8420)
2. Navigate to the History page
3. Verify the table displays three new columns: Duration, Tokens, Cost
4. Verify data formatting:
   - Duration: `Xm Ys` format (e.g., "2m 34s")
   - Tokens: `X.XK` format for thousands (e.g., "15.2K")
   - Cost: `$X.XX` format (e.g., "$0.42")

**Expected Result:**
- History page displays workflow list with Duration, Tokens, Cost columns
- Completed workflows show formatted values
- Pending/in-progress workflows show "-" for columns without data

**Verification Commands:**
```bash
# Open in browser
open http://localhost:8420/history
```

---

### TC-05: Verify Workflow Detail Page Shows Usage Card

**Objective:** Verify the Usage card appears on workflow detail page with breakdown table

**Steps:**
1. Open the dashboard in a browser
2. Navigate to a completed workflow's detail page
3. Verify the USAGE card displays:
   - Summary line: Cost | Tokens | Duration | Turns
   - Table with columns: Agent, Input, Output, Cache, Cost, Time
   - Rows for each agent (architect, developer, reviewer)

**Expected Result:**
- USAGE card visible below GOAL section
- Summary line shows aggregated totals
- Table shows breakdown by agent with correct values

**Verification Commands:**
```bash
# Get a workflow ID
WORKFLOW_ID=$(sqlite3 ~/.amelia/amelia.db "SELECT id FROM workflows ORDER BY started_at DESC LIMIT 1")

# Open in browser
open "http://localhost:8420/workflows/$WORKFLOW_ID"
```

---

### TC-06: Verify Usage Card Hidden When No Token Data

**Objective:** Verify the Usage card is hidden for workflows without token data

**Steps:**
1. Create a workflow that fails before any agent runs (e.g., invalid issue)
2. Navigate to that workflow's detail page
3. Verify no USAGE card is displayed

**Expected Result:**
- Workflow detail page loads without errors
- No USAGE card section is visible
- Other sections (GOAL, PIPELINE) display normally

---

### TC-07: Verify Formatting Edge Cases

**Objective:** Verify correct formatting for various numeric values

**Steps:**
1. Check formatting for various token counts:
   - Small values (<1000): should show exact number (e.g., "500")
   - Exactly 1000: should show "1K"
   - Thousands with decimals: should show 1 decimal (e.g., "1.5K")
   - Round thousands: should omit decimal (e.g., "2K" not "2.0K")
2. Check duration formatting:
   - <60 seconds: "Xs" format
   - >=60 seconds: "Xm Ys" format
   - Round minutes: "Xm" (no "0s")
3. Check cost formatting:
   - Always 2 decimal places: "$0.42", "$1.00"

**Expected Result:**
- All numeric displays follow the specified formatting rules

**Verification Commands:**
```bash
# Run unit tests for formatting functions
cd dashboard
pnpm test:run src/utils/__tests__/workflow.test.ts
```

---

## Test Environment Cleanup

After testing:
```bash
# Stop the server (Ctrl+C in terminal running server)

# Reset test repository changes
cd /Users/ka/github/anderskev-dot-com
git checkout -- .
rm -rf docs/plans/

# Optionally reset database for fresh testing
rm -f ~/.amelia/amelia.db
```

---

## Test Result Template

| Test ID | Description | Status | Notes |
|---------|-------------|--------|-------|
| TC-01 | Run workflow, verify token capture | [ ] Pass / [ ] Fail | |
| TC-02 | API workflow detail includes token_usage | [ ] Pass / [ ] Fail | |
| TC-03 | API workflow list includes token fields | [ ] Pass / [ ] Fail | |
| TC-04 | History page displays token columns | [ ] Pass / [ ] Fail | |
| TC-05 | Workflow detail shows Usage card | [ ] Pass / [ ] Fail | |
| TC-06 | Usage card hidden when no data | [ ] Pass / [ ] Fail | |
| TC-07 | Formatting edge cases correct | [ ] Pass / [ ] Fail | |

---

## Agent Execution Notes

### For LLM Agent Executing This Plan:

1. **Database reset required** - Delete `~/.amelia/amelia.db` before testing (schema changed)
2. **Execute tests sequentially** - TC-01 creates data needed for TC-02 through TC-05
3. **Capture output** - Log API responses and database queries for verification
4. **Mark results** - Update the result template after each test
5. **Report issues** - Note any failures with exact error messages

### Programmatic Verification:

```python
# Verify token usage in database
import sqlite3
conn = sqlite3.connect(os.path.expanduser("~/.amelia/amelia.db"))
cursor = conn.execute("""
    SELECT agent, input_tokens, output_tokens, cost_usd, duration_ms, num_turns
    FROM token_usage
    ORDER BY timestamp
""")
for row in cursor:
    print(f"Agent: {row[0]}, In: {row[1]}, Out: {row[2]}, Cost: ${row[3]:.2f}, Duration: {row[4]}ms, Turns: {row[5]}")
```

---

## Key Changes in This Branch

The following changes should be verified through testing:

1. **Backend - TokenUsage model** (`amelia/server/models/tokens.py`):
   - Added `duration_ms` and `num_turns` fields
   - Made `cost_usd` required

2. **Backend - Orchestrator** (`amelia/core/orchestrator.py`):
   - `_save_token_usage()` helper extracts usage from driver and persists

3. **Backend - Repository** (`amelia/server/database/repository.py`):
   - `save_token_usage()` - insert token usage record
   - `get_token_usage()` - fetch per-workflow usage
   - `get_token_summary()` - aggregate usage into summary

4. **Backend - API Routes** (`amelia/server/routes/workflows.py`):
   - `/workflows/{id}` includes `token_usage` field
   - `/workflows` includes summary fields in each workflow

5. **Frontend - History Page** (`dashboard/src/pages/HistoryPage.tsx`):
   - Added Duration, Tokens, Cost columns with formatting

6. **Frontend - Workflow Detail** (`dashboard/src/pages/WorkflowDetailPage.tsx`):
   - Added UsageCard component

7. **Frontend - UsageCard** (`dashboard/src/components/UsageCard.tsx`):
   - New component showing summary + breakdown table
