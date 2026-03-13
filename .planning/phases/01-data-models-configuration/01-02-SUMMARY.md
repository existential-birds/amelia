---
phase: 01-data-models-configuration
plan: 02
subsystem: database
tags: [postgresql, jsonb, migration, repository, pydantic, api-routes]

# Dependency graph
requires:
  - phase: 01-data-models-configuration plan 01
    provides: PRAutoFixConfig, AggressivenessLevel, Profile.pr_autofix models
provides:
  - Migration 008 adding pr_autofix JSONB column to profiles and pr_polling_enabled boolean to server_settings
  - ProfileRepository pr_autofix serialization/deserialization in create/read/update paths
  - ServerSettings pr_polling_enabled field with repository read/update support
  - API route models (ProfileResponse, ProfileCreate, ProfileUpdate) with pr_autofix field
  - ServerSettingsResponse/Update with pr_polling_enabled field
affects: [03-github-api, 04-classification, 05-pipeline, 06-orchestration, 07-cli-api, 08-polling, 09-dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns: [jsonb-column-with-nullable-default-for-optional-config, follow-sandbox-pattern-for-new-jsonb-fields]

key-files:
  created:
    - amelia/server/database/migrations/008_add_pr_autofix.sql
    - tests/unit/server/database/test_pr_autofix_persistence.py
  modified:
    - amelia/server/database/profile_repository.py
    - amelia/server/database/settings_repository.py
    - amelia/server/routes/settings.py

key-decisions:
  - "Followed exact sandbox JSONB pattern for pr_autofix: NULL default (not empty dict) since None means feature disabled"
  - "pr_polling_enabled defaults to FALSE at database level via NOT NULL DEFAULT FALSE"

patterns-established:
  - "Nullable JSONB column for optional nested config: DEFAULT NULL in migration, None check in repository deserialization"
  - "New server_settings fields: add to model, _row_to_settings, and valid_fields set in update method"

requirements-completed: [CONF-02, CONF-04]

# Metrics
duration: 7min
completed: 2026-03-13
---

# Phase 1 Plan 02: Database Persistence Summary

**PR auto-fix JSONB persistence with migration 008, profile repository round-trip, server settings polling toggle, and API route model integration**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-13T15:44:49Z
- **Completed:** 2026-03-13T15:52:24Z
- **Tasks:** 2 (1 TDD, 1 auto)
- **Files modified:** 8

## Accomplishments
- Migration 008 adds pr_autofix JSONB (DEFAULT NULL) to profiles and pr_polling_enabled BOOLEAN (DEFAULT FALSE) to server_settings
- ProfileRepository handles PRAutoFixConfig serialization/deserialization through create, read, and update paths following existing sandbox pattern
- ServerSettings model and repository support pr_polling_enabled in read/update with valid_fields enforcement
- API route models (ProfileResponse, ProfileCreate, ProfileUpdate, ServerSettingsResponse, ServerSettingsUpdate) expose pr_autofix and pr_polling_enabled
- 3 unit tests + 10 integration tests covering all persistence behaviors

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for pr_autofix persistence** - `644fcc54` (test)
2. **Task 1 GREEN: Implement pr_autofix database persistence** - `1b034ea3` (feat)
3. **Task 2: Update API route models for pr_autofix** - `98a933b3` (feat)

## Files Created/Modified
- `amelia/server/database/migrations/008_add_pr_autofix.sql` - Migration adding pr_autofix and pr_polling_enabled columns
- `amelia/server/database/profile_repository.py` - PRAutoFixConfig import, serialization in create, deserialization in _row_to_profile, pr_autofix in valid_fields
- `amelia/server/database/settings_repository.py` - pr_polling_enabled field on ServerSettings, added to _row_to_settings and valid_fields
- `amelia/server/routes/settings.py` - PRAutoFixConfig on ProfileResponse/Create/Update, pr_polling_enabled on ServerSettingsResponse/Update, wired through route handlers
- `tests/unit/server/database/test_pr_autofix_persistence.py` - Unit and integration tests for round-trip persistence
- `tests/unit/cli/test_config_cli.py` - Updated ServerSettings construction with pr_polling_enabled
- `tests/unit/server/routes/test_settings_routes.py` - Updated ServerSettings construction with pr_polling_enabled
- `tests/unit/server/routes/test_config.py` - Updated ServerSettings construction with pr_polling_enabled

## Decisions Made
- Followed exact sandbox JSONB pattern for pr_autofix: NULL default (not empty dict) since None means feature disabled, matching Profile.pr_autofix semantics
- pr_polling_enabled defaults to FALSE at database level with NOT NULL constraint, consistent with a global toggle that should be opt-in

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing tests for new ServerSettings field**
- **Found during:** Task 1 GREEN phase
- **Issue:** Three existing test files construct ServerSettings without pr_polling_enabled, causing ValidationError after adding the required field
- **Fix:** Added `pr_polling_enabled=False` to all ServerSettings constructor calls in test_config_cli.py, test_settings_routes.py, test_config.py
- **Files modified:** tests/unit/cli/test_config_cli.py, tests/unit/server/routes/test_settings_routes.py, tests/unit/server/routes/test_config.py
- **Verification:** All 1815 unit tests pass
- **Committed in:** 1b034ea3 (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential for test compatibility -- adding a required field to ServerSettings requires all constructors to include it. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviation above.

## User Setup Required
None - no external service configuration required. Migration runs automatically via the existing migrator.

## Next Phase Readiness
- All PR auto-fix data models and database persistence complete
- PRAutoFixConfig round-trips through Profile create/read/update via JSONB
- pr_polling_enabled toggle available in server settings
- API route models ready for dashboard and CLI consumption
- Foundation ready for Phase 2 (GitHub API integration)

## Self-Check: PASSED

---
*Phase: 01-data-models-configuration*
*Completed: 2026-03-13*
