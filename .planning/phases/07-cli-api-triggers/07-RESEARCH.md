# Phase 7: CLI & API Triggers - Research

**Researched:** 2026-03-14
**Domain:** CLI commands (Typer) + FastAPI REST endpoints for PR auto-fix triggering
**Confidence:** HIGH

## Summary

Phase 7 adds manual trigger points for the PR auto-fix pipeline: two CLI commands (`fix-pr`, `watch-pr`) and three REST API endpoints. The codebase already has well-established patterns for every component: the `review` command in `main.py` demonstrates CLI-to-API-to-WebSocket streaming, the `list_github_issues` endpoint in `server/routes/github.py` demonstrates profile-scoped GitHub API routes, and `PRAutoFixOrchestrator.trigger_fix_cycle()` is the entry point for fix cycles.

This phase is primarily an integration/wiring exercise. No new architectural patterns are needed -- every building block exists. The key implementation challenge is correctly populating `head_branch` (currently defaulting to empty string) by fetching PR metadata before calling the orchestrator, and wiring the `_execute_pipeline` method that currently raises `NotImplementedError`.

**Primary recommendation:** Follow existing patterns exactly. `fix-pr` mirrors the `review` command pattern. API endpoints go in `server/routes/github.py`. Client methods go in `client/api.py`. All PR data comes from `GitHubPRService` which already has `list_open_prs()` and `fetch_review_comments()`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- `fix-pr` streams events in real-time via WebSocket (same pattern as existing `review` command)
- Streaming is the default behavior -- no `--stream` flag needed. Add `--quiet/-q` to suppress streaming
- After streaming completes, print a compact summary table: X comments fixed, Y skipped, Z failed, plus commit SHA if fixes were pushed
- `fix-pr` goes through the server API: calls `POST /api/github/prs/{n}/auto-fix`, then streams events via WebSocket. Requires server running.
- `watch-pr` goes through the server API -- calls the trigger endpoint repeatedly on a timer, streams events for each cycle
- Between cycles, show a status line: "Waiting for new comments... next check in Xs"
- Continuous event stream for each active cycle (same as fix-pr)
- Auto-stops when all comments are resolved (zero unresolved comments remain after a cycle). Ctrl+C always works to stop early.
- No additional `--until` flags or `--max-cycles` for v1
- `POST /api/github/prs/{number}/auto-fix` returns 202 Accepted with a workflow ID immediately (async). Caller tracks progress via WebSocket events.
- Endpoint accepts optional JSON body with aggressiveness level override. No body = use profile default.
- `GET /api/github/prs` and `GET /api/github/prs/{number}/comments` require a `?profile=name` query param (consistent with existing `GET /api/github/issues`)
- All PR routes go in the existing `amelia/server/routes/github.py` module alongside the issues endpoint. Router already mounted at `/api/github`.
- CLI commands require explicit `--profile/-p` flag (required, not optional). Consistent with existing `review` command.
- CLI validates client-side that the profile has `pr_autofix` enabled (not None) before triggering. Clear error message: "PR auto-fix not enabled on profile X. Configure it in the dashboard."
- Both `fix-pr` and `watch-pr` accept `--aggressiveness/-a` flag for per-PR override (critical/standard/thorough). Omit = use profile default. Matches Phase 1 ephemeral override decision.

### Claude's Discretion
- Exact CLI command placement (top-level in main.py vs subcommands vs client/cli.py)
- Pydantic request/response models for the API endpoints
- How watch-pr's polling timer integrates with the server-side cooldown from Phase 6
- WebSocket event filtering for PR auto-fix events vs other workflow events
- Error handling and retry behavior for server unreachable during watch-pr cycles

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TRIG-01 | CLI `fix-pr <number>` command triggers one-shot fix for a PR's unresolved comments | Follow `review` command pattern: POST to trigger endpoint, stream via WebSocket, print summary |
| TRIG-02 | CLI `watch-pr <number>` command polls a single PR at configurable interval | Loop calling fix-pr trigger + check unresolved count, auto-stop on zero |
| TRIG-03 | API endpoint `POST /api/github/prs/{number}/auto-fix` triggers fix manually | Add to `github.py` router, resolve profile, call `PRAutoFixOrchestrator.trigger_fix_cycle()` |
| TRIG-04 | API endpoint `GET /api/github/prs` lists open PRs for a profile | Delegate to `GitHubPRService.list_open_prs()`, same pattern as `list_github_issues` |
| TRIG-05 | API endpoint `GET /api/github/prs/{number}/comments` returns unresolved comments | Delegate to `GitHubPRService.fetch_review_comments()` |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Typer | (existing) | CLI framework | Already used for all CLI commands in `main.py` and `client/cli.py` |
| FastAPI | (existing) | REST API framework | Already used for all server endpoints |
| httpx | (existing) | Async HTTP client | Already used in `AmeliaClient` for CLI-to-server communication |
| websockets | (existing) | WebSocket streaming | Already used in `stream_workflow_events()` |
| Rich | (existing) | CLI output formatting | Already used in `client/cli.py` for tables, styled output |
| Pydantic | (existing) | Request/response models | Already used everywhere for data validation |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio | stdlib | Async timer for watch-pr polling | `asyncio.sleep()` for polling interval between cycles |

