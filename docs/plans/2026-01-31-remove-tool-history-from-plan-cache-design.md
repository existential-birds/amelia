# Remove tool_calls/tool_results from PlanCache

**Date:** 2026-01-31
**Status:** Proposed

## Problem

The `PlanCache` model stores `tool_calls` and `tool_results` fields that accumulate across the entire workflow lifecycle. These fields use `operator.add` reducers in `ImplementationState`, meaning every tool call from Architect, Developer, and Reviewer is appended throughout execution.

A complex workflow can have hundreds or thousands of tool calls, each with potentially large inputs/outputs (file contents, diffs, etc.). All of this gets serialized into the `plan_cache` JSON column in the database, causing storage bloat.

### Analysis

| Field | Size | Actually Used? | Needed in PlanCache? |
|-------|------|----------------|---------------------|
| `goal` | Small (1-2 sentences) | API response | Yes |
| `plan_markdown` | Medium (plan text) | API response, approval UI | Yes |
| `plan_path` | Small (file path) | API response | Yes |
| `total_tasks` | Tiny (int) | Task progress tracking | Yes |
| `current_task_index` | Tiny (int) | Task progress tracking | Yes |
| `tool_calls` | Large (accumulates) | API response "history" | **No** |
| `tool_results` | Large (accumulates) | API response "history" | **No** |

### Consumer Analysis

The dashboard's `WorkflowDetailPage` does **not** use `tool_calls` or `tool_results` from the workflow detail API. It only uses:
- `goal`
- `plan_markdown`
- `recent_events`
- `token_usage`
- `status`

The `toolCalls` displayed in `SpecBuilderPage` comes from WebSocket streaming, not from `WorkflowDetailResponse`.

## Solution

Remove `tool_calls` and `tool_results` from `PlanCache` and `WorkflowDetailResponse`. The data remains available in LangGraph checkpoints if ever needed for debugging.

## Changes

### 1. PlanCache Model (`amelia/server/models/state.py`)

Remove fields and simplify `from_checkpoint_values()`:

```python
class PlanCache(BaseModel):
    """Cached plan data synced from LangGraph checkpoint."""

    goal: str | None = None
    plan_markdown: str | None = None
    plan_path: str | None = None
    total_tasks: int | None = None
    current_task_index: int | None = None

    @classmethod
    def from_checkpoint_values(cls, values: dict[str, Any]) -> PlanCache:
        """Create PlanCache from LangGraph checkpoint values."""
        plan_path = values.get("plan_path")
        if plan_path is not None:
            plan_path = str(plan_path)

        return cls(
            goal=values.get("goal"),
            plan_markdown=values.get("plan_markdown"),
            plan_path=plan_path,
            total_tasks=values.get("total_tasks"),
            current_task_index=values.get("current_task_index"),
        )
```

Key changes:
- Remove `tool_calls` and `tool_results` fields
- Read `plan_path` directly from checkpoint values (no longer derived from scanning tool calls)
- Remove ~30 lines of serialization logic

### 2. WorkflowDetailResponse (`amelia/server/models/responses.py`)

Remove fields:
- `tool_calls: list[dict[str, Any]]`
- `tool_results: list[dict[str, Any]]`

### 3. Workflow Route (`amelia/server/routes/workflows.py`)

In `get_workflow()`:
- Remove `tool_calls` and `tool_results` local variables
- Remove extraction from `workflow.plan_cache`
- Remove from `WorkflowDetailResponse` construction

### 4. Tests (`tests/unit/server/models/test_state.py`)

Update `TestPlanCache` class:

| Test Method | Changes |
|-------------|---------|
| `test_create_plan_cache_with_defaults` | Remove `tool_calls`/`tool_results` assertions |
| `test_create_plan_cache_with_values` | Remove from constructor and assertions |
| `test_from_checkpoint_values_extracts_plan_path` | Rename to `test_from_checkpoint_values`; pass `plan_path` directly in test values |
| `test_from_checkpoint_values_handles_missing_values` | Remove `tool_calls`/`tool_results` assertions |

## What Stays Unchanged

- `ImplementationState.tool_calls/tool_results` - Still needed for LangGraph state accumulation during workflow execution
- WebSocket streaming of tool calls - Separate system, unaffected
- Checkpoint storage - LangGraph still stores full state; we just don't cache it in `plan_cache`

## Impact

- **Storage:** Removes potentially megabytes of accumulated tool call data per workflow
- **API:** Breaking change for any external consumers relying on `tool_calls`/`tool_results` in workflow detail response (none known)
- **Dashboard:** No changes needed - fields were never used
