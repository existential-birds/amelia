# Task Plan Preservation Design

## Problem

When the Developer agent starts Task B after task_reviewer approves Task A, the wrong plan content is sent. The `plan_markdown` field gets narrowed to Task A's section in `call_developer_node` and is never restored, so Task B extraction fails.

## Solution

**Option B: Don't mutate `plan_markdown`**

Keep `plan_markdown` immutable throughout the workflow. Extract task sections at prompt-building time in each agent.

## Changes

### 1. Orchestrator (`amelia/core/orchestrator.py`)

Remove `plan_markdown` mutation in `call_developer_node`:

```python
# Before (buggy)
state = state.model_copy(update={
    "driver_session_id": None,
    "plan_markdown": task_plan,  # Mutates, breaks subsequent tasks
})

# After (fixed)
state = state.model_copy(update={
    "driver_session_id": None,
    # plan_markdown stays intact
})
```

### 2. Developer (`amelia/agents/developer.py`)

Update `_build_prompt()` to extract current task section with breadcrumb:

```python
def _build_prompt(self, state: ExecutionState) -> str:
    parts = []

    if not state.plan_markdown:
        raise ValueError("Developer requires plan_markdown. Architect must run first.")

    parts.append("""
You have a detailed implementation plan to follow...
---
IMPLEMENTATION PLAN:
---
""")

    from amelia.core.orchestrator import extract_task_section

    total = state.total_tasks or 1
    current = state.current_task_index

    if total == 1:
        parts.append(state.plan_markdown)
    else:
        task_section = extract_task_section(state.plan_markdown, current)
        task_num = current + 1
        if current > 0:
            parts.append(f"Tasks 1-{current} of {total} completed. Now executing Task {task_num}:\n\n")
        else:
            parts.append(f"Executing Task 1 of {total}:\n\n")
        parts.append(task_section)

    parts.append(f"\n\nPlease complete the following task:\n\n{state.goal}")

    if state.last_review and not state.last_review.approved:
        feedback = "\n".join(f"- {c}" for c in state.last_review.comments)
        parts.append(f"\n\nThe reviewer requested the following changes:\n{feedback}")

    return "\n".join(parts)
```

### 3. Reviewer (`amelia/agents/reviewer.py`)

Update `_extract_task_context()` to extract current task section:

```python
def _extract_task_context(self, state: ExecutionState) -> str | None:
    if not state.plan_markdown:
        return None

    from amelia.core.orchestrator import extract_task_section

    total = state.total_tasks or 1
    current = state.current_task_index

    if total == 1:
        return f"**Task:**\n\n{state.plan_markdown}"

    task_section = extract_task_section(state.plan_markdown, current)
    return f"**Current Task ({current + 1}/{total}):**\n\n{task_section}"
```

## Design Decisions

### No completed task summaries for Developer

The Developer gets a minimal breadcrumb ("Tasks 1-2 of 5 completed. Now executing Task 3:") rather than a summary of what previous tasks accomplished. Rationale: each task starts with a fresh git state (previous task committed) and fresh driver session, so detailed history adds noise without value.

### No cross-task context for Reviewer

The task_reviewer doesn't need to know what Task A accomplished because:
1. `next_task_node` commits Task A before transitioning to Task B
2. The reviewer's diff is computed from the post-Task-A commit
3. Task A's changes aren't in the diff—they're already committed

### Default single-task behavior

If `total_tasks` is `None`, treat the entire plan as one task. This provides graceful degradation without maintaining separate code paths.

### No backwards compatibility

Removed `state.goal` and `state.issue` fallback branches. The plan is the source of truth.

## Testing Strategy

**Integration-first, extend existing tests, DRY.**

1. Extend `tests/integration/test_task_based_execution.py`:
   - Verify `plan_markdown` unchanged across task transitions
   - Test full flow: Developer → Reviewer → next_task → Developer
   - Assert each agent receives correct extracted section

2. Unit tests for new logic:
   - `tests/unit/agents/test_developer.py`: `_build_prompt()` with task extraction
   - `tests/unit/agents/test_reviewer.py`: `_extract_task_context()` with task extraction
   - Use fixtures and parametrized tests for DRY

## Implementation Order

1. Write integration test (TDD)
2. Fix orchestrator - remove mutation
3. Update Developer - add extraction + breadcrumb
4. Update Reviewer - add extraction
5. Add unit tests for edge cases
6. Cleanup dead code paths

## Files Changed

| File | Change |
|------|--------|
| `amelia/core/orchestrator.py` | Remove `plan_markdown` mutation |
| `amelia/agents/developer.py` | Task extraction + breadcrumb in `_build_prompt()` |
| `amelia/agents/reviewer.py` | Task extraction in `_extract_task_context()` |
| `tests/integration/test_task_based_execution.py` | Full flow tests |
| `tests/unit/agents/test_developer.py` | Prompt building tests |
| `tests/unit/agents/test_reviewer.py` | Context extraction tests |
