---
phase: 06-orchestration-safety
plan: 01
subsystem: pipeline
tags: [pydantic, pr-auto-fix, cooldown, events]

requires:
  - phase: 05-thread-resolution
    provides: PRAutoFixConfig base model with aggressiveness, poll_interval, etc.
provides:
  - PRAutoFixConfig cooldown fields (post_push_cooldown_seconds, max_cooldown_seconds) with validated bounds
  - Five PR fix orchestration EventType values (PR_FIX_QUEUED, PR_FIX_DIVERGED, PR_FIX_COOLDOWN_STARTED, PR_FIX_COOLDOWN_RESET, PR_FIX_RETRIES_EXHAUSTED)
affects: [06-02-orchestrator, 07-cli-api, 09-dashboard]

tech-stack:
  added: []
  patterns: [model_validator for cross-field cooldown validation]

key-files:
  created:
    - tests/unit/pipelines/pr_auto_fix/test_orchestrator.py
  modified:
    - amelia/core/types.py
    - amelia/server/models/events.py

key-decisions:
  - "Both-zero cooldown allowed: post_push=0, max=0 disables cooldown entirely"

patterns-established:
  - "Cross-field validation via model_validator(mode='after') with Self return type"

requirements-completed: [ORCH-02]

duration: 1min
completed: 2026-03-14
---

# Phase 6 Plan 1: Config & Event Types Summary

**PRAutoFixConfig extended with validated cooldown fields (300s/900s defaults) and 5 new PR fix EventType values for orchestrator visibility**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-14T14:20:36Z
- **Completed:** 2026-03-14T14:21:46Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments
- Added post_push_cooldown_seconds and max_cooldown_seconds to PRAutoFixConfig with cross-field validation
- Registered 5 new PR fix orchestration event types in EventType enum
- Full TDD coverage with 10 passing tests

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests** - `998bc435` (test)
2. **Task 1 (GREEN): Implementation** - `464706e5` (feat)

## Files Created/Modified
- `tests/unit/pipelines/pr_auto_fix/test_orchestrator.py` - Tests for cooldown config validation and event type existence
- `amelia/core/types.py` - PRAutoFixConfig with cooldown fields and model_validator
- `amelia/server/models/events.py` - Five new PR_FIX_* event type values

## Decisions Made
- Both-zero cooldown (post_push=0, max=0) is valid and means "no cooldown" -- simpler than a separate disable flag

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Cooldown config and event types ready for PRAutoFixOrchestrator (Plan 02)
- No blockers

## Self-Check: PASSED

All files and commits verified.

---
*Phase: 06-orchestration-safety*
*Completed: 2026-03-14*
