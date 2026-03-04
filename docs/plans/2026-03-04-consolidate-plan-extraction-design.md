# Consolidate Plan Extraction: Drop LLM, Regex-Only

**Date:** 2026-03-04
**Branch:** fix/512-quickshot-external-plan-timeout-duplicate

## Problem

Plan metadata extraction (goal, key_files, total_tasks) uses an LLM in three places:

1. `import_external_plan` → `extract_plan_fields` (blocking, used by `queue_workflow`)
2. `set_workflow_plan` → `_extract_plan_metadata` → `extract_plan_fields` (background task)
3. `plan_validator_node` in the LangGraph pipeline (during execution)

All three have regex fallbacks that produce equivalent results. Since plans follow a consistent template with `**Goal:**` and `Create:/Modify:` patterns, the LLM adds latency, cost, and failure modes for no practical benefit.

Additionally, `queue_workflow` and `set_workflow_plan` duplicate the import logic inline rather than sharing a code path.

## Design

### 1. `extract_plan_fields` becomes regex-only

Drop the LLM path. Remove the `profile` parameter. The function becomes a synchronous wrapper around:

- `_extract_goal_from_plan(content)` → goal
- `_extract_key_files_from_plan(content)` → key_files
- `extract_task_count(content)` → total_tasks
- `plan_markdown` = content as-is

Keep it async to avoid churn on callers.

### 2. `import_external_plan` adds structural validation

`import_external_plan` now does: read → write → regex extract → `validate_plan_structure`. Returns `ExternalPlanImportResult` with validation result. Callers get early feedback on malformed plans.

The `profile` parameter stays (needed for `plan_path_pattern` resolution) but is no longer passed to extraction.

### 3. `plan_validator_node` drops LLM, keeps structural validation

The node becomes: read plan from disk → regex extract → `validate_plan_structure`. Same contract (returns goal, plan_markdown, plan_path, key_files, total_tasks, plan_validation_result, plan_revision_count). The revision loop (revise → architect → plan_validator_node) stays intact.

For external plans, the node re-extracts from disk redundantly with import-time extraction. This is harmless (instant regex) and keeps graph edges simple.

### 4. `set_workflow_plan` and `queue_workflow` consolidation

**`set_workflow_plan`**: Calls `import_external_plan` instead of inlining the same steps. Returns `{"status": "ready", "goal": ..., "key_files": [...], "total_tasks": N}` synchronously. No background task, no "validating" intermediate state.

**`queue_workflow`**: Already calls `import_external_plan`. Benefits from the simplified (no-LLM) version.

Both endpoints emit `PLAN_VALIDATED` or `PLAN_VALIDATION_FAILED` events synchronously after import.

### 5. Remove `_extract_plan_metadata` background task

The entire method and its `asyncio.create_task` call in `set_workflow_plan` are removed.

### 6. Events kept, emitted synchronously

- `PLAN_VALIDATED` emitted after successful extraction + structural validation
- `PLAN_VALIDATION_FAILED` emitted when `validate_plan_structure` returns `valid=False`
- Same event data shape: `{goal, key_files, total_tasks}` for validated, `{error}` for failed
- Dashboard handlers in `JobQueueItem.tsx` unchanged

### 7. Removed artifacts

- `build_plan_extraction_prompt()` — prompt template
- `MarkdownPlanOutput` schema from `amelia/agents/schemas/architect.py` and `__init__.py`
- `extract_structured` imports from `external_plan.py` and `nodes.py`
- `_extract_plan_metadata` method from orchestrator service

### 8. Kept artifacts

- `key_files` field on `ImplementationState`, API responses, dashboard types — still populated by regex
- `plan_validator` agent config key — still used for `max_iterations` in revision loop routing
- `PLAN_VALIDATED` / `PLAN_VALIDATION_FAILED` events — emitted synchronously from import path

### 9. Test updates

- `test_external_plan.py`: Remove tests that mock `extract_structured`. Fallback tests become the primary path.
- Orchestrator service tests for `set_workflow_plan`: No background task, synchronous response with goal.
- Dashboard tests: Update `SetPlanModal` tests for changed response shape (`"ready"` instead of `"validating"`).
