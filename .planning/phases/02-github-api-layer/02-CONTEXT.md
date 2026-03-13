# Phase 2: GitHub API Layer - Context

**Gathered:** 2026-03-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Fetch PR data from GitHub and perform git operations via `gh` CLI subprocess — the I/O foundation for the fix pipeline. Includes fetching PR comments, listing PRs, resolving threads, replying to comments, detecting bots, and safe git commit/push operations. No pipeline orchestration — pure I/O layer.

</domain>

<decisions>
## Implementation Decisions

### Fix explanation replies (GHAPI-04)
- Concise & factual tone — short explanation of what changed and why, no pleasantries
- No diff snippet in reply — reviewer clicks commit SHA to see changes
- Footer signature: `---\n_Amelia (automated fix)_` on every reply
- Unfixable comments: reply explaining what blocked the fix, flag for human review ("Could not auto-fix: [reason]. Flagging for human review.")

### Bot & self detection (GHAPI-05)
- Self-detection via footer signature match (`_Amelia (automated fix)_` in comment body)
- Allow all comments by default — no blanket bot filtering
- Configurable ignore list: `ignore_authors: list[str] = []` field on PRAutoFixConfig
- Exact username matching only (no glob/wildcard patterns)
- Amelia's own footer check always runs regardless of ignore list

### Git push safety (GIT-03, GIT-04)
- On remote divergence (pull-before-push finds new commits): abort and report, never rebase
- Force-push is never allowed under any circumstances
- Push failures surfaced via event bus (`pr_push_failed` event) + loguru log — pipeline marks fix as incomplete, does not crash
- Hard guard: refuse to push to main, master, or any protected branch pattern

### Async & module structure
- All `gh` CLI calls use `asyncio.create_subprocess_exec` (not sync `subprocess.run`)
- Existing `GithubTracker` remains sync and untouched — different context (issue fetching)
- New `GitHubPRService` class in a new module — handles all PR-related GitHub API operations (fetch comments, list PRs, resolve threads, reply)
- Separate async git utility class/module for stage, commit, push, pull, SHA verification — reusable across the codebase, not coupled to PR logic

### Claude's Discretion
- Exact module file paths and class naming
- Internal helper method decomposition
- GraphQL query structure for thread resolution
- Timeout and subprocess error handling details
- Whether git utility uses a protocol/ABC or concrete class

</decisions>

<specifics>
## Specific Ideas

- Reply format example: "Fixed: [what changed]. _Commit: abc123_\n---\n_Amelia (automated fix)_"
- Unfixable reply example: "Could not auto-fix: this requires a design decision about the API contract. Flagging for human review.\n---\n_Amelia (automated fix)_"
- GithubTracker uses `subprocess.run` with `capture_output=True, text=True, check=True` — new service should follow similar error handling pattern but async

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `GithubTracker` (`amelia/trackers/github.py`): Pattern for `gh` CLI subprocess calls with JSON parsing and error handling — async equivalent needed
- `WorktreeHealthChecker` (`amelia/server/lifecycle/health_checker.py`): start/stop lifecycle with async loop — pattern for background services
- `PRReviewComment`, `PRSummary` models (`amelia/core/types.py`): Already defined — this phase returns instances of them
- `PRAutoFixConfig` (`amelia/core/types.py`): Will need `ignore_authors: list[str]` field added

### Established Patterns
- `gh` CLI subprocess with JSON output parsing (`--json` flag)
- `subprocess.CalledProcessError` → `ValueError` with stderr message
- `json.JSONDecodeError` → `ValueError` with context
- Event bus for lifecycle events (`amelia/core/events.py`)
- Loguru structured logging throughout

### Integration Points
- `PRAutoFixConfig` needs new `ignore_authors` field (Phase 1 model extension)
- New GitHubPRService consumed by Phase 4 (Core Fix Pipeline)
- New git utility consumed by Phase 4 (commit/push after fixes)
- Event bus integration for push failure events

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-github-api-layer*
*Context gathered: 2026-03-13*
