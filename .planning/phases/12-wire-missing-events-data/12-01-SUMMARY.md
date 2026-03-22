---
phase: 12-wire-missing-events-data
plan: 01
subsystem: events
tags: [event-bus, websocket, dashboard, pr-auto-fix, typescript]

# Dependency graph
requires:
  - phase: 06-pr-autofix-orchestration
    provides: orchestrator with _emit_event pattern and EventType enum
  - phase: 09-dashboard-pr-autofix
    provides: frontend EventType union and workflow record creation
provides:
  - pr_title forwarding from API trigger to orchestrator
  - PR_COMMENTS_DETECTED event emission in poller
  - PR_COMMENTS_RESOLVED event emission in orchestrator
  - pr_auto_fix_failed in frontend EventType union
affects: [dashboard, pr-auto-fix, event-streaming]

# Tech tracking
tech-stack:
  added: []
  patterns: [event emission before fire-and-forget dispatch, resolution counting from pipeline state]

key-files:
  created: []
  modified:
    - amelia/server/routes/github.py
    - amelia/server/lifecycle/pr_poller.py
    - amelia/pipelines/pr_auto_fix/orchestrator.py
    - dashboard/src/types/index.ts
    - tests/unit/server/routes/test_github_pr_routes.py
    - tests/unit/server/lifecycle/test_pr_poller.py
    - tests/unit/pipelines/pr_auto_fix/test_orchestrator.py

key-decisions:
  - "Emit PR_COMMENTS_DETECTED before fire-and-forget dispatch so event is guaranteed even if pipeline fails"
  - "Compute resolution_results_raw at higher scope to avoid duplicate computation in metrics block"
  - "Conditional PR_COMMENTS_RESOLVED emission (only when resolved_count > 0) to avoid noisy no-op events"

patterns-established:
  - "Event emission before async dispatch: emit detection events before fire-and-forget task creation"

requirements-completed: [TRIG-03, DASH-01, DASH-03, DASH-04]

# Metrics
duration: 4min
completed: 2026-03-22
---

# Phase 12 Plan 01: Wire Missing Events & Data Summary

**Close four audit gaps: pr_title forwarding, PR_COMMENTS_DETECTED/RESOLVED event emission, and pr_auto_fix_failed frontend type**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-22T01:51:52Z
- **Completed:** 2026-03-22T01:55:25Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- API trigger endpoint now forwards pr_summary.title to orchestrator so dashboard shows real PR titles
- PR comment poller emits PR_COMMENTS_DETECTED event with pr_number, comment_count, and pr_title
- Orchestrator emits PR_COMMENTS_RESOLVED event with resolved_count and total_count after successful pipeline
- Frontend EventType union includes pr_auto_fix_failed for complete backend event coverage

## Task Commits

Each task was committed atomically (TDD: RED then GREEN):

1. **Task 1: Wire pr_title forwarding and PR_COMMENTS_DETECTED event**
   - `4944a329` (test: failing tests for pr_title forwarding and PR_COMMENTS_DETECTED)
   - `cb7fe692` (feat: wire pr_title forwarding and PR_COMMENTS_DETECTED event emission)
2. **Task 2: Emit PR_COMMENTS_RESOLVED and add pr_auto_fix_failed to frontend types**
   - `ffba50a5` (test: failing tests for PR_COMMENTS_RESOLVED event emission)
   - `b11e4a86` (feat: emit PR_COMMENTS_RESOLVED event and add pr_auto_fix_failed to frontend types)

## Files Created/Modified
- `amelia/server/routes/github.py` - Added pr_title=pr_summary.title to trigger_fix_cycle call
- `amelia/server/lifecycle/pr_poller.py` - Added PR_COMMENTS_DETECTED event emission before dispatch
- `amelia/pipelines/pr_auto_fix/orchestrator.py` - Added PR_COMMENTS_RESOLVED event emission after pipeline success
- `dashboard/src/types/index.ts` - Added pr_auto_fix_failed to EventType union
- `tests/unit/server/routes/test_github_pr_routes.py` - Test for pr_title forwarding
- `tests/unit/server/lifecycle/test_pr_poller.py` - Test for PR_COMMENTS_DETECTED emission, fixed mock_orchestrator fixture
- `tests/unit/pipelines/pr_auto_fix/test_orchestrator.py` - Tests for PR_COMMENTS_RESOLVED emission

## Decisions Made
- Emit PR_COMMENTS_DETECTED before fire-and-forget dispatch so the event is guaranteed even if the pipeline task fails
- Compute resolution_results_raw at a higher scope in _execute_pipeline to avoid duplicate computation with the metrics block
- Only emit PR_COMMENTS_RESOLVED when resolved_count > 0 to avoid noisy no-op events

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed mock_orchestrator fixture in test_pr_poller.py**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** mock_orchestrator used AsyncMock() which made get_workflow_id() return a coroutine instead of a UUID, causing pydantic ValidationError
- **Fix:** Set get_workflow_id as MagicMock (sync) with return_value=UUID on the fixture
- **Files modified:** tests/unit/server/lifecycle/test_pr_poller.py
- **Verification:** All 44 poller tests pass
- **Committed in:** cb7fe692 (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Mock fixture correction required for test compatibility with new event emission code. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All four v1.0 audit gaps are closed
- Dashboard can now render all backend event types without unknown-type fallback
- Event streams include comment detection and resolution lifecycle events

---
*Phase: 12-wire-missing-events-data*
*Completed: 2026-03-22*
