---
phase: 11-fix-streaming-stage-events
plan: 01
subsystem: streaming
tags: [websocket, events, cli, streaming, workflow-summary]

# Dependency graph
requires:
  - phase: 06-pr-autofix-orchestrator
    provides: PR auto-fix orchestrator with _emit_event helper and pipeline execution
provides:
  - PR auto-fix terminal events in streaming terminal set (stream_workflow_events exits on pr_auto_fix_completed/failed)
  - Stage event emission from orchestrator after pipeline execution for WorkflowSummary counters
  - EventFormat entries for PR auto-fix completed/failed display
affects: [cli, watch-pr, fix-pr, dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Post-invocation stage event emission: reconstruct per-node events from final state when using ainvoke"
    - "Per-comment stage_completed emission: one event per comment_id for accurate WorkflowSummary counting"

key-files:
  created: []
  modified:
    - amelia/client/streaming.py
    - amelia/pipelines/pr_auto_fix/orchestrator.py
    - tests/unit/client/test_streaming_summary.py
    - tests/unit/pipelines/pr_auto_fix/test_orchestrator.py

key-decisions:
  - "Post-invocation stage emission over astream: lower risk than switching pipeline execution model"
  - "One stage_completed per comment_id not per group: ensures WorkflowSummary counters match actual comment count"
  - "Map no_changes to skipped: client-side expects fixed/skipped/failed, pipeline uses no_changes internally"

patterns-established:
  - "Post-invocation stage event reconstruction: emit synthetic stage_completed events after ainvoke returns"

requirements-completed: [TRIG-01, TRIG-02]

# Metrics
duration: 4min
completed: 2026-03-22
---

# Phase 11 Plan 01: Fix Streaming Stage Events Summary

**PR auto-fix terminal events added to streaming terminal set and stage_completed events emitted from orchestrator for WorkflowSummary counters**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-22T00:55:04Z
- **Completed:** 2026-03-22T00:58:42Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- stream_workflow_events now terminates on pr_auto_fix_completed and pr_auto_fix_failed events
- commit_sha extracted from pr_auto_fix_completed event data for WorkflowSummary
- PR auto-fix orchestrator emits stage_completed events with per-comment result status after pipeline execution
- no_changes status mapped to skipped for client compatibility
- All 2218 unit tests pass, no lint or type errors

## Task Commits

Each task was committed atomically:

1. **Task 1: Add PR auto-fix terminal events to streaming terminal set** - `2e2c6ba6` (feat)
2. **Task 2: Emit stage_completed events from PR auto-fix orchestrator** - `6e392ece` (feat)
3. **Lint fix** - `6e5e7f3a` (chore)

## Files Created/Modified
- `amelia/client/streaming.py` - Added pr_auto_fix_completed/failed to terminal set, commit_sha extraction, EventFormat entries
- `amelia/pipelines/pr_auto_fix/orchestrator.py` - Added _emit_stage_events method for post-invocation stage event emission
- `tests/unit/client/test_streaming_summary.py` - 3 new tests for PR auto-fix terminal behavior
- `tests/unit/pipelines/pr_auto_fix/test_orchestrator.py` - 2 new tests for stage_completed emission

## Decisions Made
- Used post-invocation stage event emission (reconstruct from final state) rather than switching to astream -- lower risk, simpler
- Emit one stage_completed per comment_id rather than per group -- ensures WorkflowSummary fixed/skipped/failed counters match actual comment outcomes
- Map GroupFixStatus.NO_CHANGES to "skipped" in client-facing events

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- fix-pr and watch-pr CLI commands will now receive terminal events and exit cleanly
- WorkflowSummary counters will reflect actual per-comment pipeline outcomes
- Ready for end-to-end CLI testing

---
*Phase: 11-fix-streaming-stage-events*
*Completed: 2026-03-22*
