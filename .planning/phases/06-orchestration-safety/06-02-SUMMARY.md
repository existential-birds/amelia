---
phase: 06-orchestration-safety
plan: 02
subsystem: pipeline
tags: [asyncio, concurrency, cooldown, divergence-recovery, pr-auto-fix]

requires:
  - phase: 06-orchestration-safety
    provides: PRAutoFixConfig cooldown fields and PR_FIX_* event types
  - phase: 04-fix-pipeline
    provides: PRAutoFixPipeline for pipeline execution
  - phase: 02-api-tooling
    provides: GitOperations for branch operations and divergence detection
provides:
  - PRAutoFixOrchestrator class with per-PR concurrency, cooldown, and divergence recovery
  - GitHubPRService.create_issue_comment for PR-level comments
  - PR_FIX_* event type classification in PERSISTED_TYPES and level sets
affects: [07-cli-api, 08-polling, 09-dashboard]

tech-stack:
  added: []
  patterns: [asyncio.Event interruptible cooldown, per-resource Lock dict with pending flag, repo-level git serialization]

key-files:
  created:
    - amelia/pipelines/pr_auto_fix/orchestrator.py
  modified:
    - amelia/services/github_pr.py
    - amelia/server/models/events.py
    - tests/unit/pipelines/pr_auto_fix/test_orchestrator.py
    - tests/unit/test_event_filtering.py

key-decisions:
  - "Non-divergence errors logged and returned (not retried) -- only ValueError with 'diverged' triggers retry"
  - "create_issue_comment added to GitHubPRService using issues endpoint for PR-level comments"
  - "PR_FIX_RETRIES_EXHAUSTED classified as ERROR level, PR_FIX_DIVERGED as WARNING, others as INFO"

patterns-established:
  - "asyncio.Event + wait_for for interruptible timer with max cap"
  - "Repo-level asyncio.Lock serializing git operations across PRs sharing the same repo_path"
  - "_execute_pipeline method seam for testability -- tests mock this to isolate orchestration logic"

requirements-completed: [ORCH-01, ORCH-02, ORCH-03]

duration: 9min
completed: 2026-03-14
---

# Phase 6 Plan 2: PRAutoFixOrchestrator Summary

**PRAutoFixOrchestrator with per-PR asyncio.Lock concurrency, asyncio.Event interruptible cooldown timer, and divergence recovery with retry and GitHub PR comment on final failure**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-14T14:23:19Z
- **Completed:** 2026-03-14T14:32:19Z
- **Tasks:** 2 (TDD RED + GREEN)
- **Files modified:** 5

## Accomplishments
- PRAutoFixOrchestrator with per-PR locking and boolean pending flag (latest wins, no accumulation)
- Interruptible cooldown timer using asyncio.Event with max cap enforcement and reset-on-new-comments
- Divergence recovery with up to 2 retries, plus GitHub PR comment on final failure via create_issue_comment
- Repo-level asyncio.Lock serializing git operations across PRs sharing the same repo_path
- 25 passing orchestrator tests covering all behaviors

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing orchestrator tests** - `4e4e38f1` (test)
2. **Task 1 (GREEN): Implementation + event classification fix** - `1aaae283` (feat)

## Files Created/Modified
- `amelia/pipelines/pr_auto_fix/orchestrator.py` - PRAutoFixOrchestrator class with concurrency, cooldown, and divergence recovery
- `amelia/services/github_pr.py` - Added create_issue_comment for PR-level comments
- `amelia/server/models/events.py` - PR_FIX_* events classified in PERSISTED_TYPES and level sets
- `tests/unit/pipelines/pr_auto_fix/test_orchestrator.py` - 25 tests covering all orchestration behaviors
- `tests/unit/test_event_filtering.py` - Updated persisted types count (33 -> 38)

## Decisions Made
- Non-divergence errors (RuntimeError, etc.) are logged and returned without retry -- only ValueError containing "diverged" triggers the retry loop
- Added create_issue_comment to GitHubPRService using the /repos/{repo}/issues/{pr}/comments endpoint for PR-level (non-review) comments
- Classified PR_FIX_RETRIES_EXHAUSTED as ERROR level, PR_FIX_DIVERGED as WARNING, and QUEUED/COOLDOWN_STARTED/COOLDOWN_RESET as INFO

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] PR_FIX_* event types not classified in PERSISTED_TYPES and level sets**
- **Found during:** Task 1 GREEN (implementation)
- **Issue:** Plan 06-01 added 5 PR_FIX_* event types but didn't add them to PERSISTED_TYPES, _ERROR_TYPES, _WARNING_TYPES, or _INFO_TYPES. test_every_event_type_is_classified and test_persisted_types_count failed.
- **Fix:** Added all 5 to PERSISTED_TYPES, classified RETRIES_EXHAUSTED as error, DIVERGED as warning, others as info. Updated count test from 33 to 38.
- **Files modified:** amelia/server/models/events.py, tests/unit/test_event_filtering.py
- **Verification:** Full test suite passes (2019 tests, 0 failures)
- **Committed in:** 1aaae283

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential for correctness -- event types must be classified per existing test guard.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- PRAutoFixOrchestrator ready for Phase 7 (CLI/API triggers) and Phase 8 (Polling) to call trigger_fix_cycle
- _execute_pipeline method needs wiring to PRAutoFixPipeline in integration phase
- No blockers

## Self-Check: PASSED

All files and commits verified.

---
*Phase: 06-orchestration-safety*
*Completed: 2026-03-14*