### Alternatives Considered
None -- all libraries are already in use. No new dependencies needed.

## Architecture Patterns

### Recommended Structure (files to modify/create)
```
amelia/
├── main.py                     # Add fix_pr and watch_pr commands (top-level like review)
├── client/
│   ├── api.py                  # Add trigger_pr_autofix(), list_prs(), get_pr_comments() methods
│   └── models.py               # Add TriggerPRAutoFixRequest, TriggerPRAutoFixResponse, etc.
├── server/
│   └── routes/
│       └── github.py           # Add 3 new endpoints alongside list_github_issues
└── pipelines/
    └── pr_auto_fix/
        └── orchestrator.py     # Wire _execute_pipeline (may remain a Phase 7 seam if pipeline not ready)
tests/
└── unit/
    ├── test_fix_pr_command.py       # CLI command tests
    ├── test_watch_pr_command.py     # CLI watch-pr tests
    └── server/
        └── routes/
            └── test_github_pr_routes.py  # API endpoint tests
```

### Pattern 1: CLI Command (mirrors `review` command)
**What:** Top-level Typer command that calls server API, then streams events via WebSocket
**When to use:** `fix-pr` command
**Example:**
```python
# Source: amelia/main.py review command (lines 53-120)
@app.command(name="fix-pr")
def fix_pr(
    pr_number: Annotated[int, typer.Argument(help="PR number to fix")],
    profile_name: Annotated[str, typer.Option("--profile", "-p", help="Profile name")] = ...,  # Required
    aggressiveness: Annotated[str | None, typer.Option("--aggressiveness", "-a")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
) -> None:
    async def _run() -> None:
        client = AmeliaClient()
        # 1. Validate profile has pr_autofix enabled (client-side)
        # 2. POST /api/github/prs/{pr_number}/auto-fix
        # 3. Stream events via WebSocket (unless --quiet)
        # 4. Print summary table
    asyncio.run(_run())
```

### Pattern 2: API Endpoint (mirrors `list_github_issues`)
**What:** FastAPI endpoint with profile query param, `gh` CLI delegation
**When to use:** All three new endpoints
**Example:**
```python
# Source: amelia/server/routes/github.py (lines 66-138)
@router.get("/prs", response_model=PRListResponse)
async def list_prs(
    profile: str = Query(..., description="Profile name"),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> PRListResponse:
    # 1. Resolve profile, validate tracker type
    # 2. Create GitHubPRService(resolved.repo_root)
    # 3. Call service.list_open_prs()
    # 4. Return response model
```

### Pattern 3: Async Trigger (202 Accepted)
**What:** POST endpoint that spawns async work and returns immediately
**When to use:** `POST /api/github/prs/{number}/auto-fix`
**Example:**
```python
@router.post("/prs/{number}/auto-fix", status_code=202)
async def trigger_pr_autofix(
    number: int,
    body: TriggerPRAutoFixRequest | None = None,
    profile: str = Query(...),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> TriggerPRAutoFixResponse:
    # 1. Resolve profile, validate pr_autofix enabled
    # 2. Fetch PR metadata to get head_branch
    # 3. Build config override if aggressiveness provided
    # 4. Create asyncio.Task for orchestrator.trigger_fix_cycle()
    # 5. Return 202 with workflow_id from orchestrator._get_workflow_id()
```

