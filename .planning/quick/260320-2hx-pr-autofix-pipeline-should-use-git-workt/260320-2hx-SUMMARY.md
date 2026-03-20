---
phase: quick-260320-2hx
plan: 01
subsystem: pr-auto-fix
tags: [git, worktree, isolation, orchestrator]
dependency_graph:
  requires: []
  provides: [worktree-isolation]
  affects: [pr-auto-fix-pipeline]
tech_stack:
  added: []
  patterns: [async-context-manager, git-worktree]
key_files:
  created:
    - tests/unit/tools/test_git_utils.py
  modified:
    - amelia/tools/git_utils.py
    - amelia/pipelines/pr_auto_fix/orchestrator.py
    - tests/unit/pipelines/pr_auto_fix/test_orchestrator.py
    - tests/unit/pipelines/pr_auto_fix/conftest.py
    - tests/integration/test_pr_autofix_flow.py
decisions:
  - Detached HEAD mode for worktrees avoids creating conflicting local branch names
  - Repo lock removed from fix cycle since worktrees are inherently isolated
  - Empty head_branch skips worktree creation for backward compatibility
metrics:
  duration: 9m
  completed: 2026-03-20T06:00:21Z
  tasks: 3/3
  tests_passed: 2219
  tests_failed: 0
---

# Quick Task 260320-2hx: PR Autofix Pipeline Worktree Isolation Summary

LocalWorktree async context manager creates isolated git worktrees per PR fix cycle, preventing branch switching in the user's main checkout.

## What Changed

### Task 1: LocalWorktree async context manager (TDD)
Added `LocalWorktree` class to `amelia/tools/git_utils.py` with:
- Creates worktree at `{repo_root}/../.amelia-worktrees/{worktree_id}`
- `__aenter__`: fetches origin, runs `git worktree add --detach`, returns path
- `__aexit__`: forces removal with fallback to `shutil.rmtree` + prune
- Stale worktree cleanup on entry
- Module-level `_run_git_cmd` helper to avoid subprocess boilerplate

4 tests: create/cleanup lifecycle, stale removal, exception safety, bad branch error.

**Commits:** `6efb1a73` (RED), `d1876369` (GREEN)

### Task 2: Wire worktree into orchestrator
Modified `_run_fix_cycle` in `orchestrator.py`:
- Uses `async with LocalWorktree(...)` to create isolated worktree per cycle
- Creates `wt_profile = profile.model_copy(update={"repo_root": worktree_path})` before pipeline execution
- All downstream nodes (commit_push, reply_resolve, Developer agent) automatically use the worktree path via the overridden profile
- Empty `head_branch` skips worktree creation (backward compatibility)
- Removed repo lock from fix cycle (worktrees are isolated; no branch switching contention)

Updated test infrastructure: `mock_local_worktree` fixture, 3 new worktree integration tests, removed obsolete `_reset_to_remote` tests.

**Commit:** `bc8d3000`

### Task 3: Full suite verification
- Fixed 2 ruff SIM105 lint issues (contextlib.suppress)
- Updated integration test `test_pr_autofix_flow.py` to mock `LocalWorktree`
- Full suite: 2219 passed, 0 failed, ruff clean, mypy clean

**Commit:** `4341c168`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Integration test needed LocalWorktree mock**
- **Found during:** Task 3
- **Issue:** `test_trigger_fix_cycle_runs_pipeline_with_comments` failed because it patched `GitOperations` but not `LocalWorktree`
- **Fix:** Added `LocalWorktree` mock patch to the integration test's context manager stack
- **Files modified:** `tests/integration/test_pr_autofix_flow.py`
- **Commit:** `4341c168`

## Decisions Made

1. **Detached HEAD for worktrees**: Using `--detach` avoids creating local branch names like `origin/feat/test` that could conflict across concurrent fix cycles.
2. **Removed repo lock from fix cycle**: Since each PR fix now runs in its own worktree, there is no branch-switching contention. The repo lock was only needed when multiple PRs shared the same checkout.
3. **Backward compatibility**: Empty `head_branch` (the deferred-checkout case) bypasses worktree creation entirely, preserving existing behavior.
