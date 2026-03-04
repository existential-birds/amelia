# Daytona Sandbox Provider Design

## Goal

Run Amelia workflows inside ephemeral Daytona cloud sandboxes instead of local Docker containers, enabling remote execution with managed infrastructure.

## Approach

Hybrid of drop-in `SandboxProvider` (minimal integration surface) and native Daytona API usage (idiomatic lifecycle/git). The existing `ContainerDriver` and `WorktreeManager` are reused; only the sandbox provider is new.

### Architecture

```
Profile (mode="daytona")
  -> get_driver() factory
    -> DaytonaSandboxProvider (new)
      -> ContainerDriver (existing, unchanged)
        -> WorktreeManager (existing, unchanged)
```

### Workflow Lifecycle

1. `ensure_running()` creates an ephemeral Daytona sandbox via `daytona.create()` and clones the repo using Daytona's native `sandbox.git.clone()`.
2. `WorktreeManager` creates a worktree branch inside the sandbox (via `exec_stream` — git worktree commands).
3. Agents execute (Architect, Developer, Reviewer) — worker runs via `exec_stream` wrapping `sandbox.process.exec()`.
4. `WorktreeManager.push()` pushes the branch from inside the sandbox.
5. `teardown()` deletes the ephemeral sandbox via `sandbox.delete()`.

## Data Model Changes

### `SandboxMode` enum

Add `DAYTONA = "daytona"`.

### `DaytonaResources` model (new)

```python
class DaytonaResources(BaseModel):
    cpu: int = 2
    memory: int = 4   # GB
    disk: int = 10     # GB
```

### `SandboxConfig` additions

```python
repo_url: str | None = None              # Git remote URL for remote sandboxes
daytona_api_url: str = "https://app.daytona.io/api"
daytona_target: str = "us"
daytona_resources: DaytonaResources | None = None
```

`DAYTONA_API_KEY` is read from the environment (not stored in config/DB), consistent with `OPENROUTER_API_KEY`.

## New File: `amelia/sandbox/daytona.py`

`DaytonaSandboxProvider` implements the `SandboxProvider` protocol:

- **`ensure_running()`** — `daytona.create()` with configured resources + `sandbox.git.clone()`. No-op if sandbox already healthy.
- **`exec_stream()`** — wraps `sandbox.process.exec()`, yields stdout lines. Used by `ContainerDriver` for worker invocation and by `WorktreeManager` for git worktree/push commands.
- **`teardown()`** — `sandbox.delete()`.
- **`health_check()`** — `sandbox.process.exec("true")`, checks exit code.

### Native vs shell-out boundary

| Operation | Method |
|---|---|
| Sandbox creation | Native `daytona.create()` |
| Repo clone | Native `sandbox.git.clone()` |
| Sandbox deletion | Native `sandbox.delete()` |
| Worker execution | Shell via `exec_stream` |
| Git worktree/push | Shell via `exec_stream` (no native Daytona API) |

## Factory Changes

`get_driver()` in `amelia/drivers/factory.py`:

- When `sandbox_config.mode == "daytona"`: read `DAYTONA_API_KEY` from env, raise `ValueError` if missing. Instantiate `DaytonaSandboxProvider`, wrap in `ContainerDriver`.
- CLI drivers (`claude`, `codex`) rejected with Daytona mode (same as Docker).

## Dashboard Changes

### TypeScript types (`dashboard/src/api/settings.ts`)

- `SandboxConfig.mode`: add `'daytona'` to union
- Add optional fields: `repo_url`, `daytona_api_url`, `daytona_target`, `daytona_resources`

### Profile edit modal

- When `mode === "daytona"`: hide Docker `image` field, show Daytona fields (api_url, target, resources, repo_url)
- Note in UI: "Set `DAYTONA_API_KEY` environment variable"

## Testing

### Unit tests

- `tests/unit/sandbox/test_daytona_provider.py` — mock Daytona SDK client, verify `ensure_running()` calls `create()` + `git.clone()`, `teardown()` calls `delete()`, `exec_stream()` wraps `process.exec()`
- `tests/unit/drivers/test_factory.py` — extend: `mode="daytona"` produces correct driver, missing env var raises, CLI drivers rejected
- `tests/unit/core/test_sandbox_config.py` — extend: `DaytonaResources`, `repo_url`, `SandboxMode.DAYTONA` roundtrip

### Integration tests

- `tests/integration/test_daytona_sandbox.py` — `DaytonaSandboxProvider` + `ContainerDriver` + `WorktreeManager` together, mocking at the Daytona SDK boundary

## Dependencies

- `daytona-sdk` added to `pyproject.toml` (currently ~v0.148.0 on PyPI)
