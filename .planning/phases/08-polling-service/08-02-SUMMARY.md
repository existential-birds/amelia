---
phase: 08-polling-service
plan: 02
subsystem: server
tags: [polling, lifespan, asyncio, pr-auto-fix]

# Dependency graph
requires:
  - phase: 08-01
    provides: PRCommentPoller service class with start/stop lifecycle
provides:
  - PRCommentPoller wired into server lifespan (starts on boot, stops on shutdown)
affects: [09-dashboard, 10-metrics]

# Tech tracking
tech-stack:
  added: []
  patterns: [lifespan-registration for background services]

key-files:
  created: []
  modified: [amelia/server/main.py]

key-decisions:
  - "Placeholder GitHubPRService('.') for PRAutoFixOrchestrator -- poller creates per-profile services at poll time"
  - "Poller stops before health_checker to avoid fix cycles on unhealthy worktrees during shutdown"

patterns-established:
  - "Lifespan registration: instantiate service, start after health_checker, stop before health_checker"

requirements-completed: [POLL-03]

# Metrics
duration: 2min
completed: 2026-03-14
---

# Phase 8 Plan 2: Server Lifespan Integration Summary

**PRCommentPoller wired into FastAPI lifespan with PRAutoFixOrchestrator, starting after health_checker and stopping before it during shutdown**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-14T20:32:52Z
- **Completed:** 2026-03-14T20:34:31Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- PRCommentPoller instantiated in server lifespan with all required dependencies
- Poller starts after health_checker during startup, stops before it during shutdown
- Full test suite passes (2091 tests, 0 failures)

## Task Commits

Each task was committed atomically:

1. **Task 1: Register PRCommentPoller in server lifespan** - `0cb241cf` (feat)

## Files Created/Modified
- `amelia/server/main.py` - Added PRCommentPoller, PRAutoFixOrchestrator, GitHubPRService imports; instantiation in lifespan; start/stop lifecycle calls

## Decisions Made
- Used placeholder GitHubPRService(".") for PRAutoFixOrchestrator constructor -- the orchestrator only uses it for create_issue_comment on divergence failure; the poller creates per-profile services for actual PR operations
- Poller stops before health_checker during shutdown to avoid triggering fix cycles on worktrees being torn down

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 8 (Polling Service) is complete with both plans finished
- PRCommentPoller is fully integrated: service class (08-01) + lifespan wiring (08-02)
- Ready for Phase 9 (Dashboard) and Phase 10 (Metrics)

---
*Phase: 08-polling-service*
*Completed: 2026-03-14*