### Pattern 4: watch-pr Polling Loop
**What:** CLI command that repeatedly triggers fix-pr and checks for remaining comments
**When to use:** `watch-pr` command
**Example:**
```python
@app.command(name="watch-pr")
def watch_pr(...) -> None:
    async def _run() -> None:
        client = AmeliaClient()
        while True:
            # 1. Trigger fix via API
            # 2. Stream events until cycle completes
            # 3. Check unresolved comment count via GET /api/github/prs/{n}/comments
            # 4. If zero unresolved: break (auto-stop)
            # 5. Display "Waiting for new comments... next check in Xs"
            # 6. await asyncio.sleep(interval)
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching.[/dim]")
```

### Anti-Patterns to Avoid
- **Calling orchestrator directly from CLI:** CLI MUST go through server API. The `review` command sets this precedent -- CLI is a thin HTTP client.
- **Creating a new router module:** All PR routes belong in the existing `github.py` router. Don't create `pr.py`.
- **Making --profile optional:** Context decision requires it to be required (no default). Use `typer.Option(..., "--profile", "-p")` with no default.
- **Blocking the event loop in watch-pr:** Use `asyncio.sleep()` not `time.sleep()` for the polling interval.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PR metadata fetching | Custom `gh pr view` calls | `GitHubPRService.list_open_prs()` to get head_branch | Already returns `PRSummary` with `head_branch` field |
| Comment fetching | Custom REST/GraphQL | `GitHubPRService.fetch_review_comments()` | Already handles thread resolution, filtering, pagination |
| WebSocket streaming | Custom WebSocket client | `stream_workflow_events()` from `client/streaming.py` | Handles subscribe, ping/pong, backfill, event display |
| Profile resolution in routes | Manual DB queries | `ProfileRepository` via `Depends(get_profile_repository)` | Existing pattern in `list_github_issues` |
| CLI error handling | Custom try/except patterns | `_handle_workflow_api_error()` from `client/cli.py` | Already handles all `AmeliaClientError` subtypes |
| Event emission | Manual event construction | `PRAutoFixOrchestrator._emit_event()` | Already handles workflow ID, timestamp, bus emission |

## Common Pitfalls

### Pitfall 1: head_branch Must Be Populated
**What goes wrong:** Calling `trigger_fix_cycle()` without fetching the PR's head branch means `_reset_to_remote()` skips checkout/reset (branch empty string check at line 308-310 of orchestrator.py).
**Why it happens:** Phase 6 deferred head_branch population to Phase 7 (empty string default).
**How to avoid:** The trigger endpoint MUST fetch PR metadata (via `GitHubPRService` or a targeted `gh pr view` call) to get `head_branch` before calling the orchestrator.
**Warning signs:** Orchestrator runs but doesn't reset to remote HEAD, leading to stale code fixes.

### Pitfall 2: _execute_pipeline Is NotImplementedError
**What goes wrong:** The orchestrator's `_execute_pipeline()` raises `NotImplementedError`. Triggering a fix cycle will fail.
**Why it happens:** Phase 6 left this as a seam for testing. The real pipeline (`PRAutoFixPipeline`) exists from Phase 4-5 but isn't wired in.
**How to avoid:** Wire `_execute_pipeline` to create and run the actual `PRAutoFixPipeline`. This is a critical integration point.
**Warning signs:** All fix cycles fail with `NotImplementedError`.

