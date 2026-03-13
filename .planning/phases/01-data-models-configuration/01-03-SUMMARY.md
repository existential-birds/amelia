---
phase: 01-data-models-configuration
plan: 03
subsystem: api
tags: [pydantic, model_fields_set, nullable-jsonb, fastapi]

# Dependency graph
requires:
  - phase: 01-data-models-configuration
    provides: "PRAutoFixConfig model and profile repository with JSONB nullable support"
provides:
  - "model_fields_set-based nullable field handling in profile update route"
  - "Regression tests for null-clearing vs omission distinction"
affects: [02-api-endpoints, 04-core-fix-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns: ["model_fields_set for distinguishing omitted vs explicit-null in Pydantic update models"]

key-files:
  created: []
  modified:
    - amelia/server/routes/settings.py
    - tests/unit/server/routes/test_settings_routes.py

key-decisions:
  - "Applied model_fields_set fix to both pr_autofix and sandbox fields for consistency"

patterns-established:
  - "model_fields_set pattern: Use `field in updates.model_fields_set` instead of `is not None` for nullable JSONB fields in PUT handlers"

requirements-completed: [CONF-02]

# Metrics
duration: 2min
completed: 2026-03-13
---

# Phase 1 Plan 3: Nullable PR Auto-fix Update Fix Summary

**Fixed nullable field ambiguity in profile PUT handler using Pydantic model_fields_set to distinguish omission from explicit null**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-13T19:24:26Z
- **Completed:** 2026-03-13T19:26:36Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Fixed the bug where setting pr_autofix to null could not clear the config (UAT Test 3 failure)
- Applied same fix to sandbox field which had identical bug pattern
- Added 3 regression tests covering null-clearing, omission, and valid config scenarios
- All 1843 tests pass with 0 failures

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Add failing tests for nullable pr_autofix** - `c43b1829` (test)
2. **Task 1 (GREEN): Fix using model_fields_set** - `bd6dc71e` (fix)

## Files Created/Modified
- `amelia/server/routes/settings.py` - Replaced `is not None` with `model_fields_set` checks for pr_autofix and sandbox fields
- `tests/unit/server/routes/test_settings_routes.py` - Added 3 tests for null-clearing, omission, and valid config scenarios

## Decisions Made
- Applied model_fields_set fix to both pr_autofix AND sandbox fields, even though only pr_autofix was failing UAT. Both had the identical bug pattern where explicit null could not clear the config.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 1 (Data Models & Configuration) is fully complete
- All nullable JSONB fields now correctly handle the omission vs explicit-null distinction
- Ready for Phase 2 (API Endpoints) to build on this foundation

---
*Phase: 01-data-models-configuration*
*Completed: 2026-03-13*
