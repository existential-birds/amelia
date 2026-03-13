---
phase: 02-github-api-layer
plan: 01
subsystem: api
tags: [github, graphql, rest, gh-cli, async, pydantic]

requires:
  - phase: 01-data-models
    provides: PRReviewComment, PRSummary, PRAutoFixConfig Pydantic models
provides:
  - GitHubPRService class with fetch_review_comments, list_open_prs, resolve_thread, reply_to_comment
  - AMELIA_FOOTER constant for self-comment detection
  - ignore_authors field on PRAutoFixConfig for configurable author filtering
  - _should_skip_comment method for bot/self comment filtering
affects: [04-core-fix-pipeline, 06-orchestration, 08-polling-service]

tech-stack:
  added: []
  patterns: [async gh CLI subprocess with timeout, REST+GraphQL hybrid for PR data, comment thread ID mapping]

key-files:
  created:
    - amelia/services/__init__.py
    - amelia/services/github_pr.py
    - tests/unit/services/__init__.py
    - tests/unit/services/test_github_pr.py
  modified:
    - amelia/core/types.py

key-decisions:
  - "Two-step REST+GraphQL approach for fetching review comments: REST for comment data, GraphQL for thread resolution status"
  - "Footer signature match (_Amelia (automated fix)_) for self-comment detection rather than author name matching"
  - "Parent comment ID used for replies when in_reply_to_id is set (GitHub Pitfall 7)"

patterns-established:
  - "GitHubPRService pattern: async class with _run_gh helper wrapping asyncio.create_subprocess_exec with timeout and error handling"
  - "Comment thread mapping: REST databaseId matched to GraphQL thread nodes for thread_id/is_resolved enrichment"

requirements-completed: [GHAPI-01, GHAPI-02, GHAPI-03, GHAPI-04, GHAPI-05]

duration: 4min
completed: 2026-03-13
---

# Phase 2 Plan 1: GitHub PR Service Summary

**Async GitHubPRService with REST+GraphQL hybrid comment fetching, thread resolution, reply posting, and configurable bot/self-comment filtering via gh CLI**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-13T21:10:04Z
- **Completed:** 2026-03-13T21:14:03Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- GitHubPRService class with all 4 public methods and _should_skip_comment helper
- 12 unit tests covering all GHAPI requirements (01-05) including error handling and config round-trip
- ignore_authors field added to PRAutoFixConfig with backward-compatible empty list default
- Clean mypy and ruff on all new code

## Task Commits

Each task was committed atomically:

1. **Task 1: Add ignore_authors + test scaffolds (RED)** - `5a8f11ac` (test)
2. **Task 2: Implement GitHubPRService (GREEN + REFACTOR)** - `442fd4f2` (feat)

## Files Created/Modified
- `amelia/services/__init__.py` - Services package init
- `amelia/services/github_pr.py` - GitHubPRService with fetch_review_comments, list_open_prs, resolve_thread, reply_to_comment
- `amelia/core/types.py` - Added ignore_authors field to PRAutoFixConfig
- `tests/unit/services/__init__.py` - Test package init
- `tests/unit/services/test_github_pr.py` - 12 unit tests for GHAPI-01 through GHAPI-05

## Decisions Made
- Two-step REST+GraphQL approach for comment fetching: REST provides comment data, GraphQL provides thread resolution status and thread IDs
- Footer signature match for self-comment detection (body contains `_Amelia (automated fix)_`) rather than author name matching
- Parent comment ID used for replies when in_reply_to_id is set, per GitHub's single-level threading constraint (Pitfall 7)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff lint violations in github_pr.py**
- **Found during:** Task 2 (REFACTOR phase)
- **Issue:** Missing `from exc` on re-raised TimeoutError, unsorted imports, verbose boolean return
- **Fix:** Added `from exc`, ran `ruff check --fix`, simplified `_should_skip_comment` return
- **Files modified:** amelia/services/github_pr.py
- **Verification:** `uv run ruff check amelia/services/` passes clean
- **Committed in:** 442fd4f2 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Standard lint compliance fix during REFACTOR phase. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- GitHubPRService ready for consumption by fix pipeline (Phase 4)
- Thread resolution via GraphQL mutation available for auto-resolve flow
- Comment filtering logic (self/ignored) ready for integration
- Next plan (02-02) will add git operations (stage, commit, push, pull, SHA verification)

## Self-Check: PASSED

All 5 files verified present. Both commit hashes (5a8f11ac, 442fd4f2) confirmed in git log.

---
*Phase: 02-github-api-layer*
*Completed: 2026-03-13*
