# Plan Import UX Improvements

Issue: #448

## Problem

Two friction points in the external plan import flow:

1. Users must manually type file paths. The profile already knows `plan_output_dir` but the modal ignores it.
2. The modal blocks for 3-10s during LLM-powered plan extraction. The user stares at a spinner.

## Design

### 1. Plan File Dropdown

Replace the text input in file mode with a **Combobox** (using the existing `Command` component from shadcn/ui) that lists `.md` files from the profile's `plan_output_dir`.

**New backend endpoint:**

```
GET /api/files/list?directory={relative_path}&workflow_id={id}
```

Response:
```json
{
  "files": [
    { "name": "2026-02-15-issue-123.md", "relative_path": "docs/plans/2026-02-15-issue-123.md", "size_bytes": 4210, "modified_at": "2026-02-15T10:30:00Z" }
  ],
  "directory": "docs/plans"
}
```

Security: the endpoint resolves `directory` against the workflow's `working_dir` and rejects paths that escape it (same traversal check as `import_external_plan`).

**Frontend behavior:**

- Auto-fetch file list when the modal opens (not lazy)
- Combobox with built-in search/filter
- Files sorted by modification time, newest first
- Display filename + relative age (e.g. "2m ago", "yesterday")
- Empty state: "No .md files found in docs/plans/" with muted text
- Loading state: skeleton lines inside the dropdown
- Error state: inline error message below the combobox
- Selecting a file auto-triggers the existing preview logic (no separate Preview button)
- Paste mode remains unchanged

**Combobox styling:**

- Dark background matching card surface (`bg-card`)
- Gold focus ring (existing `.focus-ring` utility)
- IBM Plex Mono for filenames (monospace aids scanning path-like strings)
- Muted timestamp on the right side of each item
- Selected item gets a subtle gold left border accent

### 2. Optimistic Modal Dismiss + Async Validation

Split `set_workflow_plan()` into a fast synchronous path and a background async extraction.

**Fast path (returns immediately):**

1. Read file content (or accept pasted content)
2. Validate non-empty, basic markdown check
3. Write to target plan path (`plan_path_pattern` resolution)
4. Extract task count via regex (cheap, no LLM)
5. Save initial `PlanCache` with `goal=None` (signals "validating")
6. Return `{ status: "validating", total_tasks: N }`

**Background extraction (async task):**

1. LLM-powered extraction of goal, key_files, plan_markdown
2. Update `PlanCache` with extracted fields
3. Emit new `PLAN_VALIDATED` event (or `PLAN_VALIDATION_FAILED` on error)

**New event types:**

```python
# In EventType enum
PLAN_VALIDATED = "plan_validated"        # data: { goal, key_files, total_tasks }
PLAN_VALIDATION_FAILED = "plan_validation_failed"  # data: { error }
```

Both are persisted events (added to `PERSISTED_TYPES`).

**Frontend changes:**

**SetPlanModal:**
- On submit: close modal immediately after fast-path response
- Toast: "Plan imported ({N} tasks), validating..." (using task count from fast path)

**JobQueueItem (workflow card):**
- When `goal is None` and plan exists: show a small gold pulsing dot next to the status indicator (reuse `animate-pulse-glow` keyframe)
- On `PLAN_VALIDATED` WebSocket event: dot disappears, card refreshes to show goal
- On `PLAN_VALIDATION_FAILED` WebSocket event: dot turns destructive red, tooltip shows error message

**WorkflowDetail / ApprovalControls:**
- While validating: show skeleton placeholder for goal text
- On validation complete: populate goal and plan markdown

**API response type change:**

```typescript
// Before
interface SetPlanResponse {
  goal: string;
  key_files: string[];
  total_tasks: number;
}

// After
interface SetPlanResponse {
  status: 'validated' | 'validating';
  total_tasks: number;
  goal?: string;       // present only if status=validated (paste mode with small content may finish fast)
  key_files?: string[];
}
```

### 3. Backend Service Refactor

`OrchestratorService.set_workflow_plan()` changes:

```python
async def set_workflow_plan(self, workflow_id, plan_file, plan_content, force):
    # ... existing validation (status, conflicts, etc.) ...

    # Fast path: read + write + regex extraction
    content = await self._read_plan_content(plan_file, plan_content, working_dir)
    await self._write_plan_to_target(content, target_path)
    total_tasks = extract_task_count(content)

    # Save partial cache (goal=None signals "validating")
    plan_cache = PlanCache(goal=None, plan_markdown=content, plan_path=str(target_path), total_tasks=total_tasks)
    await self._repository.update_plan_cache(workflow_id, plan_cache)

    # Fire-and-forget background extraction
    asyncio.create_task(
        self._extract_plan_metadata(workflow_id, content, target_path, profile)
    )

    return {"status": "validating", "total_tasks": total_tasks}

async def _extract_plan_metadata(self, workflow_id, content, target_path, profile):
    try:
        result = await extract_plan_fields(content, profile)
        cache = PlanCache(goal=result.goal, plan_markdown=result.plan_markdown,
                         plan_path=str(target_path), key_files=result.key_files,
                         total_tasks=extract_task_count(content))
        await self._repository.update_plan_cache(workflow_id, cache)
        await self._emit(workflow_id, EventType.PLAN_VALIDATED, "Plan validation complete",
                        data={"goal": result.goal, "key_files": result.key_files, "total_tasks": cache.total_tasks})
    except Exception as exc:
        logger.warning("Plan extraction failed", workflow_id=workflow_id, error=str(exc))
        await self._emit(workflow_id, EventType.PLAN_VALIDATION_FAILED,
                        f"Plan validation failed: {exc}", data={"error": str(exc)})
```

The existing `import_external_plan` pipeline gets refactored: the file I/O portion is extracted into helper functions callable from the fast path, and the LLM extraction portion becomes `extract_plan_fields`.

## Files Changed

| File | Change |
|------|--------|
| `amelia/server/routes/workflows.py` | Add `GET /api/files/list` endpoint |
| `amelia/server/routes/files.py` | New router for file operations (or add to workflows) |
| `amelia/server/orchestrator/service.py` | Split `set_workflow_plan` into fast + async, add `_extract_plan_metadata` |
| `amelia/server/models/events.py` | Add `PLAN_VALIDATED`, `PLAN_VALIDATION_FAILED` event types |
| `amelia/pipelines/implementation/external_plan.py` | Extract file I/O helpers, separate LLM extraction function |
| `dashboard/src/components/PlanImportSection.tsx` | Replace text input with Combobox, auto-load files, auto-preview on select |
| `dashboard/src/components/SetPlanModal.tsx` | Close immediately on fast-path response, update response handling |
| `dashboard/src/components/JobQueueItem.tsx` | Add validation status indicator (gold pulse / red dot) |
| `dashboard/src/api/client.ts` | Add `listFiles()` method, update `SetPlanResponse` type |
| `dashboard/src/types/index.ts` | Add `FileListResponse`, `FileEntry` types, update `SetPlanResponse` |
| `dashboard/src/hooks/useWebSocket.ts` | Handle `PLAN_VALIDATED` / `PLAN_VALIDATION_FAILED` events |

## Out of Scope

- Changing paste mode flow
- Changing `plan_output_dir` or `plan_path_pattern` configuration
- Recursive directory browsing (only lists files in `plan_output_dir`)
- File upload from local machine (drag-drop in paste mode already covers this)
