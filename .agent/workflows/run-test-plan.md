---
name: run-test-plan
description: Protocol for executing manual test plans with isolation and evidence collection.
---

# Test Plan Execution

**Role:** QA Tester.
**Objective:** Execute tests faithfully and document evidence.

## 🚧 Phase 1: Isolation (Safety First)

**Never test on a dirty state.**

1.  **Worktree Setup:**
    *   Run tests in a clean `git worktree` or fresh environment if possible.
    *   Ensure database is seeded/migrated to the correct version.

2.  **Dependencies:**
    *   Run `uv sync` or `npm install` to match the exact branch state.

## ⚡️ Phase 2: Execution Loop

For each Test Case in the Plan:

1.  **Setup:** Establish pre-conditions.
2.  **Action:** Perform the steps exactly. **Do not improvise.**
3.  **Observation:**
    *   Does the result match the Expected Result?
    *   **If YES:** Mark `[PASS]`.
    *   **If NO:** Mark `[FAIL]`. Record *exactly* what happened (screenshot, error message).

4.  **Evidence Collection:**
    *   If the test requires a backend check, run the query and paste the output.

## 📊 Phase 3: Reporting

Create `docs/testing/test-run-{YYYYMMDD}.md`.

### Summary
*   **Total Tests:** N
*   **Passed:** X (Green)
*   **Failed:** Y (Red)

### Defect Report (If Failures)
*   For each failure, link to the Code Review workflow: "Major functional regression found in TC-03."

### Teardown
*   Clean up test artifacts, drop test DBs, remove worktree.
