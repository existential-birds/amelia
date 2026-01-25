# External Plan Import

Allow users to provide pre-written implementation plans that bypass the Architect phase while going through the same validation as Architect-generated plans.

## Background

Currently, Amelia's Architect agent generates implementation plans. Users may want to:
- Use plans created by other tools or agents
- Provide hand-crafted plans for specific workflows
- Re-use plans across similar issues

This feature adds the ability to import external plans at workflow creation or after queueing.

## API Changes

### CreateWorkflowRequest

Two new optional fields:

```python
class CreateWorkflowRequest(BaseModel):
    # ... existing fields ...
    plan_file: str | None = None      # Path to external plan file
    plan_content: str | None = None   # Inline plan markdown content
```

**Validation rules:**
- `plan_file` and `plan_content` are mutually exclusive
- If either is provided, Architect phase is skipped
- `plan_file` paths are resolved relative to the worktree

### New Endpoint: POST /api/workflows/{id}/plan

Set or replace the plan for a queued workflow.

**Request body:**

```python
class SetPlanRequest(BaseModel):
    plan_file: str | None = None
    plan_content: str | None = None
    force: bool = False  # Required to overwrite existing plan
```

**Constraints:**
- Workflow must be in `pending` or `planning` status
- If plan exists and `force=false`, returns 409 Conflict
- No active planning task (Architect) can be running

**Response:** 200 with validated plan summary (goal, key_files, total_tasks)

### Error Responses

| Code | Condition |
|------|-----------|
| 400 | Both `plan_file` and `plan_content` provided |
| 400 | Neither `plan_file` nor `plan_content` provided |
| 400 | Workflow not in pending/planning status |
| 404 | Plan file not found |
| 409 | Plan exists and `force=false` |
| 422 | Plan validation failed |

## Implementation

### State Changes

New field on `ImplementationState`:

```python
class ImplementationState(BaseModel):
    # ... existing fields ...
    external_plan: bool = False  # True if plan was imported externally
```

### Helper Function

Shared logic for both entry points:

```python
async def import_external_plan(
    plan_file: str | None,
    plan_content: str | None,
    target_path: Path,
    profile: Profile,
    workflow_id: str,
) -> dict[str, Any]:
    """Import and validate an external plan.

    Args:
        plan_file: Path to plan file (relative to worktree or absolute)
        plan_content: Inline plan markdown content
        target_path: Where to write the plan (standard plan location)
        profile: Profile for LLM extraction config
        workflow_id: For logging

    Returns:
        Dict with goal, plan_markdown, plan_path, key_files, total_tasks

    Raises:
        FileNotFoundError: If plan_file doesn't exist
        ValueError: If validation fails
    """
```

Steps:
1. Resolve content (read from file or use inline)
2. Write to `target_path`
3. Run `plan_validator_node` logic to extract structured fields
4. Return extracted state fields

### Pipeline Changes

Conditional routing after start node:

```python
def route_after_start(state: ImplementationState) -> str:
    """Route to architect or directly to validator."""
    if state.external_plan:
        return "plan_validator"
    return "architect"
```

Graph structure:

```
START → route_after_start ─→ architect → plan_validator → human_approval → ...
                          ╰→ plan_validator ─────────────╯
```

The `plan_validator_node` is unchanged - it reads the plan file and extracts structure regardless of source.

### Workflow Creation Flow

When external plan is provided:

1. Validate `plan_file`/`plan_content` mutual exclusivity
2. Call `import_external_plan()` to write and validate
3. Set `external_plan=True` in initial state
4. Start graph - routing skips Architect
5. Continue with normal lifecycle based on `start` flag

### POST /plan Handler Flow

1. Load workflow from repository
2. Check status is `pending` or `planning`
3. Check no active planning task in `_planning_tasks`
4. Check existing plan - if exists and not `force`, return 409
5. Call `import_external_plan()`
6. Update workflow state in DB (goal, key_files, total_tasks)
7. If status was `planning`, transition to `pending`
8. Emit plan updated event
9. Return 200 with summary

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| External plan + `plan_now=true` | `plan_now` ignored, external plan implies planning done |
| External plan + `start=false` | Workflow created in `pending`, awaits manual start |
| External plan + `start=true` | Validate, then proceed to Developer |
| `POST /plan` while Architect running | 409 Conflict |
| `POST /plan` on completed workflow | 400 Bad Request |
| Relative `plan_file` path | Resolved relative to worktree |
| Empty plan content | 422 validation error |

## Testing

### Unit Tests

- `test_import_external_plan()` - file path, inline content, validation errors
- `test_route_after_start()` - routing with/without `external_plan` flag
- `test_create_workflow_request_validation()` - mutual exclusivity

### Integration Tests

Real integration tests that only mock at the external HTTP boundary (LLM API calls):

- External plan at workflow creation (file path)
- External plan at workflow creation (inline content)
- `POST /plan` on pending workflow
- `POST /plan` with `force=true` to overwrite
- `POST /plan` on wrong status (should fail)
- Full workflow: external plan → Developer → Reviewer cycle

### Test Fixtures

- Valid plan markdown matching Architect output format
- Invalid plan (missing structure)
- Temporary plan files

## Related

- Issue #268 - Non-blocking plan generation and plan re-runs