### Pitfall 3: Profile pr_autofix Can Be None
**What goes wrong:** Profiles without `pr_autofix` configured (it's a nullable JSONB column) will crash when trying to access config fields.
**Why it happens:** Phase 1 decision: `None` means feature disabled. Not all profiles have it configured.
**How to avoid:** CLI validates client-side before triggering. API endpoint returns 400 if `profile.pr_autofix` is None.
**Warning signs:** `AttributeError: 'NoneType' object has no attribute 'aggressiveness'`

### Pitfall 4: Repo Resolution for GitHubPRService
**What goes wrong:** `GitHubPRService` needs `repo_root` (filesystem path) for `gh` CLI commands, but the API needs `repo` in `owner/repo` format for the orchestrator.
**Why it happens:** Two different contexts: `gh pr list` needs CWD set to repo root, orchestrator needs `owner/repo` for GitHub API URLs.
**How to avoid:** Profile has `repo_root` for filesystem path. Extract `owner/repo` from the git remote or profile configuration. The `list_github_issues` endpoint shows the pattern of using `resolved.repo_root` as CWD.
**Warning signs:** `gh` CLI failures about "not a git repository" or orchestrator failures with invalid repo format.

### Pitfall 5: asyncio.run() Cannot Be Nested
**What goes wrong:** watch-pr command uses `asyncio.run()` which creates a new event loop. Cannot call it multiple times or nest it.
**Why it happens:** The existing pattern of `asyncio.run(_run())` with the entire polling loop inside `_run()` works. But if you try to call `asyncio.run()` for each iteration, it fails.
**How to avoid:** Put the entire watch-pr loop inside a single `async def _run()` and call `asyncio.run(_run())` once. All awaits happen within that single event loop.
**Warning signs:** `RuntimeError: This event loop is already running`

### Pitfall 6: watch-pr Auto-Stop Check Needs Server Round-Trip
**What goes wrong:** After a fix cycle completes, watch-pr needs to check if unresolved comments remain. This requires another API call, not just checking the fix cycle result.
**Why it happens:** New comments may have arrived during the fix cycle, or some comments may have been classified as non-actionable.
**How to avoid:** After each fix cycle, call `GET /api/github/prs/{n}/comments` to get the current unresolved count. If zero, stop.
**Warning signs:** watch-pr stops prematurely or runs forever.

## Code Examples

### CLI fix-pr Command Structure
```python
# Source: Pattern from amelia/main.py:53-120 (review command)
@app.command(name="fix-pr")
def fix_pr(
    pr_number: Annotated[int, typer.Argument(help="PR number to fix")],
    profile_name: Annotated[str, typer.Option("--profile", "-p", help="Profile name (required)")] = ...,
    aggressiveness: Annotated[str | None, typer.Option("--aggressiveness", "-a", help="Override: critical/standard/thorough")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress event streaming")] = False,
) -> None:
    """Fix unresolved PR review comments in one shot."""
    async def _run() -> None:
        client = AmeliaClient()
        try:
            response = await client.trigger_pr_autofix(
                pr_number=pr_number,
                profile=profile_name,
                aggressiveness=aggressiveness,
            )
            typer.echo(f"Triggered auto-fix for PR #{pr_number}: {response.workflow_id}")
            if not quiet:
                await stream_workflow_events(response.workflow_id)
            # Print summary
        except ServerUnreachableError:
            typer.echo("Server not running. Start with: amelia server", err=True)
            raise typer.Exit(code=1) from None
    asyncio.run(_run())
```

### API Trigger Endpoint Structure
```python
# Source: Pattern from amelia/server/routes/github.py:66-138 (list_github_issues)
class TriggerPRAutoFixRequest(BaseModel):
    aggressiveness: str | None = None  # Optional override

class TriggerPRAutoFixResponse(BaseModel):
    workflow_id: str
    message: str

@router.post("/prs/{number}/auto-fix", status_code=202, response_model=TriggerPRAutoFixResponse)
async def trigger_pr_autofix(
    number: int,
    body: TriggerPRAutoFixRequest | None = None,
    profile: str = Query(..., description="Profile name"),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> TriggerPRAutoFixResponse:
    resolved = await profile_repo.get_profile(profile)
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")
    if resolved.pr_autofix is None:
        raise HTTPException(status_code=400, detail=f"PR auto-fix not enabled on profile '{profile}'")

    # Fetch PR metadata for head_branch
    service = GitHubPRService(resolved.repo_root)
    # ... get head_branch from PR metadata
    # Build config override if aggressiveness specified
    # Spawn async task for orchestrator
    # Return 202 with workflow_id
```

### AmeliaClient Method for Trigger
```python
# Source: Pattern from amelia/client/api.py (create_review_workflow)
async def trigger_pr_autofix(
    self,
    pr_number: int,
    profile: str,
    aggressiveness: str | None = None,
) -> TriggerPRAutoFixResponse:
    body = {}
    if aggressiveness:
        body["aggressiveness"] = aggressiveness
    async with self._http_client() as client:
        response = await client.post(
            f"{self.base_url}/api/github/prs/{pr_number}/auto-fix",
            params={"profile": profile},
            json=body if body else None,
        )
        if response.status_code == 202:
            return TriggerPRAutoFixResponse.model_validate(response.json())
        self._handle_workflow_create_errors(response)
    raise RuntimeError("Unexpected code path")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| head_branch defaults to empty string | Phase 7 populates real head_branch | Phase 6 -> Phase 7 | Orchestrator actually resets to remote HEAD before fixing |
| _execute_pipeline raises NotImplementedError | Phase 7 wires to real PRAutoFixPipeline | Phase 6 -> Phase 7 | Fix cycles actually run the pipeline |

## Open Questions

1. **How to get single PR metadata for head_branch**
   - What we know: `GitHubPRService.list_open_prs()` returns all open PRs with head_branch. Could filter by number.
   - What's unclear: Whether fetching all open PRs just to get one PR's head_branch is inefficient.
   - Recommendation: Add a `get_pr_summary(pr_number)` method to `GitHubPRService` that calls `gh pr view {number} --json headRefName,number,title,author,updatedAt`. More efficient than listing all.

2. **How to determine the `repo` (owner/repo) format string**
   - What we know: Orchestrator needs `repo` in `owner/repo` format. Profile has `repo_root` (filesystem path).
   - What's unclear: Whether there's an existing utility to extract owner/repo from a git remote.
   - Recommendation: Use `gh repo view --json nameWithOwner -q .nameWithOwner` in the repo_root directory, or parse from git remote URL. Could also add to profile configuration.

3. **Wiring _execute_pipeline**
   - What we know: The PRAutoFixPipeline graph exists from Phase 4-5. The orchestrator has a seam method.
   - What's unclear: Whether the pipeline needs additional wiring or if it can be called directly.
   - Recommendation: Import and invoke the pipeline inside `_execute_pipeline`. This may require creating the graph instance and invoking it with appropriate state.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio (auto mode) |
| Config file | pyproject.toml |
| Quick run command | `uv run pytest tests/unit/ -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRIG-01 | `fix-pr` CLI triggers one-shot fix | unit | `uv run pytest tests/unit/test_fix_pr_command.py -x` | Wave 0 |
| TRIG-02 | `watch-pr` CLI polls at configurable interval | unit | `uv run pytest tests/unit/test_watch_pr_command.py -x` | Wave 0 |
| TRIG-03 | POST /api/github/prs/{number}/auto-fix triggers fix | unit | `uv run pytest tests/unit/server/routes/test_github_pr_routes.py::test_trigger_autofix -x` | Wave 0 |
| TRIG-04 | GET /api/github/prs lists open PRs | unit | `uv run pytest tests/unit/server/routes/test_github_pr_routes.py::test_list_prs -x` | Wave 0 |
| TRIG-05 | GET /api/github/prs/{number}/comments returns unresolved | unit | `uv run pytest tests/unit/server/routes/test_github_pr_routes.py::test_get_pr_comments -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/server/routes/test_github_pr_routes.py` -- covers TRIG-03, TRIG-04, TRIG-05
- [ ] `tests/unit/test_fix_pr_command.py` -- covers TRIG-01
- [ ] `tests/unit/test_watch_pr_command.py` -- covers TRIG-02
- [ ] `tests/unit/server/routes/__init__.py` -- package init if missing

## Sources

### Primary (HIGH confidence)
- `amelia/main.py` -- review command pattern (lines 53-120)
- `amelia/client/api.py` -- AmeliaClient HTTP methods
- `amelia/client/streaming.py` -- WebSocket streaming implementation
- `amelia/server/routes/github.py` -- list_github_issues endpoint pattern
- `amelia/pipelines/pr_auto_fix/orchestrator.py` -- PRAutoFixOrchestrator with trigger_fix_cycle
- `amelia/services/github_pr.py` -- GitHubPRService with list_open_prs, fetch_review_comments
- `amelia/client/cli.py` -- CLI patterns (start_command, error handling)
- `amelia/core/types.py` -- PRAutoFixConfig, PRSummary, AggressivenessLevel models

### Secondary (MEDIUM confidence)
- `amelia/server/dependencies.py` -- FastAPI dependency injection pattern

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use, no new dependencies
- Architecture: HIGH -- every pattern has an existing exemplar in the codebase
- Pitfalls: HIGH -- identified from direct code reading of Phase 6 seams and data models

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable -- internal codebase patterns)
