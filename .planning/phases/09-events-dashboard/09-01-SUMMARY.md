---
phase: 09-events-dashboard
plan: 01
subsystem: api
tags: [events, workflow-type, pydantic, orchestrator, dashboard-visibility]

# Dependency graph
requires:
  - phase: 06-orchestration
    provides: PRAutoFixOrchestrator with event emission and divergence recovery
  - phase: 08-polling
    provides: PR_POLL_RATE_LIMITED event type and poller integration
provides:
  - 5 new PR auto-fix lifecycle EventType values with correct classification
  - WorkflowType.PR_AUTO_FIX enum value
  - pipeline_type, pr_number, pr_title, pr_comment_count fields on WorkflowSummary
  - pipeline_type, pr_number, pr_title, pr_comment_count, pr_comments fields on WorkflowDetailResponse
  - Orchestrator creates workflow DB records visible in GET /api/workflows
  - PR comment resolution data persisted in issue_cache
affects: [09-02, 09-03, dashboard-frontend]

# Tech tracking
tech-stack:
  added: []
  patterns: [issue_cache as flexible metadata store for pipeline-specific data]

key-files:
  created:
    - tests/unit/server/test_event_filtering.py
  modified:
    - amelia/server/models/events.py
    - amelia/server/models/state.py
    - amelia/server/models/responses.py
    - amelia/server/routes/workflows.py
    - amelia/pipelines/pr_auto_fix/orchestrator.py
    - amelia/server/main.py
    - amelia/server/routes/github.py
    - tests/unit/pipelines/pr_auto_fix/test_orchestrator.py
    - tests/unit/server/models/test_events.py
    - tests/unit/server/routes/test_github_pr_routes.py
    - tests/unit/test_event_filtering.py

key-decisions:
  - "WorkflowRepository is optional param on PRAutoFixOrchestrator (backward compatible with existing callers)"
  - "PR title fetched via get_pr_summary with fallback to 'PR #{number}' on error"
  - "PR_COMMENTS_DETECTED and PR_COMMENTS_RESOLVED are non-persisted internal events (ephemeral signals)"
  - "issue_cache stores pr_number, pr_title, comment_count, pr_comments for WorkflowSummary/Detail consumption"
  - "Each _execute_pipeline call creates a fresh workflow_id (not the per-PR synthetic ID used for orchestration events)"

patterns-established:
  - "issue_cache pattern: store pipeline-specific metadata in issue_cache dict for flexible API response enrichment"
  - "Optional dependency injection: workflow_repo=None allows backward compatibility for callers that don't need DB tracking"

requirements-completed: [DASH-01, DASH-02, DASH-03, DASH-04]

# Metrics
duration: 12min
completed: 2026-03-14
---

# Phase 9 Plan 1: Backend PR Auto-Fix Dashboard Visibility Summary

**5 new event types, WorkflowType.PR_AUTO_FIX, pipeline_type + PR metadata on API responses, and orchestrator workflow DB record creation with comment resolution data**

## Performance

- **Duration:** 12 min
- **Started:** 2026-03-14T21:34:11Z
- **Completed:** 2026-03-14T21:46:11Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments
- Added 5 new EventType values (PR_COMMENTS_DETECTED, PR_AUTO_FIX_STARTED, PR_AUTO_FIX_COMPLETED, PR_COMMENTS_RESOLVED, PR_POLL_ERROR) with correct INFO/ERROR classification and persistence rules
- Extended WorkflowSummary and WorkflowDetailResponse with pipeline_type, pr_number, pr_title, pr_comment_count fields populated from workflow_type and issue_cache
- PRAutoFixOrchestrator now creates/updates workflow DB records, emits PR_AUTO_FIX_STARTED/COMPLETED lifecycle events, persists PR comment resolution data in issue_cache

## Task Commits

Each task was committed atomically:

1. **Task 1: Event types, WorkflowType, and response fields** - `afb2323b` (test) + `e61a9045` (feat)
2. **Task 2: Orchestrator workflow DB records** - `16d1fe11` (test) + `7a8201c7` (feat)

_TDD: each task has RED (test) and GREEN (implementation) commits_

## Files Created/Modified
- `amelia/server/models/events.py` - 5 new EventType values with classification in PERSISTED_TYPES, _ERROR_TYPES, _INFO_TYPES
- `amelia/server/models/state.py` - WorkflowType.PR_AUTO_FIX enum value
- `amelia/server/models/responses.py` - pipeline_type, pr_number, pr_title, pr_comment_count, pr_comments fields
- `amelia/server/routes/workflows.py` - Populate new fields from workflow_type and issue_cache in all WorkflowSummary/Detail constructions
- `amelia/pipelines/pr_auto_fix/orchestrator.py` - WorkflowRepository integration, lifecycle events, pr_comments building
- `amelia/server/main.py` - Pass workflow_repo to PRAutoFixOrchestrator
- `amelia/server/routes/github.py` - Pass workflow_repo via Depends(get_repository)
- `tests/unit/server/test_event_filtering.py` - 31 tests for event types, classifications, response fields
- `tests/unit/pipelines/pr_auto_fix/test_orchestrator.py` - 9 new tests for workflow records, events, failure handling

## Decisions Made
- WorkflowRepository is an optional parameter (None default) on PRAutoFixOrchestrator for backward compatibility
- PR title fetched via get_pr_summary with graceful fallback to "PR #{number}" on error
- PR_COMMENTS_DETECTED and PR_COMMENTS_RESOLVED are non-persisted (ephemeral internal signals, not workflow log entries)
- Each pipeline execution creates a fresh workflow_id, separate from the per-PR synthetic ID used for orchestration events
- issue_cache serves as the bridge between orchestrator data and API response fields

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated event classification guard test for new persisted types count**
- **Found during:** Task 2 verification
- **Issue:** tests/unit/server/models/test_events.py and tests/unit/test_event_filtering.py had hardcoded PERSISTED_TYPES count of 38, now 41
- **Fix:** Updated count to 41, added PR_COMMENTS_DETECTED and PR_COMMENTS_RESOLVED to stream_only set
- **Files modified:** tests/unit/server/models/test_events.py, tests/unit/test_event_filtering.py
- **Verification:** Full unit test suite passes (2109 tests)
- **Committed in:** 7a8201c7 (Task 2 commit)

**2. [Rule 3 - Blocking] Fixed github.py route DB initialization for test compatibility**
- **Found during:** Task 2 verification
- **Issue:** Initial approach used `WorkflowRepository(get_database())` directly in route, which fails in tests without DB initialization
- **Fix:** Changed to `Depends(get_repository)` pattern and added dependency override in test fixture
- **Files modified:** amelia/server/routes/github.py, tests/unit/server/routes/test_github_pr_routes.py
- **Verification:** All github route tests pass
- **Committed in:** 7a8201c7 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both fixes necessary for test correctness. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Backend infrastructure complete for PR auto-fix dashboard visibility
- WorkflowSummary and WorkflowDetailResponse now carry all data needed for frontend plans (09-02, 09-03)
- PR auto-fix runs will appear in GET /api/workflows with pipeline_type="pr_auto_fix" and PR metadata

---
*Phase: 09-events-dashboard*
*Completed: 2026-03-14*
