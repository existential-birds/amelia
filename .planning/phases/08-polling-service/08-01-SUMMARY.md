---
phase: 08-polling-service
plan: 01
subsystem: polling
tags: [asyncio, github-api, rate-limiting, lifecycle, fire-and-forget]

requires:
  - phase: 06-orchestration-safety
    provides: PRAutoFixOrchestrator with trigger_fix_cycle
  - phase: 02-github-integration
    provides: GitHubPRService with fetch_review_comments and list_open_prs

provides:
  - PRCommentPoller class with start/stop lifecycle
  - poll_label field on PRAutoFixConfig
  - PR_POLL_RATE_LIMITED event type
  - list_labeled_prs method on GitHubPRService

affects: [09-dashboard, 10-metrics, server-startup]

tech-stack:
  added: []
  patterns: [lifecycle-service, fire-and-forget-dispatch, monotonic-scheduling, rate-limit-backoff]

key-files:
  created:
    - amelia/server/lifecycle/pr_poller.py
  modified:
    - amelia/core/types.py
    - amelia/server/models/events.py
    - amelia/services/github_pr.py
    - tests/unit/server/lifecycle/test_pr_poller.py
    - tests/unit/server/models/test_events.py

key-decisions:
  - "PR_POLL_RATE_LIMITED classified as transient (not persisted to workflow log) since it is an ephemeral operational signal"
  - "time.monotonic() for schedule tracking (NTP-immune), time.time() only for rate limit reset comparison (GitHub returns unix timestamps)"
  - "next_poll set BEFORE _poll_profile call to prevent overlap when cycles run long"

patterns-established:
  - "Lifecycle service pattern: start/stop with asyncio.create_task following WorktreeHealthChecker"
  - "Fire-and-forget pattern: asyncio.create_task with _active_tasks set and done callback for cleanup"
  - "Rate limit backoff: 10% threshold with event emission and sleep-to-reset"

requirements-completed: [POLL-01, POLL-02, POLL-04, POLL-05]

duration: 5min
completed: 2026-03-14
---

# Phase 8 Plan 1: PR Comment Poller Summary

**PRCommentPoller service with per-profile scheduling, GitHub rate limit backoff, and fire-and-forget fix cycle dispatch via orchestrator**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-14T20:25:00Z
- **Completed:** 2026-03-14T20:30:32Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- PRCommentPoller class with full start/stop lifecycle, per-profile poll scheduling, rate limit awareness, and fire-and-forget dispatch
- poll_label config field enabling label-based PR filtering per profile
- list_labeled_prs method on GitHubPRService for GitHub label-filtered PR listing
- 24 unit tests covering all behaviors: lifecycle, scheduling, dispatch, rate limiting, resilience, toggle, overlap prevention

## Task Commits

Each task was committed atomically:

1. **Task 1: Config extensions and label-filtered PR listing** - `edfc75ee` (feat)
2. **Task 2: PRCommentPoller service with lifecycle, rate limiting, and dispatch** - `e29f8183` (feat)

_TDD approach: tests written first (RED), then implementation (GREEN) for both tasks._

## Files Created/Modified
- `amelia/server/lifecycle/pr_poller.py` - PRCommentPoller class with lifecycle, scheduling, rate limiting, dispatch
- `amelia/core/types.py` - Added poll_label field to PRAutoFixConfig
- `amelia/server/models/events.py` - Added PR_POLL_RATE_LIMITED event type to EventType and _WARNING_TYPES
- `amelia/services/github_pr.py` - Added list_labeled_prs method to GitHubPRService
- `tests/unit/server/lifecycle/test_pr_poller.py` - 24 unit tests for all poller behaviors
- `tests/unit/server/models/test_events.py` - Updated event classification test for new transient event type

## Decisions Made
- PR_POLL_RATE_LIMITED classified as transient (not persisted to workflow log) since it's an ephemeral operational signal, not a workflow event
- Used time.monotonic() for schedule tracking (immune to NTP adjustments), time.time() only for rate limit reset comparison (GitHub returns unix timestamps)
- next_poll set BEFORE _poll_profile call to prevent overlap when cycles take longer than poll_interval

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed event classification test for new event type**
- **Found during:** Task 2 (full test suite verification)
- **Issue:** test_every_event_type_is_classified failed because PR_POLL_RATE_LIMITED was not in either PERSISTED_TYPES or stream_only set
- **Fix:** Added PR_POLL_RATE_LIMITED to stream_only set in test (consistent with its transient nature)
- **Files modified:** tests/unit/server/models/test_events.py
- **Verification:** Full test suite passes (2091 tests)
- **Committed in:** e29f8183 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary for test suite correctness. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- PRCommentPoller ready for server startup integration (needs wiring in server lifecycle)
- Dashboard can subscribe to PR_POLL_RATE_LIMITED events for visibility
- Full test coverage ensures safe integration

---
*Phase: 08-polling-service*
*Completed: 2026-03-14*
