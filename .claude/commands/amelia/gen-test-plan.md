---
description: generate manual test plan for PR (auto-posted by amelia-qa action)
---

# Generate Manual Test Plan

Generate a manual test plan for the current PR that will be auto-posted as a PR comment by the `amelia-qa` GitHub Action.

## Instructions

1. **Analyze the changes** in this branch compared to main:
   ```bash
   git log --oneline main..HEAD
   git diff --stat main..HEAD
   ```

2. **Identify testable functionality** - focus on:
   - New features or commands
   - Changed behavior
   - Integration points
   - Edge cases that automated tests can't cover
   - User-facing workflows

3. **Write the test plan** to `docs/testing/pr-test-plan.md` using the template below.

4. **Guidelines:**
   - Only include tests that require manual verification (not automated test coverage)
   - Be specific with commands and expected output
   - Include setup/teardown if needed
   - Keep it concise - focus on what's changed

5. **After PR merges:** Delete `docs/testing/pr-test-plan.md` (it's preserved in the PR comment)

---

## Template

```markdown
# {Feature Name} Manual Testing Plan

**Branch:** `{branch_name}`
**Feature:** {Brief description of the feature being tested}

## Overview

{Detailed description of what this PR changes and why manual testing is needed. Explain the key functionality being added or modified.}

---

## Prerequisites

### Environment Setup

```bash
# 1. Install dependencies
cd /Users/ka/github/amelia
uv sync

# 2. Start the server (if needed)
uv run amelia-server start --reload

# 3. Verify setup
{verification command}
```

### Testing Tools

{List any tools needed for testing with installation instructions}

---

## Test Scenarios

### TC-01: {Test Case Name}

**Objective:** {What this test verifies}

**Steps:**
1. {Step 1}
2. {Step 2}
3. {Step 3}

**Expected Result:**
- {Expected outcome 1}
- {Expected outcome 2}

**Verification Commands:**
```bash
{Command to run the test}
```

---

### TC-02: {Next Test Case}

**Objective:** {What this test verifies}

**Steps:**
1. {Step 1}
2. {Step 2}

**Expected Result:**
- {Expected outcome}

**Verification Commands:**
```bash
{Command to run the test}
```

---

{Continue with TC-03, TC-04, etc. for each test scenario}

---

## Test Environment Cleanup

After testing:
```bash
# Stop any running processes
{cleanup commands}

# Reset state if needed
{reset commands}
```

---

## Test Result Template

| Test ID | Description | Status | Notes |
|---------|-------------|--------|-------|
| TC-01 | {Description} | [ ] Pass / [ ] Fail | |
| TC-02 | {Description} | [ ] Pass / [ ] Fail | |
{Add rows for each test case}

---

## Agent Execution Notes

### For LLM Agent Executing This Plan:

1. **{Setup step}** - {Details}
2. **Execute tests sequentially** - Some tests may depend on state
3. **Capture output** - Log important verification data
4. **Mark results** - Update the result template after each test
5. **Report issues** - Note any failures with exact error messages

{Add any code examples for programmatic testing if applicable}

---

## Key Changes in This Branch

The following changes should be verified through testing:

1. **{Change category 1}** (`{file path}`):
   - {Specific change to verify}
   - {Another change}

2. **{Change category 2}** (`{file path}`):
   - {Specific change to verify}
```
