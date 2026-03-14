---
phase: 07-cli-api-triggers
plan: 01
subsystem: api
tags: [fastapi, rest, orchestrator, github-cli, pr-autofix]

requires:
  - phase: 06-orchestration-safety
    provides: PRAutoFixOrchestrator with concurrency control, cooldown, divergence recovery
provides:
  - Four PR API endpoints (list, comments, config, trigger)
  - get_pr_summary service method for single-PR metadata
  - _execute_pipeline wired to real PRAutoFixPipeline
  - head_branch threaded from API through orchestrator to pipeline
affects: [07-cli-api-triggers, 08-polling-service]

tech-stack:
  added: []
  patterns: [_resolve_github_profile helper for shared profile validation, _get_repo_name for repo resolution]

key-files:
  created:
    - tests/unit/server/routes/test_github_pr_routes.py
    - tests/unit/services/test_github_pr_get_summary.py
  modified:
    - amelia/server/routes/github.py
    - amelia/services/github_pr.py
    - amelia/pipelines/pr_auto_fix/orchestrator.py
    - tests/unit/pipelines/pr_auto_fix/test_orchestrator.py

key-decisions:
  - "enabled flag derived from pr_autofix presence (not a separate field) since PRAutoFixConfig has no enabled field"
  - "_get_repo_name extracted as testable async helper for gh repo view subprocess"
  - "_resolve_github_profile extracted as shared helper to avoid duplicating profile validation across endpoints"

patterns-established:
  - "PR endpoint pattern: resolve profile, create GitHubPRService, delegate to service, return typed response"
  - "Trigger pattern: fetch PR metadata for head_branch before spawning orchestrator task"

requirements-completed: [TRIG-03, TRIG-04, TRIG-05]

duration: 5min
completed: 2026-03-14
---

# Phase 7 Plan 01: PR API Endpoints Summary

**Four REST endpoints for PR auto-fix (list/comments/config/trigger) with orchestrator pipeline wiring via get_pr_summary**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-14T18:30:22Z
- **Completed:** 2026-03-14T18:35:22Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Four PR API endpoints: GET /prs, GET /prs/{n}/comments, GET /prs/config, POST /prs/{n}/auto-fix
- get_pr_summary service method for efficient single-PR metadata lookup via gh CLI
- _execute_pipeline wired to real PRAutoFixPipeline (no more NotImplementedError)
- head_branch properly threaded from trigger endpoint through orchestrator to pipeline

## Task Commits

Each task was committed atomically:

1. **Task 1: Add get_pr_summary and four PR API endpoints** - `c5e60c9a` (feat)
2. **Task 2: Wire _execute_pipeline to real PRAutoFixPipeline** - `ef8cdb37` (feat)

_Note: Task 1 was TDD with tests written first (RED), then implementation (GREEN)._

## Files Created/Modified
- `amelia/server/routes/github.py` - Four new PR endpoints alongside existing issues endpoint
- `amelia/services/github_pr.py` - get_pr_summary method for single PR metadata
- `amelia/pipelines/pr_auto_fix/orchestrator.py` - _execute_pipeline wired to PRAutoFixPipeline
- `tests/unit/server/routes/test_github_pr_routes.py` - 16 tests for all PR endpoints
- `tests/unit/services/test_github_pr_get_summary.py` - 3 tests for get_pr_summary
- `tests/unit/pipelines/pr_auto_fix/test_orchestrator.py` - 1 new test for pipeline wiring

## Decisions Made
- `enabled` flag derived from `pr_autofix is not None` since PRAutoFixConfig has no explicit enabled field
- `_get_repo_name` extracted as a separate async helper for testability (mocked in trigger tests)
- `_resolve_github_profile` extracted as shared helper to DRY profile validation across all PR endpoints
- AggressivenessLevel override uses IntEnum name lookup (`AggressivenessLevel[name.upper()]`)

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- API layer complete, ready for CLI commands (Plan 02) to call these endpoints
- Polling service (Phase 8) can also trigger via POST /prs/{n}/auto-fix
- All orchestrator tests still pass with mocked _execute_pipeline

---
*Phase: 07-cli-api-triggers*
*Completed: 2026-03-14*
