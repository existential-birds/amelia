# Phase 8: Polling Service - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Background service that autonomously polls all pr_autofix-enabled profiles for new unresolved PR comments, triggering fix cycles via the orchestrator without manual intervention. No dashboard integration (Phase 9), no metrics (Phase 10).

</domain>

<decisions>
## Implementation Decisions

### Profile discovery
- Only poll profiles where `pr_autofix` config is set (not None) — pr_autofix=None means feature disabled
- Label-based PR filtering: only poll PRs with a configurable GitHub label (default `amelia`)
- New `poll_label` field on `PRAutoFixConfig` (default `"amelia"`, configurable per profile)
- PRs with zero unresolved comments are skipped silently (no log, no event)

### Rate limit strategy
- Parse `X-RateLimit-Remaining` and `X-RateLimit-Reset` headers from `gh` CLI responses
- Back off when <10% of hourly rate limit budget remains
- On backoff: sleep until the `X-RateLimit-Reset` timestamp, then resume normal polling
- Emit a `pr_poll_rate_limited` dashboard event (warning level) when backing off so users know why polling paused

### Polling intervals & concurrency
- Per-profile intervals using existing `PRAutoFixConfig.poll_interval` field (default 60s)
- Poller tracks a next-poll timestamp per profile and polls each profile on its own schedule
- Profiles polled sequentially within each tick (one at a time, naturally spreads API calls)
- No overlap: if a cycle hasn't finished, skip the next scheduled tick for that profile
- Fix cycle dispatch is fire-and-forget concurrent — poller triggers `PRAutoFixOrchestrator.trigger_fix_cycle()` for each PR with unresolved comments and doesn't wait for completion (orchestrator handles per-PR locking)

### Startup & lifecycle
- Immediate first poll on startup — catches comments that arrived while server was down
- Runtime toggle: updating `pr_polling_enabled` in server settings starts/stops the poller without server restart
- Follows `WorktreeHealthChecker` lifecycle pattern: `start()`/`stop()` methods, `asyncio.Task` for the poll loop, registered in server lifespan

### Observability
- Cycle summaries at INFO level: "Polled profile X: N PRs checked, M fix cycles triggered"
- Silent when nothing found (no log for empty cycles)
- Errors logged and swallowed — poller never crashes, continues to next profile/cycle
- Start/stop logged at INFO level

### Claude's Discretion
- Internal loop structure (single asyncio.Task with per-profile timers, or one task per profile)
- How to parse X-RateLimit headers from `gh` CLI subprocess output
- Whether rate limit state is shared across profiles or tracked independently
- Exact mechanism for runtime start/stop toggle (periodic config check, event subscription, etc.)

</decisions>

<specifics>
## Specific Ideas

- The `WorktreeHealthChecker` in `amelia/server/lifecycle/health_checker.py` is the proven template for this service: `__init__`/`start()`/`stop()`, `asyncio.Task`, exception-resilient loop
- `PRAutoFixOrchestrator.trigger_fix_cycle()` is the entry point — the poller's job is to call this with the right arguments per PR
- `GitHubPRService.list_open_prs()` and `fetch_review_comments()` already exist for fetching PR data
- Label filtering can use `gh pr list --label amelia` to reduce API calls (filter server-side rather than client-side)
- STATE.md research flag: "Phase 8 needs real-world validation of rate limit budget calculations" — the 10% threshold is the starting point

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `WorktreeHealthChecker` (`amelia/server/lifecycle/health_checker.py`): Lifecycle pattern template — start/stop, asyncio.Task, exception-resilient loop
- `PRAutoFixOrchestrator` (`amelia/pipelines/pr_auto_fix/orchestrator.py`): Entry point via `trigger_fix_cycle()` — handles locking, cooldown, divergence
- `GitHubPRService.list_open_prs()` and `fetch_review_comments()`: Already built, return typed Pydantic models
- `PRAutoFixConfig.poll_interval`: Already exists (default 60s, range 10-3600)
- `ServerSettings.pr_polling_enabled`: Already exists (default False, NOT NULL)
- `ProfileRepository`: Provides `get_all()` to fetch profiles for discovery

### Established Patterns
- `asyncio.Task` with `contextlib.suppress(asyncio.CancelledError)` for lifecycle services
- `loguru` structured logging with kwargs
- Event bus for dashboard events (`EventType` enum, `WorkflowEvent` model)
- `gh` CLI subprocess calls via `GithubTracker`/`GitHubPRService` pattern

### Integration Points
- `amelia/server/main.py` lifespan: Register poller alongside `WorktreeHealthChecker` (start/stop in lifespan)
- `PRAutoFixConfig` in `amelia/core/types.py`: Add `poll_label` field
- `EventType` enum: Add `pr_poll_rate_limited` event type
- `ServerSettings`/`ServerSettingsRepository`: Read `pr_polling_enabled` for runtime toggle

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 08-polling-service*
*Context gathered: 2026-03-14*
