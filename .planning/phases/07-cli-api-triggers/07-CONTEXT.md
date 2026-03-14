# Phase 7: CLI & API Triggers - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Manual trigger points for PR auto-fix: CLI commands (`fix-pr`, `watch-pr`) and REST API endpoints for listing PRs, viewing comments, and triggering fixes. No background polling (Phase 8), no dashboard integration (Phase 9), no metrics (Phase 10).

</domain>

<decisions>
## Implementation Decisions

### CLI output experience
- `fix-pr` streams events in real-time via WebSocket (same pattern as existing `review` command)
- Streaming is the default behavior — no `--stream` flag needed. Add `--quiet/-q` to suppress streaming
- After streaming completes, print a compact summary table: X comments fixed, Y skipped, Z failed, plus commit SHA if fixes were pushed
- `fix-pr` goes through the server API: calls `POST /api/github/prs/{n}/auto-fix`, then streams events via WebSocket. Requires server running.

### watch-pr lifecycle
- `watch-pr` goes through the server API — calls the trigger endpoint repeatedly on a timer, streams events for each cycle
- Between cycles, show a status line: "Waiting for new comments... next check in Xs"
- Continuous event stream for each active cycle (same as fix-pr)
- Auto-stops when all comments are resolved (zero unresolved comments remain after a cycle). Ctrl+C always works to stop early.
- No additional `--until` flags or `--max-cycles` for v1

### API trigger design
- `POST /api/github/prs/{number}/auto-fix` returns 202 Accepted with a workflow ID immediately (async). Caller tracks progress via WebSocket events.
- Endpoint accepts optional JSON body with aggressiveness level override. No body = use profile default.
- `GET /api/github/prs` and `GET /api/github/prs/{number}/comments` require a `?profile=name` query param (consistent with existing `GET /api/github/issues`)
- All PR routes go in the existing `amelia/server/routes/github.py` module alongside the issues endpoint. Router already mounted at `/api/github`.

### Profile & repo resolution
- CLI commands require explicit `--profile/-p` flag (required, not optional). Consistent with existing `review` command.
- CLI validates client-side that the profile has `pr_autofix` enabled (not None) before triggering. Clear error message: "PR auto-fix not enabled on profile X. Configure it in the dashboard."
- Both `fix-pr` and `watch-pr` accept `--aggressiveness/-a` flag for per-PR override (critical/standard/thorough). Omit = use profile default. Matches Phase 1 ephemeral override decision.

### Claude's Discretion
- Exact CLI command placement (top-level in main.py vs subcommands vs client/cli.py)
- Pydantic request/response models for the API endpoints
- How watch-pr's polling timer integrates with the server-side cooldown from Phase 6
- WebSocket event filtering for PR auto-fix events vs other workflow events
- Error handling and retry behavior for server unreachable during watch-pr cycles

</decisions>

<specifics>
## Specific Ideas

- `fix-pr` pattern follows the existing `review` command in `main.py`: inner async function, `AmeliaClient` for API calls, `stream_workflow_events()` for WebSocket streaming
- `watch-pr` auto-stop on zero unresolved comments is a practical default — the user's intent is "fix this PR's comments until they're done"
- The trigger endpoint returns a workflow ID from `PRAutoFixOrchestrator`, which already generates per-PR workflow IDs via `_get_workflow_id()`
- Phase 6's `head_branch` parameter (currently defaulting to empty string) must be populated by the trigger layer — fetch PR metadata to get the head branch before calling `trigger_fix_cycle()`

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `review` command (`amelia/main.py:52-119`): Pattern for CLI → server API → WebSocket streaming. `fix-pr` follows this exact pattern.
- `start_command` (`amelia/client/cli.py:94-182`): Pattern for Typer commands with `AmeliaClient`, Rich console output, error handling
- `AmeliaClient` (`amelia/client/api.py`): HTTP client for server API — needs new methods for PR endpoints
- `stream_workflow_events()` (`amelia/client/streaming.py`): WebSocket event streaming — reuse directly for fix-pr streaming
- `list_github_issues` endpoint (`amelia/server/routes/github.py:65-137`): Pattern for GitHub API routes with profile resolution, gh CLI calls, error handling
- `PRAutoFixOrchestrator.trigger_fix_cycle()` (`amelia/pipelines/pr_auto_fix/orchestrator.py:78-143`): Entry point for fix cycles with locking and cooldown
- `GitHubPRService.list_open_prs()` and `fetch_review_comments()`: Already built, return typed models

### Established Patterns
- Typer commands with `asyncio.run()` wrapping inner async functions
- `AmeliaClient` for all CLI-to-server communication
- Rich console for CLI output formatting
- FastAPI router with Depends() for dependency injection (profile repo, settings repo)
- 202 Accepted for async operations (workflow creation pattern in existing routes)

### Integration Points
- `amelia/server/routes/github.py`: Add PR endpoints (list PRs, get comments, trigger fix)
- `amelia/main.py` or `amelia/client/cli.py`: Add `fix-pr` and `watch-pr` commands
- `amelia/client/api.py`: Add client methods for new PR endpoints
- `PRAutoFixOrchestrator`: Called from the trigger endpoint with real `head_branch` values
- Event bus: PR auto-fix events already defined in Phase 6 — streaming filters on these

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-cli-api-triggers*
*Context gathered: 2026-03-14*
