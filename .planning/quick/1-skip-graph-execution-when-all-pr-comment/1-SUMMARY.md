---
phase: quick-1
plan: 01
subsystem: pr-poller
tags: [polling, dedup, performance]
dependency_graph:
  requires: []
  provides: [processed-comment-tracking]
  affects: [pr_poller]
tech_stack:
  added: []
  patterns: [set-based-dedup, per-key-tracking]
key_files:
  created: []
  modified:
    - amelia/server/lifecycle/pr_poller.py
    - tests/unit/server/lifecycle/test_pr_poller.py
decisions:
  - "_processed_comments keyed by (profile.name, pr.number) tuple for per-profile per-PR isolation"
  - "Replace (not union) processed set on each dispatch to track only currently unresolved comments"
  - "Pop key on empty comments to reset tracking when PR is fully resolved"
metrics:
  duration: 3min
  completed: "2026-03-16"
---

# Quick Task 1: Skip Graph Execution When All PR Comments Already Processed

Per-PR processed comment ID tracking in PRCommentPoller to avoid redundant graph executions when the same unresolved comments persist between poll cycles.

## What Changed

### amelia/server/lifecycle/pr_poller.py

- Added `_processed_comments: dict[tuple[str, int], set[int]]` to `__init__` for tracking dispatched comment IDs per (profile, PR) pair
- In `_poll_profile`, after fetching comments for each PR:
  - Empty comments: pop the tracking key (reset for future re-trigger)
  - All current IDs already in processed set: skip dispatch with debug log
  - New IDs detected: proceed with dispatch, then replace the processed set with current IDs
- Debug log message "All comments already processed, skipping" for observability

### tests/unit/server/lifecycle/test_pr_poller.py

- `TestProcessedCommentTracking` class with 5 tests:
  - `test_all_processed_skips_graph_dispatch` -- second call with same IDs does not trigger
  - `test_new_comment_triggers_dispatch` -- new comment ID triggers despite prior processing
  - `test_first_call_records_processed_and_dispatches` -- first call dispatches and records IDs
  - `test_empty_comments_clears_processed_set` -- resolved PR clears tracking
  - `test_per_pr_isolation` -- PR #42 and PR #43 tracked independently

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 3879d2da | test | Add failing tests for processed comment tracking |
| 30bad19e | feat | Implement processed comment tracking in _poll_profile |

## Deviations from Plan

None -- plan executed exactly as written.

## Verification

- All 30 poller tests pass (25 existing + 5 new)
- ruff check: all checks passed
- mypy: no issues found

## Self-Check: PASSED
