---
phase: 13-fix-streaming-workflow-id-routing
plan: 01
subsystem: api
tags: [websocket, uuid, streaming, workflow-id, event-bus]

# Dependency graph
requires:
  - phase: 06-orchestrator-core
    provides: PRAutoFixOrchestrator with event emission
  - phase: 12-wire-missing-events-data
    provides: Event wiring for PR auto-fix lifecycle
provides:
  - Single unified workflow_id flowing from API route through pipeline to WebSocket delivery
  - UUID-to-string normalization in ConnectionManager broadcast filter
affects: [cli-streaming, watch-pr, fix-pr]

# Tech tracking
tech-stack:
  added: []
  patterns: [workflow-id-threading, uuid-string-normalization]

key-files:
  created: []
  modified:
    - amelia/pipelines/pr_auto_fix/orchestrator.py
    - amelia/server/routes/github.py
    - amelia/server/events/connection_manager.py
    - amelia/server/lifecycle/pr_poller.py
    - tests/unit/pipelines/pr_auto_fix/test_orchestrator.py
    - tests/unit/server/events/test_connection_manager.py
    - tests/unit/server/routes/test_github_pr_routes.py
    - tests/unit/server/lifecycle/test_pr_poller.py

key-decisions:
  - "Removed synthetic _pr_workflow_ids dict -- single uuid4() in API route replaces dual-ID system"
  - "Used workflow_id or uuid4() fallback in _execute_pipeline for polling case (no streaming client)"
  - "Used uuid4() fallback in _emit_event when workflow_id is None (WorkflowEvent requires UUID)"

patterns-established:
  - "Workflow ID threading: API route creates UUID, passes through trigger -> run -> execute pipeline chain"
  - "UUID normalization: str(event.workflow_id) before set membership check in subscription filter"

requirements-completed: [TRIG-01, TRIG-02]

# Metrics
duration: 8min
completed: 2026-03-22
---

# Phase 13 Plan 01: Fix Streaming Workflow ID Routing Summary

**Fixed two independent bugs preventing CLI streaming: workflow ID mismatch (synthetic vs real) and UUID/string type mismatch in ConnectionManager broadcast filter**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-22T02:30:28Z
- **Completed:** 2026-03-22T02:38:34Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Removed synthetic `_pr_workflow_ids` dict and `get_workflow_id()` method from orchestrator
- Threaded `workflow_id` parameter from API route through `trigger_fix_cycle` -> `_run_fix_cycle` -> `_execute_pipeline`
- Fixed UUID-to-string type mismatch in `ConnectionManager.broadcast()` subscription filter
- All 2229 unit tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Thread workflow_id (RED)** - `b99cef02` (test)
2. **Task 1: Thread workflow_id (GREEN)** - `3dce6b0f` (feat)
3. **Task 2: Fix broadcast filter (RED)** - `0de77858` (test)
4. **Task 2: Fix broadcast filter (GREEN)** - `56b82afe` (feat)
5. **Route test + lint fix** - `e1ea1653` (fix)
6. **Poller get_workflow_id removal** - `9a910a26` (fix)

## Files Created/Modified
- `amelia/pipelines/pr_auto_fix/orchestrator.py` - Removed synthetic ID system, added workflow_id threading
- `amelia/server/routes/github.py` - Create workflow_id=uuid4() in route, pass to trigger_fix_cycle
- `amelia/server/events/connection_manager.py` - Normalize UUID to str before subscription set membership check
- `amelia/server/lifecycle/pr_poller.py` - Replace get_workflow_id with uuid4()
- `tests/unit/pipelines/pr_auto_fix/test_orchestrator.py` - Added 5 workflow_id threading tests
- `tests/unit/server/events/test_connection_manager.py` - Added 2 UUID/string match tests, fixed specific_match case
- `tests/unit/server/routes/test_github_pr_routes.py` - Updated to patch uuid4 instead of mock get_workflow_id
- `tests/unit/server/lifecycle/test_pr_poller.py` - Removed mock get_workflow_id from fixture

## Decisions Made
- Removed synthetic `_pr_workflow_ids` dict entirely -- the dual-ID system was the root cause of the streaming bug
- Used `workflow_id or uuid4()` fallback in `_execute_pipeline` so polling triggers (no streaming client) still get a UUID
- Used `workflow_id or uuid4()` fallback in `_emit_event` because `WorkflowEvent.workflow_id` is a required UUID field

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed get_workflow_id references in pr_poller.py**
- **Found during:** Final verification (post Task 2)
- **Issue:** `pr_poller.py` called `self._orchestrator.get_workflow_id()` which no longer exists
- **Fix:** Replaced with `uuid4()` directly, removed mock from test fixture
- **Files modified:** amelia/server/lifecycle/pr_poller.py, tests/unit/server/lifecycle/test_pr_poller.py
- **Verification:** 30 poller tests pass
- **Committed in:** 9a910a26

**2. [Rule 3 - Blocking] Fixed route test expecting mock get_workflow_id**
- **Found during:** Final verification (post Task 2)
- **Issue:** Route test mocked `orchestrator.get_workflow_id` which no longer exists
- **Fix:** Patched `uuid4` in the route module instead
- **Files modified:** tests/unit/server/routes/test_github_pr_routes.py
- **Verification:** 5 route tests pass
- **Committed in:** e1ea1653

**3. [Rule 1 - Bug] WorkflowEvent.workflow_id requires UUID, not None**
- **Found during:** Task 1 GREEN phase
- **Issue:** `_emit_event` with `workflow_id=None` caused Pydantic ValidationError
- **Fix:** Used `workflow_id or uuid4()` fallback in `_emit_event`
- **Verification:** All orchestrator tests pass
- **Committed in:** 3dce6b0f

---

**Total deviations:** 3 auto-fixed (1 bug, 2 blocking)
**Impact on plan:** All auto-fixes necessary for correctness. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Workflow ID now flows correctly from API route through pipeline to WebSocket delivery
- CLI streaming commands (fix-pr, watch-pr) should now receive pipeline events without hanging

---
*Phase: 13-fix-streaming-workflow-id-routing*
*Completed: 2026-03-22*
