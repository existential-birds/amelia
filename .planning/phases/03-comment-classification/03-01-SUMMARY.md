---
phase: 03-comment-classification
plan: 01
subsystem: classification
tags: [pydantic, strenum, enum, schema, aggressiveness, threshold]

requires:
  - phase: 01-core-models
    provides: AggressivenessLevel IntEnum, PRAutoFixConfig model
provides:
  - CommentCategory StrEnum with 6 classification categories
  - CommentClassification frozen Pydantic model for single comment
  - ClassificationOutput batch wrapper for LLM structured output
  - CATEGORY_THRESHOLD mapping categories to minimum AggressivenessLevel
  - is_actionable pure function for aggressiveness-based filtering
  - PRAutoFixConfig.confidence_threshold field (default 0.7)
  - classifier.system prompt in PROMPT_DEFAULTS
affects: [03-comment-classification, 04-core-fix-pipeline]

tech-stack:
  added: []
  patterns: [StrEnum for JSON-readable category enums, threshold mapping with None sentinel for never-actionable]

key-files:
  created:
    - amelia/agents/schemas/classifier.py
    - tests/unit/agents/schemas/test_classifier_schema.py
  modified:
    - amelia/core/types.py
    - amelia/agents/prompts/defaults.py

key-decisions:
  - "Used StrEnum (not str+Enum) for CommentCategory for JSON readability and modern Python 3.12+ idiom"
  - "CATEGORY_THRESHOLD uses None sentinel for praise (never-actionable) rather than a separate boolean"

patterns-established:
  - "Threshold mapping pattern: dict[Category, Level | None] with None = never-actionable"
  - "is_actionable as pure function (no method on model) for testability and reuse"

requirements-completed: [CMNT-01, CMNT-02]

duration: 3min
completed: 2026-03-13
---

# Phase 3 Plan 01: Classification Schemas Summary

**CommentCategory StrEnum, CommentClassification/ClassificationOutput Pydantic models, CATEGORY_THRESHOLD mapping, is_actionable helper, and classifier system prompt**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-14T00:03:58Z
- **Completed:** 2026-03-14T00:07:03Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Defined CommentCategory StrEnum with 6 values (bug, security, style, suggestion, question, praise)
- Created CommentClassification frozen model with bounded confidence and ClassificationOutput batch wrapper
- Implemented CATEGORY_THRESHOLD mapping and is_actionable pure function for aggressiveness filtering
- Added confidence_threshold field (default 0.7, bounded 0-1) to PRAutoFixConfig
- Registered classifier.system prompt in PROMPT_DEFAULTS with aggressiveness-parameterized instructions

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for classifier schemas** - `9ba19a18` (test)
2. **Task 1 GREEN: Implement classifier schemas + config update** - `2dce16c6` (feat)
3. **Task 2: Register classifier.system prompt** - `9fbe563f` (feat)

## Files Created/Modified
- `amelia/agents/schemas/classifier.py` - CommentCategory, CommentClassification, ClassificationOutput, CATEGORY_THRESHOLD, is_actionable
- `amelia/core/types.py` - Added confidence_threshold field to PRAutoFixConfig
- `amelia/agents/prompts/defaults.py` - Added classifier.system entry to PROMPT_DEFAULTS
- `tests/unit/agents/schemas/test_classifier_schema.py` - 37 tests covering all schemas, thresholds, and filtering

## Decisions Made
- Used StrEnum (not str+Enum pattern from evaluator.py) for CommentCategory -- modern Python 3.12+ idiom, better JSON readability per research recommendations
- CATEGORY_THRESHOLD uses None sentinel for praise (never-actionable) rather than a separate exclusion set -- simpler single-lookup pattern

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All classification contracts ready for Plan 02 (classifier service implementation)
- CommentCategory, CATEGORY_THRESHOLD, and is_actionable provide the typed interface the classifier service will use
- classifier.system prompt ready for runtime formatting with {aggressiveness_level} placeholder

---
*Phase: 03-comment-classification*
*Completed: 2026-03-13*
