---
phase: 03-comment-classification
plan: 02
subsystem: classification
tags: [classifier, llm, filtering, aggressiveness, confidence, grouping]

requires:
  - phase: 03-comment-classification
    provides: CommentCategory StrEnum, CommentClassification model, ClassificationOutput schema, CATEGORY_THRESHOLD, is_actionable, classifier.system prompt
  - phase: 02-github-integration
    provides: AMELIA_FOOTER signature, PRReviewComment model
  - phase: 01-core-models
    provides: AggressivenessLevel IntEnum, PRAutoFixConfig model, DriverInterface protocol

provides:
  - classify_comments async function for LLM-based batch classification with post-filtering
  - filter_comments pre-filtering (top-level, iteration limits, Amelia reply detection)
  - filter_top_level, count_amelia_replies, has_new_feedback_after_amelia, should_skip_thread helpers
  - group_comments_by_file for organizing actionable comments by path
affects: [04-core-fix-pipeline]

tech-stack:
  added: []
  patterns: [model_copy for frozen model updates, defaultdict for file grouping, footer signature matching for self-comment detection]

key-files:
  created:
    - amelia/services/classifier.py
    - tests/unit/services/test_classifier.py
  modified: []

key-decisions:
  - "Footer signature match (AMELIA_FOOTER in body) for detecting Amelia replies rather than author-name matching"
  - "Thread skip logic: any Amelia reply with no new feedback = skip, regardless of iteration count"

patterns-established:
  - "Pre-filter then classify then post-filter pipeline: top-level + thread skip -> LLM classify -> confidence threshold -> aggressiveness filter"
  - "model_copy(update={'actionable': False}) for mutating frozen CommentClassification"

requirements-completed: [CMNT-01, CMNT-02, CMNT-03, CMNT-04, CMNT-05]

duration: 4min
completed: 2026-03-13
---

# Phase 3 Plan 02: Classifier Service Summary

**Async classifier service with pre-filtering (top-level, iteration, Amelia-reply), LLM-based batch classification, confidence/aggressiveness post-filtering, and file grouping**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-14T00:09:01Z
- **Completed:** 2026-03-14T00:13:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Implemented pre-filtering pipeline: filter_top_level, count_amelia_replies, has_new_feedback_after_amelia, should_skip_thread, filter_comments
- Built async classify_comments that calls driver.generate with ClassificationOutput schema, applies confidence threshold and aggressiveness filters
- Created group_comments_by_file for organizing actionable comments by path with None-path separation
- 27 unit tests covering all pre-filtering, classification, filtering, and grouping behaviors

## Task Commits

Each task was committed atomically:

1. **Task 1: Pre-filtering helpers and iteration detection** - `254a3f23` (test+feat TDD)
2. **Task 2: LLM classification, confidence/aggressiveness filtering, and file grouping** - `172fdaac` (feat TDD)

## Files Created/Modified
- `amelia/services/classifier.py` - classify_comments, filter_comments, group_comments_by_file, and pre-filtering helpers
- `tests/unit/services/test_classifier.py` - 27 unit tests for all classifier service functions

## Decisions Made
- Footer signature match (AMELIA_FOOTER in body) for detecting Amelia replies, consistent with Phase 02 approach
- Thread skip logic treats any Amelia reply without new feedback as skip-worthy, regardless of whether max_iterations is reached

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff SIM103 lint violation**
- **Found during:** Task 2 (verification step)
- **Issue:** ruff flagged should_skip_thread return logic as SIM103 (return negated condition directly)
- **Fix:** Simplified `if new_feedback: return False; return True` to `return not has_new_feedback_after_amelia(...)`
- **Files modified:** amelia/services/classifier.py
- **Verification:** ruff check passes, all tests still pass

---

**Total deviations:** 1 auto-fixed (1 lint fix)
**Impact on plan:** Trivial style fix. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Classifier service ready for Phase 4 (Core Fix Pipeline) to invoke
- classify_comments takes comments + driver + config, returns dict[int, CommentClassification]
- filter_comments handles all pre-filtering before classification
- group_comments_by_file provides file-organized output for Developer agent

## Self-Check: PASSED

---
*Phase: 03-comment-classification*
*Completed: 2026-03-13*
