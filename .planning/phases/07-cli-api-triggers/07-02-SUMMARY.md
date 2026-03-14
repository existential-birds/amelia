---
phase: 07-cli-api-triggers
plan: 02
subsystem: cli
tags: [typer, cli, websocket, streaming, pr-autofix]

requires:
  - phase: 07-cli-api-triggers
    provides: Four PR API endpoints (list, comments, config, trigger)
provides:
  - fix-pr CLI command with one-shot PR auto-fix
  - watch-pr CLI command with polling loop and auto-stop
  - AmeliaClient PR methods (trigger, list, comments, config status)
  - WorkflowSummary model from stream_workflow_events
affects: [08-polling-service, 09-dashboard]

tech-stack:
  added: []
  patterns: [WorkflowSummary collection from streaming events, client-side pr_autofix validation before trigger]

key-files:
  created:
    - tests/unit/client/test_pr_api_client.py
    - tests/unit/client/test_streaming_summary.py
    - tests/unit/test_fix_pr_command.py
    - tests/unit/test_watch_pr_command.py
  modified:
    - amelia/client/api.py
    - amelia/client/streaming.py
    - amelia/main.py

key-decisions:
  - "WorkflowSummary collects counts from stage_completed result.status and commit_sha from workflow_completed event data"
  - "display=False on stream_workflow_events creates no Console at all (None check) rather than quiet Console"
  - "Client-side response models (TriggerPRAutoFixResponse, PRAutoFixStatusResponse, etc.) defined in api.py since they are API-specific"

patterns-established:
  - "CLI validation pattern: get_pr_autofix_status before trigger, with locked error message and exit(1)"
  - "Summary line format: '{N} comments fixed, {N} skipped, {N} failed' with optional commit SHA"

requirements-completed: [TRIG-01, TRIG-02]

duration: 6min
completed: 2026-03-14
---

# Phase 7 Plan 02: CLI Commands Summary

**fix-pr and watch-pr CLI commands with AmeliaClient PR methods, streaming WorkflowSummary, and client-side validation**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-14T18:37:44Z
- **Completed:** 2026-03-14T18:43:44Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- AmeliaClient with trigger_pr_autofix, list_prs, get_pr_comments, get_pr_autofix_status methods
- stream_workflow_events returns WorkflowSummary with fixed/skipped/failed counts and commit_sha
- fix-pr command: validates config, triggers fix, streams events, prints summary with commit SHA
- watch-pr command: continuous polling loop with auto-stop on zero unresolved comments

## Task Commits

Each task was committed atomically:

1. **Task 1: AmeliaClient PR methods, streaming summary, and fix-pr CLI command**
   - `02ab089c` (test) - RED: failing tests
   - `bb46f513` (feat) - GREEN: implementation
2. **Task 2: watch-pr CLI command with polling loop and auto-stop**
   - `5bcdf885` (test) - RED: failing tests
   - `bd8ccc2a` (feat) - GREEN: implementation

_Note: Both tasks followed TDD with RED then GREEN commits._

## Files Created/Modified
- `amelia/client/api.py` - Four new PR methods on AmeliaClient, response models
- `amelia/client/streaming.py` - WorkflowSummary model, display parameter, summary collection
- `amelia/main.py` - fix-pr and watch-pr CLI commands
- `tests/unit/client/test_pr_api_client.py` - 12 tests for PR API client methods
- `tests/unit/client/test_streaming_summary.py` - 4 tests for streaming summary
- `tests/unit/test_fix_pr_command.py` - 7 tests for fix-pr command
- `tests/unit/test_watch_pr_command.py` - 7 tests for watch-pr command

## Decisions Made
- WorkflowSummary collects counts from stage_completed events with result.status field; defaults to zeros if pipeline doesn't emit these yet
- display=False creates no Console object rather than a quiet/null Console -- simpler implementation
- Client-side PR response models live in api.py (not client/models.py) since they're specific to the PR API surface

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test data for PRSummary and PRReviewComment models**
- **Found during:** Task 1
- **Issue:** Test mock data was missing required fields (updated_at for PRSummary, author for PRReviewComment)
- **Fix:** Updated test fixtures with correct field names and values
- **Files modified:** tests/unit/client/test_pr_api_client.py
- **Committed in:** bb46f513

**2. [Rule 3 - Blocking] Fixed async iterator mock for WebSocket streaming tests**
- **Found during:** Task 1
- **Issue:** `iter(messages).__aiter__()` fails because sync iterators don't have `__aiter__`
- **Fix:** Created `_AsyncIter` helper class wrapping list into proper async iterator
- **Files modified:** tests/unit/client/test_streaming_summary.py
- **Committed in:** bb46f513

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both fixes were test infrastructure issues. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- CLI trigger layer complete: fix-pr for one-shot, watch-pr for continuous monitoring
- Phase 8 (Polling Service) can proceed independently -- uses same API endpoints
- Phase 9 (Dashboard) can show workflow summaries using same WorkflowSummary model

---
*Phase: 07-cli-api-triggers*
*Completed: 2026-03-14*
