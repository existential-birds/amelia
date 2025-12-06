---
description: execute a manual test plan in an isolated worktree and report failures
---
Execute the manual test plan at the specified path in an isolated git worktree.

## Arguments

$1 = Path to the test plan markdown file (e.g., `docs/testing/websocket-manual-testing-plan.md`)

## Workflow

### 1. Setup Test Worktree

Create an isolated worktree for test execution:

```bash
# Get current branch
BRANCH=$(git rev-parse --abbrev-ref HEAD)
WORKTREE_NAME="test-run-$(date +%Y%m%d-%H%M%S)"
WORKTREE_PATH="../amelia-${WORKTREE_NAME}"

# Create worktree from current branch
git worktree add "${WORKTREE_PATH}" "${BRANCH}"
cd "${WORKTREE_PATH}"

# Install dependencies
uv sync
```

### 2. Parse Test Plan

Read the test plan file and extract:
- **Prerequisites**: Setup commands that must run before tests
- **Test Cases**: Each `### TC-XX:` section is a test case
- **Verification Commands**: Code blocks with commands to execute
- **Expected Results**: What to verify after each test

### 3. Execute Tests

For each test case in the plan:

1. **Log the test case ID and name**
2. **Execute any setup/verification commands** from the test case
3. **Capture stdout, stderr, and exit codes**
4. **Compare against expected results**
5. **Record PASS/FAIL with evidence**

### 4. Generate Report

Create a markdown report at `docs/testing/test-run-{timestamp}.md`:

```markdown
# Test Plan Execution Report

**Plan:** {test_plan_path}
**Branch:** {branch_name}
**Worktree:** {worktree_path}
**Executed:** {timestamp}
**Duration:** {total_time}

## Summary

| Status | Count |
|--------|-------|
| PASS   | X     |
| FAIL   | Y     |
| SKIP   | Z     |

## Failed Tests

### TC-XX: {Test Name}

**Expected:** {expected result}
**Actual:** {actual result}
**Error:**
```
{error output}
```

## All Results

| Test ID | Name | Status | Duration | Notes |
|---------|------|--------|----------|-------|
| TC-01 | ... | PASS | 2.3s | |
| TC-02 | ... | FAIL | 1.1s | Connection refused |
```

### 5. Cleanup

```bash
# Return to original directory
cd -

# Remove test worktree
git worktree remove "${WORKTREE_PATH}" --force
```

## Execution Notes

- **Server-dependent tests**: If the plan requires a running server, start it in the worktree before running tests
- **Interactive tests**: Skip tests marked as requiring manual interaction, mark as SKIP
- **Timing-sensitive tests**: Tests with "wait X seconds" should use appropriate sleeps
- **Cleanup on failure**: Always remove the worktree even if tests fail
- **Parallel safety**: Each test run uses a unique worktree name

## Example Usage

```
/ka-run-test-plan docs/testing/websocket-manual-testing-plan.md
```

## Output

The command produces:
1. Console output showing test progress
2. A markdown report file at `docs/testing/test-run-{timestamp}.md`
3. Summary of pass/fail counts
