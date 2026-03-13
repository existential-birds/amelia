---
phase: 01-data-models-configuration
plan: 01
subsystem: data-models
tags: [pydantic, intenum, frozen-models, pr-autofix, configuration]

# Dependency graph
requires: []
provides:
  - AggressivenessLevel IntEnum with ordered threshold comparisons
  - PRSummary frozen model for GitHub PR metadata
  - PRReviewComment frozen model for inline and general review comments
  - PRAutoFixConfig frozen model with validated defaults and string serialization
  - Profile.pr_autofix optional field (None = disabled)
affects: [02-database-migration, 03-github-api, 04-classification, 05-pipeline, 06-orchestration, 07-cli-api, 08-polling]

# Tech tracking
tech-stack:
  added: []
  patterns: [IntEnum-with-field-serializer-for-string-output, field-validator-for-bidirectional-enum-parsing]

key-files:
  created:
    - tests/unit/core/test_pr_autofix_models.py
  modified:
    - amelia/core/types.py

key-decisions:
  - "Added field_validator on AggressivenessLevel for bidirectional string/int parsing to support JSON round-trip with string serialization"
  - "Included pr_number as optional field on PRReviewComment for self-contained context in downstream consumers"

patterns-established:
  - "IntEnum with field_serializer + field_validator: serialize to lowercase string name, parse from both string and int"
  - "Optional nested frozen config on Profile: None means feature disabled, PRAutoFixConfig() means enabled with defaults"

requirements-completed: [DATA-01, DATA-02, DATA-03, DATA-04, CONF-01, CONF-02, CONF-03]

# Metrics
duration: 3min
completed: 2026-03-13
---

# Phase 1 Plan 01: Data Models Summary

**Frozen Pydantic models for PR auto-fix (AggressivenessLevel IntEnum, PRSummary, PRReviewComment, PRAutoFixConfig) with Profile integration and bidirectional JSON serialization**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-13T15:40:01Z
- **Completed:** 2026-03-13T15:43:00Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- AggressivenessLevel IntEnum with 3 ordered levels (CRITICAL=1, STANDARD=2, THOROUGH=3) supporting threshold comparisons
- PRSummary, PRReviewComment, PRAutoFixConfig frozen Pydantic models with all required fields and validation
- AggressivenessLevel serializes to string name in JSON and deserializes from both string and int
- Profile.pr_autofix optional field integrating auto-fix config into existing profile system
- 29 unit tests covering all behavior: ordering, immutability, validation bounds, serialization round-trip, overrides

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for PR auto-fix models** - `ca2ae811` (test)
2. **Task 1 GREEN: Implement PR auto-fix data models** - `2aacc7a2` (feat)

## Files Created/Modified
- `tests/unit/core/test_pr_autofix_models.py` - 29 unit tests for all PR auto-fix models
- `amelia/core/types.py` - AggressivenessLevel, PRSummary, PRReviewComment, PRAutoFixConfig models + Profile.pr_autofix field

## Decisions Made
- Added `field_validator("aggressiveness", mode="before")` to PRAutoFixConfig for bidirectional parsing -- serializer outputs lowercase string name for API readability, validator accepts both string names and integer values for deserialization. This ensures JSON round-trip works correctly.
- Included `pr_number: int | None = None` on PRReviewComment (Claude's discretion per CONTEXT.md) for self-contained context in downstream classification and pipeline consumers.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed IntEnum JSON round-trip with field_validator**
- **Found during:** Task 1 GREEN phase
- **Issue:** field_serializer outputs string name ("thorough") but Pydantic IntEnum validator rejects string input on deserialization, breaking model_dump/model_validate round-trip
- **Fix:** Added field_validator with mode="before" that accepts both string names (via `.upper()` lookup) and integer values
- **Files modified:** amelia/core/types.py
- **Verification:** test_round_trip_serialization and test_aggressiveness_deserializes_from_string both pass
- **Committed in:** 2aacc7a2 (GREEN phase commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential for correctness -- without the validator, serialized configs cannot be deserialized. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All PR auto-fix data models defined and tested, ready for database migration (Plan 02) and all downstream phases
- Profile.pr_autofix field available for repository deserialization and API route models

---
*Phase: 01-data-models-configuration*
*Completed: 2026-03-13*
