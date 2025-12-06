# Manual Test Plan: CLI Thin Client Architecture

## Overview

This PR introduces a thin client architecture where CLI commands delegate workflow operations to the REST API server instead of running locally. The main changes include:

- New CLI commands: `start`, `approve`, `reject`, `status`, `cancel`
- REST API client (`amelia/client/api.py`) for server communication
- Git worktree detection (`amelia/client/git.py`) for automatic context
- Deprecation of local `start-local` command in favor of server-based `start`

Manual testing is needed because the end-to-end workflow involves user interactions, real git repositories, and server state that automated tests can't fully cover.

## Prerequisites

- [ ] Clean git worktree (no uncommitted changes that would interfere)
- [ ] Amelia server running (`amelia server`)
- [ ] Valid `settings.amelia.yaml` with at least one profile
- [ ] Access to a test issue ID (or use `noop` tracker with any ID)

## Test Cases

### 1. Server Connection Error Handling

**Purpose:** Verify helpful error messages when server is not running

**Steps:**
1. Stop the server if running
2. Run `amelia start TEST-123`
3. Run `amelia status`
4. Run `amelia approve`

**Expected Result:**
- Each command shows: `Error: Cannot connect to Amelia server...`
- Shows helpful message: `Start the server: amelia server`
- Exit code 1

### 2. Start Workflow Command

**Purpose:** Verify workflow creation via thin client

**Steps:**
1. Start server: `amelia server`
2. Navigate to a git repository
3. Run `amelia start TEST-123`
4. Run `amelia start TEST-123` again (same worktree)

**Expected Result:**
- First start: Shows success with workflow ID, issue ID, worktree path, status
- Shows dashboard URL hint
- Second start: Shows conflict error with active workflow info
- Suggests canceling or using different worktree

### 3. Status Command - Current Worktree

**Purpose:** Verify status shows workflow for current worktree only

**Steps:**
1. Start server and create a workflow (`amelia start TEST-123`)
2. Run `amelia status`
3. Navigate to a different directory (non-worktree)
4. Run `amelia status`

**Expected Result:**
- In worktree with active workflow: Shows table with workflow details
- In different directory: Shows "No active workflow" or error for non-git directory

### 4. Status Command - All Worktrees

**Purpose:** Verify `--all` flag shows workflows across worktrees

**Steps:**
1. Create workflows in multiple worktrees (if available)
2. Run `amelia status --all`
3. Run `amelia status -a`

**Expected Result:**
- Shows all active workflows in a formatted table
- Displays workflow ID, issue, status, worktree, started time
- Shows total count

### 5. Approve Command

**Purpose:** Verify plan approval works correctly

**Steps:**
1. Start a workflow that reaches "awaiting approval" state
2. Run `amelia approve`

**Expected Result:**
- Shows success: "Plan approved for workflow {id}"
- Workflow continues execution

**Edge Cases:**
- Run `amelia approve` when no workflow exists: Should show "No workflow active" error
- Run `amelia approve` when workflow is not awaiting approval: Should show "not awaiting approval" error

### 6. Reject Command

**Purpose:** Verify plan rejection with reason

**Steps:**
1. Start a workflow that reaches "awaiting approval" state
2. Run `amelia reject "The plan doesn't address the performance issue"`

**Expected Result:**
- Shows: "Plan rejected for workflow {id}"
- Shows the reason provided
- Message indicates architect will replan

**Edge Cases:**
- Run without a reason (should be required argument)
- Run when no workflow exists

### 7. Cancel Command

**Purpose:** Verify workflow cancellation with confirmation

**Steps:**
1. Start a workflow: `amelia start TEST-456`
2. Run `amelia cancel`
3. Respond "no" to confirmation
4. Run `amelia cancel` again
5. Respond "yes" to confirmation

**Expected Result:**
- First cancel (no): Shows "Cancelled." and exits
- Second cancel (yes): Shows "Workflow {id} cancelled"

**Force Flag:**
- Run `amelia cancel --force` or `amelia cancel -f`
- Should skip confirmation and cancel immediately

### 8. Git Worktree Detection

**Purpose:** Verify automatic worktree context detection

**Steps:**
1. Create a git worktree: `git worktree add ../test-worktree feature-branch`
2. Navigate to `../test-worktree`
3. Run `amelia start TEST-789`
4. Check the worktree_name in response

**Expected Result:**
- Worktree path correctly detected as absolute path
- Worktree name derived from branch name (`feature-branch`)

**Edge Cases:**
- Detached HEAD state: Should show `detached-{shorthash}`
- Bare repository: Should show clear error
- Non-git directory: Should show "Not inside a git repository"

### 9. Profile Selection

**Purpose:** Verify profile option works with thin client

**Steps:**
1. Run `amelia start TEST-123 --profile work`
2. Run `amelia start TEST-123 -p personal`

**Expected Result:**
- Profile is passed to server and used for workflow
- Invalid profile should show appropriate error from server

## Regression Checks

- [ ] `amelia start-local` still works (deprecated but functional)
- [ ] `amelia plan-only` still works independently
- [ ] `amelia review --local` still works independently
- [ ] `amelia server` starts correctly
- [ ] Pre-existing CLI help text is accurate

## Notes

- The server must be running for thin client commands (`start`, `approve`, `reject`, `status`, `cancel`)
- Legacy commands (`start-local`, `plan-only`, `review`) work without the server
- Worktree detection uses `git rev-parse` commands under the hood
- All thin client commands auto-detect the current git worktree context
