# CLI Task Option Design

**Issue:** #209 - Add --task option to CLI for one-off tasks with noop tracker
**Date:** 2026-01-07
**Status:** Implemented

## Problem

The `noop` tracker returns placeholder issues with generic title/description, making it unusable for ad-hoc tasks. Users cannot provide custom task descriptions without creating real GitHub/Jira issues.

## Solution

Add `--title` and `--description` flags to CLI commands. When provided with a noop tracker, these construct the Issue directly, bypassing the tracker.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Data flow | Pass-through to orchestrator | Simple, avoids coupling tracker to CLI concerns |
| Flag structure | Separate `--title` and `--description` | More control than single combined flag |
| Non-noop behavior | Error | Prevents confusion about task source |
| Required flags | Title required, description optional | Minimum viable context for Architect |
| File input | Deferred | YAGNI; shell substitution works for power users |

## CLI Interface

```bash
# Full task
amelia start MY-TASK -p noop --title "Add logout button" --description "Add to navbar with confirmation"

# Minimal (description defaults to title)
amelia start MY-TASK -p noop --title "Fix typo in README"

# Plan command (same flags)
amelia plan MY-TASK -p noop --title "Add logout button" --description "Details..."
```

**Validation:**
- `--description` without `--title`: client-side error
- `--title` with non-noop tracker: server-side 400 error

## API Changes

### Request Model

```python
class CreateWorkflowRequest(BaseModel):
    issue_id: str
    worktree_path: str
    worktree_name: str | None = None
    profile: str | None = None
    driver: str | None = None
    task_title: str | None = None      # New
    task_description: str | None = None  # New
```

### Client Method

```python
async def create_workflow(
    self,
    issue_id: str,
    worktree_path: str,
    worktree_name: str | None = None,
    profile: str | None = None,
    task_title: str | None = None,
    task_description: str | None = None,
) -> CreateWorkflowResponse:
```

## Orchestrator Logic

```python
async def start_workflow(self, ..., task_title: str | None = None, task_description: str | None = None):
    if task_title is not None:
        if loaded_profile.tracker not in ("noop", "none"):
            raise InvalidRequestError(
                f"--title/--description requires noop tracker, not '{loaded_profile.tracker}'"
            )
        issue = Issue(
            id=issue_id,
            title=task_title,
            description=task_description or task_title,
        )
    else:
        tracker = create_tracker(loaded_profile)
        issue = tracker.get_issue(issue_id, cwd=worktree_path)
```

## Files Changed

| File | Change |
|------|--------|
| `amelia/client/cli.py` | Add `--title`/`--description` to `start_command` and `plan_command` |
| `amelia/client/api.py` | Add `task_title`/`task_description` params to `create_workflow()` |
| `amelia/server/models/requests.py` | Add fields to `CreateWorkflowRequest` |
| `amelia/server/orchestrator/service.py` | Add logic to `start_workflow()` |

## Testing

**Unit tests:**
- CLI: `--description` without `--title` errors
- Request model: `task_description` without `task_title` errors
- Orchestrator: noop tracker constructs Issue; non-noop raises error

**Integration tests:**
- `POST /workflows` with task fields and noop profile succeeds
- `POST /workflows` with task fields and GitHub profile returns 400
