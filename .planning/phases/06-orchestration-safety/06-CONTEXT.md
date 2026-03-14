# Phase 6: Orchestration & Safety - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Safely handle concurrent and repeated fix attempts without race conditions, infinite loops, or branch corruption. One auto-fix workflow per PR at a time, queued handling for new comments, and Developer always operates on the PR's head branch.

</domain>

<decisions>
## Implementation Decisions

### Queued cycle scope
- Fresh scan on every cycle — re-fetch ALL unresolved comments from the PR, don't track incremental deltas
- Phase 3's "already has Amelia reply" check naturally deduplicates, so fresh scan is safe and simple
- Key use case: third-party LLM reviewers (e.g., CodeRabbit) that take 10+ minutes to re-review after Amelia pushes fixes

### Post-push cooldown
- After pushing fixes, wait a configurable cooldown period (default 5 minutes) before starting the next cycle
- Cooldown gives third-party reviewers time to re-review the new commit before Amelia acts again
- Timer resets when new comments arrive during cooldown — prevents acting on a half-complete review
- Max cooldown cap (configurable, default 15 minutes) — prevents infinite deferral if comments keep trickling in
- Cooldown config fields on PRAutoFixConfig: `post_push_cooldown_seconds` (default 300), `max_cooldown_seconds` (default 900)

### Divergence recovery
- On branch divergence (remote moved while Amelia was fixing): discard local changes, hard reset to remote HEAD, retry fresh
- Fresh retry means: re-fetch comments, re-classify, re-fix — new code may have already addressed some comments
- Max 2 retries per trigger on divergence — if branch keeps moving, someone is actively pushing, back off and wait for next trigger
- Hard reset is safe because Amelia's unpushed changes are stale relative to the new branch state

### Concurrency control
- One auto-fix workflow per PR at a time — concurrent triggers for the same PR number are queued
- Queued triggers don't accumulate — only one pending cycle exists per PR (latest wins, since fresh scan covers everything)
- Different PRs can run fix cycles concurrently (no global lock)

### Orchestration notifications
- Queue events: dashboard event + log only — no GitHub PR comment (avoids noise, reviewers don't need to know about internal scheduling)
- Divergence: dashboard event + log on each retry; GitHub PR comment ONLY on final failure after all retries exhausted ("Could not apply fixes — PR branch changed during fix attempt. Will retry on next cycle.")
- Cooldown state: dashboard event with live countdown showing remaining time and "resets on new comments" indicator
- New event types needed: `pr_fix_queued`, `pr_fix_diverged`, `pr_fix_cooldown_started`, `pr_fix_cooldown_reset`, `pr_fix_retries_exhausted`

### Claude's Discretion
- Concurrency mechanism (asyncio.Lock dict keyed by PR number, or similar)
- Internal state management for cooldown timer (asyncio.Task, Event, etc.)
- How to integrate with existing OrchestratorService patterns
- Whether cooldown logic lives in the pipeline or in a separate orchestration layer
- Exact dashboard event data payloads

</decisions>

<specifics>
## Specific Ideas

- Primary use case for cooldown: third-party LLM code review agents that take 10+ minutes to complete a review pass after Amelia pushes. Without cooldown, Amelia would pick up stale unresolved comments from the previous review before the new review finishes.
- Cooldown timer reset on new comments is critical — it means Amelia naturally waits for the reviewer to finish their full pass before acting.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `OrchestratorService` (`amelia/server/orchestrator/service.py`): Has `_sequence_locks` (dict of asyncio.Lock keyed by workflow_id) — similar pattern needed for per-PR locking
- `asyncio.Lock` used throughout codebase (connection_manager, brainstorm service, orchestrator) — established concurrency pattern
- `GitOperations` (`amelia/trackers/`): Already has pull-before-push with divergence detection (Phase 2)
- Phase 3's skip logic: comments with Amelia reply are skipped — enables safe fresh scan without re-fixing

### Established Patterns
- `asyncio.Lock` for per-resource concurrency control (not threading.Lock)
- Event bus + loguru for observability (dashboard events for user-visible state, loguru for operational detail)
- Lifecycle services in `amelia/server/lifecycle/` for background tasks with start/stop

### Integration Points
- `PRAutoFixConfig` in `amelia/core/types.py` — new cooldown fields added here
- PR auto-fix pipeline in `amelia/pipelines/pr_auto_fix/` — orchestration wraps this pipeline
- Event bus for dashboard events — new event types registered alongside existing ones

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-orchestration-safety*
*Context gathered: 2026-03-14*
