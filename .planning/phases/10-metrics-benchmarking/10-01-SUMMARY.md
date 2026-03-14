---
phase: 10-metrics-benchmarking
plan: 01
subsystem: database, pipeline
tags: [metrics, asyncpg, pydantic, time.monotonic, sha256, audit-log]

# Dependency graph
requires:
  - phase: 09-events-dashboard
    provides: PRAutoFixOrchestrator with WorkflowRepository, classify_node pipeline
provides:
  - pr_autofix_runs and pr_autofix_classifications database tables
  - MetricsRepository with save/query methods
  - Pydantic response models for metrics API
  - Instrumented orchestrator with timing and per-comment counters
  - Classification audit logging in classify_node
  - get_prompt_hash utility for prompt tracking
affects: [10-02 (API endpoints), 10-03 (dashboard visualization)]

# Tech tracking
tech-stack:
  added: [hashlib (stdlib)]
  patterns: [metrics failure isolation, per-comment counting via comment_ids, prompt hash tracking]

key-files:
  created:
    - amelia/server/database/migrations/009_add_pr_autofix_metrics.sql
    - amelia/server/models/metrics.py
    - amelia/server/database/metrics_repository.py
    - tests/unit/server/database/test_metrics_repository.py
    - tests/unit/pipelines/pr_auto_fix/test_metrics_collection.py
  modified:
    - amelia/server/database/__init__.py
    - amelia/pipelines/pr_auto_fix/orchestrator.py
    - amelia/pipelines/pr_auto_fix/nodes.py
    - amelia/services/classifier.py

key-decisions:
  - "MetricsRepository in separate file (metrics_repository.py) matching profile_repository.py pattern"
  - "Metrics persistence failures log warning but do not crash the pipeline (failure isolation)"
  - "Per-comment counting iterates group_results.comment_ids not group count (Pitfall 3)"
  - "Prompt hash uses SHA-256 of stripped system prompt, first 16 hex chars"
  - "Classification audit data passed via RunnableConfig configurable dict (metrics_repo + metrics_run_id)"

patterns-established:
  - "Metrics failure isolation: wrap save in try/except with logger.warning"
  - "Per-comment counting: iterate comment_ids on GroupFixResult, not group-level counts"
  - "Prompt hash: hashlib.sha256(prompt.strip().encode()).hexdigest()[:16]"

requirements-completed: [METR-01, METR-03, METR-05, METR-06]

# Metrics
duration: 7min
completed: 2026-03-14
---

# Phase 10 Plan 01: Metrics Data Layer Summary

**Database tables, Pydantic models, MetricsRepository, and instrumented orchestrator/classify_node for PR auto-fix metrics collection and persistence**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-14T23:20:37Z
- **Completed:** 2026-03-14T23:27:20Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Migration 009 creates pr_autofix_runs and pr_autofix_classifications tables with proper indexes
- MetricsRepository provides save_run_metrics, save_classifications, get_metrics_summary, get_classifications
- Orchestrator measures end-to-end latency with time.monotonic() and persists per-run counters
- Classification audit logging captures comment_id, body_snippet, category, confidence, actionable, aggressiveness, prompt_hash
- All metrics failures isolated -- pipeline never crashes due to metrics write failures

## Task Commits

Each task was committed atomically:

1. **Task 1: Migration, Pydantic models, and MetricsRepository** - `806d26a6` (feat)
2. **Task 2: Instrument orchestrator and classify_node** - `b7ca119e` (feat)

## Files Created/Modified
- `amelia/server/database/migrations/009_add_pr_autofix_metrics.sql` - Two new tables with indexes
- `amelia/server/models/metrics.py` - Pydantic response models (PRAutoFixMetricsResponse, ClassificationsResponse)
- `amelia/server/database/metrics_repository.py` - MetricsRepository with 4 methods
- `amelia/server/database/__init__.py` - Export MetricsRepository
- `amelia/pipelines/pr_auto_fix/orchestrator.py` - Timing, per-comment counting, metrics persistence
- `amelia/pipelines/pr_auto_fix/nodes.py` - Classification audit logging
- `amelia/services/classifier.py` - get_prompt_hash utility
- `tests/unit/server/database/test_metrics_repository.py` - 8 unit tests
- `tests/unit/pipelines/pr_auto_fix/test_metrics_collection.py` - 7 unit tests

## Decisions Made
- MetricsRepository in separate file matching existing *_repository.py pattern
- Metrics persistence failures are isolated (warning log, no pipeline crash) per Pitfall 1
- Per-comment counting via comment_ids iteration, not group-level counting per Pitfall 3
- Classification audit data flows through RunnableConfig configurable dict
- Prompt hash normalized with .strip() before hashing per Pitfall 2

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed PRSummary construction in tests**
- **Found during:** Task 2 (test writing)
- **Issue:** PRSummary requires number, head_branch, author, updated_at fields
- **Fix:** Added all required fields to test PRSummary construction
- **Files modified:** tests/unit/pipelines/pr_auto_fix/test_metrics_collection.py
- **Committed in:** b7ca119e (Task 2 commit)

**2. [Rule 1 - Bug] Fixed driver enum value in test Profile**
- **Found during:** Task 2 (test writing)
- **Issue:** Driver enum accepts 'claude', 'codex', or 'api' -- not 'anthropic'
- **Fix:** Changed to 'claude' matching existing test conventions
- **Files modified:** tests/unit/pipelines/pr_auto_fix/test_metrics_collection.py
- **Committed in:** b7ca119e (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs in test setup)
**Impact on plan:** Both were test construction issues, not plan scope changes. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- MetricsRepository and Pydantic models ready for API endpoint wiring (Plan 10-02)
- Orchestrator and classify_node instrumented and ready to collect data
- All 2124 unit tests passing

---
*Phase: 10-metrics-benchmarking*
*Completed: 2026-03-14*
