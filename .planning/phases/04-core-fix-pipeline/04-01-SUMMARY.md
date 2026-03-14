---
phase: 04-core-fix-pipeline
plan: 01
subsystem: pipeline
tags: [langgraph, pydantic, state-machine, pr-auto-fix]

# Dependency graph
requires:
  - phase: 01-models-config
    provides: PRAutoFixConfig, PRReviewComment models
  - phase: 03-comment-classification
    provides: CommentClassification schema
provides:
  - PRAutoFixState, GroupFixResult, GroupFixStatus state models
  - PRAutoFixPipeline registered in PIPELINES dict
  - create_pr_auto_fix_graph factory with 3-node linear topology
  - developer.pr_fix.system prompt
affects: [04-02, orchestration, triggers]

# Tech tracking
tech-stack:
  added: []
  patterns: [linear-graph-pipeline, stub-node-pattern]

key-files:
  created:
    - amelia/pipelines/pr_auto_fix/state.py
    - amelia/pipelines/pr_auto_fix/pipeline.py
    - amelia/pipelines/pr_auto_fix/graph.py
    - amelia/pipelines/pr_auto_fix/nodes.py
    - tests/unit/pipelines/pr_auto_fix/test_state.py
    - tests/unit/pipelines/pr_auto_fix/test_pipeline.py
  modified:
    - amelia/pipelines/registry.py
    - amelia/agents/prompts/defaults.py

key-decisions:
  - "Used regular list fields (not Annotated+operator.add) for group_results since develop node handles groups internally"
  - "PRAutoFixState defaults pipeline_type to 'pr_auto_fix' and status to 'pending' via Literal defaults"

patterns-established:
  - "Stub node pattern: async nodes returning empty dict for graph compilation before implementation"
  - "Linear graph topology: entry -> classify -> develop -> commit_push -> END"

requirements-completed: [PIPE-01, PIPE-02]

# Metrics
duration: 3min
completed: 2026-03-14
---

# Phase 04 Plan 01: PR Auto-Fix Pipeline Shell Summary

**PR auto-fix pipeline structural shell with PRAutoFixState, 3-node linear graph, registry entry, and developer.pr_fix.system prompt**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-14T01:26:18Z
- **Completed:** 2026-03-14T01:29:30Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- PRAutoFixState extending BasePipelineState with PR-specific fields (pr_number, head_branch, repo, classified_comments, file_groups, group_results, etc.)
- GroupFixStatus enum and GroupFixResult model for tracking per-group fix outcomes
- PRAutoFixPipeline with linear graph (classify_node -> develop_node -> commit_push_node -> END)
- Pipeline registered in PIPELINES dict, accessible via get_pipeline("pr_auto_fix")
- developer.pr_fix.system prompt registered in PROMPT_DEFAULTS

## Task Commits

Each task was committed atomically:

1. **Task 1: State models, prompt registration, and tests** - `c3c1c52e` (feat)
2. **Task 2: Pipeline class, graph construction, registry, and tests** - `4e9be2dd` (feat)

_TDD approach: tests written first (RED), then implementation (GREEN), lint fixes applied._

## Files Created/Modified
- `amelia/pipelines/pr_auto_fix/__init__.py` - Package exports for state models and pipeline
- `amelia/pipelines/pr_auto_fix/state.py` - GroupFixStatus, GroupFixResult, PRAutoFixState models
- `amelia/pipelines/pr_auto_fix/nodes.py` - Stub node functions (classify, develop, commit_push)
- `amelia/pipelines/pr_auto_fix/graph.py` - create_pr_auto_fix_graph factory function
- `amelia/pipelines/pr_auto_fix/pipeline.py` - PRAutoFixPipeline implementing Pipeline protocol
- `amelia/pipelines/registry.py` - Added pr_auto_fix entry to PIPELINES dict
- `amelia/agents/prompts/defaults.py` - Registered developer.pr_fix.system prompt
- `tests/unit/pipelines/pr_auto_fix/test_state.py` - 24 tests for state models and prompt
- `tests/unit/pipelines/pr_auto_fix/test_pipeline.py` - 21 tests for pipeline, graph, and registry

## Decisions Made
- Used regular list fields (not Annotated+operator.add) for group_results since the develop node handles groups internally via temporary ImplementationState instances
- PRAutoFixState defaults pipeline_type to "pr_auto_fix" and status to "pending" via Literal type defaults

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff lint violations**
- **Found during:** Task 2 (after implementation)
- **Issue:** Import sorting (I001), datetime.UTC alias (UP017), blind exception assertion (B017)
- **Fix:** Ran ruff --fix for auto-fixable issues, manually changed pytest.raises(Exception) to pytest.raises(ValidationError)
- **Files modified:** All pr_auto_fix source and test files
- **Verification:** ruff check passes clean
- **Committed in:** 4e9be2dd (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Standard lint compliance. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Pipeline shell is complete with all type contracts established
- Plan 02 can implement classify_node, develop_node, and commit_push_node against the stub functions
- All 175 existing pipeline tests pass

## Self-Check: PASSED

- All 10 files verified present on disk
- Commits c3c1c52e and 4e9be2dd verified in git log
- 175 pipeline tests passing

---
*Phase: 04-core-fix-pipeline*
*Completed: 2026-03-14*
