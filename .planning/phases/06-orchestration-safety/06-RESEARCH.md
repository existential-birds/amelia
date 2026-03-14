# Phase 6: Orchestration & Safety - Research

**Researched:** 2026-03-14
**Domain:** Asyncio concurrency control, per-PR locking, cooldown timers, divergence recovery
**Confidence:** HIGH

## Summary

Phase 6 wraps the existing PR auto-fix pipeline (Phase 4-5) with concurrency control, cooldown logic, and divergence recovery. The codebase already has well-established patterns for all three concerns: `asyncio.Lock` dicts keyed by resource ID (orchestrator, brainstorm), background task lifecycle management (lifecycle services), and divergence detection in `GitOperations.safe_push`. This phase creates a new orchestration layer that sits between trigger points (Phase 7-8) and the pipeline itself.

The primary complexity is the cooldown timer with reset-on-new-comments behavior. This requires coordinating an `asyncio.Event` (or similar) between the cooldown wait and incoming comment notifications. The concurrency model is straightforward: one `asyncio.Lock` per PR number, with a single pending flag (not a queue) since fresh scan makes accumulated triggers redundant.

**Primary recommendation:** Create a `PRAutoFixOrchestrator` service class that owns per-PR locks, cooldown state, and divergence retry logic. It exposes a single `trigger_fix_cycle(pr_number, profile)` method that handles all queuing/cooldown/retry internally. New event types are added to `EventType` enum.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Fresh scan on every cycle -- re-fetch ALL unresolved comments from the PR, don't track incremental deltas
- Phase 3's "already has Amelia reply" check naturally deduplicates, so fresh scan is safe and simple
- After pushing fixes, wait a configurable cooldown period (default 5 minutes) before starting the next cycle
- Cooldown gives third-party reviewers time to re-review the new commit before Amelia acts again
- Timer resets when new comments arrive during cooldown -- prevents acting on a half-complete review
- Max cooldown cap (configurable, default 15 minutes) -- prevents infinite deferral if comments keep trickling in
- Cooldown config fields on PRAutoFixConfig: `post_push_cooldown_seconds` (default 300), `max_cooldown_seconds` (default 900)
- On branch divergence: discard local changes, hard reset to remote HEAD, retry fresh
- Max 2 retries per trigger on divergence
- One auto-fix workflow per PR at a time -- concurrent triggers queued
- Queued triggers don't accumulate -- only one pending cycle exists per PR (latest wins)
- Different PRs can run fix cycles concurrently (no global lock)
- Queue events: dashboard event + log only -- no GitHub PR comment
- Divergence: dashboard event + log on each retry; GitHub PR comment ONLY on final failure after all retries exhausted
- Cooldown state: dashboard event with live countdown showing remaining time
- New event types: `pr_fix_queued`, `pr_fix_diverged`, `pr_fix_cooldown_started`, `pr_fix_cooldown_reset`, `pr_fix_retries_exhausted`

### Claude's Discretion
- Concurrency mechanism (asyncio.Lock dict keyed by PR number, or similar)
- Internal state management for cooldown timer (asyncio.Task, Event, etc.)
- How to integrate with existing OrchestratorService patterns
- Whether cooldown logic lives in the pipeline or in a separate orchestration layer
- Exact dashboard event data payloads

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ORCH-01 | Only one auto-fix workflow runs per PR at a time | Per-PR asyncio.Lock dict pattern (matches brainstorm `_session_locks` and orchestrator `_sequence_locks`) |
| ORCH-02 | New comments arriving during an active fix are queued for the next cycle | Pending flag per PR + fresh scan means no comment tracking needed; cooldown timer with reset handles the timing |
| ORCH-03 | Developer agent operates on the PR's head branch, not main | GitOperations already has branch safety; orchestrator adds `git fetch + reset` before each cycle |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncio (stdlib) | Python 3.12+ | Locks, Events, Tasks, sleep | Already used throughout codebase for all concurrency |
| Pydantic | v2 | PRAutoFixConfig extension, event data models | Project convention for all data structures |
| Loguru | latest | Structured logging for orchestration events | Project convention (`logger.info("msg", key=value)`) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| EventBus | internal | Dashboard event emission | All state transitions (queued, cooldown, divergence, exhausted) |
| GitOperations | internal | Branch operations, divergence detection | Before each fix cycle and on divergence recovery |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| asyncio.Lock dict | asyncio.Semaphore(1) | Lock is simpler and semantically correct for mutual exclusion |
| asyncio.Event for cooldown | asyncio.sleep with cancellation | Event allows clean reset without task cancellation complexity |
| Separate orchestrator class | Extending OrchestratorService | Separate class is cleaner -- OrchestratorService is already 1500+ lines and handles workflow-level concerns, not PR-level |

**No new dependencies needed.** Everything uses stdlib asyncio and existing project internals.

## Architecture Patterns

### Recommended Structure
```
amelia/pipelines/pr_auto_fix/
    orchestrator.py      # NEW: PRAutoFixOrchestrator class
    pipeline.py          # Existing: pipeline entry point
    graph.py             # Existing: LangGraph definition
    nodes.py             # Existing: node functions
    state.py             # Existing: state models
amelia/core/types.py     # MODIFIED: add cooldown fields to PRAutoFixConfig
amelia/server/models/events.py  # MODIFIED: add new EventType values
```

### Pattern 1: Per-PR Lock with Pending Flag
**What:** Dict of `asyncio.Lock` keyed by PR number + dict of pending booleans
**When to use:** Every `trigger_fix_cycle` call

```python
class PRAutoFixOrchestrator:
    def __init__(self, event_bus: EventBus) -> None:
        self._pr_locks: dict[int, asyncio.Lock] = {}
        self._pr_pending: dict[int, bool] = {}
        self._cooldown_events: dict[int, asyncio.Event] = {}
        self._cooldown_deadline: dict[int, float] = {}  # monotonic time

    def _get_lock(self, pr_number: int) -> asyncio.Lock:
        if pr_number not in self._pr_locks:
            self._pr_locks[pr_number] = asyncio.Lock()
        return self._pr_locks[pr_number]

    async def trigger_fix_cycle(self, pr_number: int, profile: Profile) -> None:
        lock = self._get_lock(pr_number)

        if lock.locked():
            # Already running -- set pending flag (latest wins, no accumulation)
            self._pr_pending[pr_number] = True
            # If in cooldown, reset the timer
            if pr_number in self._cooldown_events:
                self._cooldown_events[pr_number].set()
            # Emit queued event
            return

        async with lock:
            await self._run_fix_cycle(pr_number, profile)

            # Check if pending cycle was requested during execution
            while self._pr_pending.pop(pr_number, False):
                await self._run_cooldown(pr_number)
                await self._run_fix_cycle(pr_number, profile)
```

### Pattern 2: Cooldown with Reset-on-New-Comments
**What:** After pushing fixes, wait before next cycle. Timer resets on new comments but has a max cap.
**When to use:** Between consecutive fix cycles for the same PR

```python
async def _run_cooldown(self, pr_number: int) -> None:
    cooldown_seconds = self._config.post_push_cooldown_seconds  # default 300
    max_cooldown = self._config.max_cooldown_seconds  # default 900

    event = asyncio.Event()
    self._cooldown_events[pr_number] = event
    absolute_deadline = asyncio.get_event_loop().time() + max_cooldown

    remaining = cooldown_seconds
    while remaining > 0:
        cap = min(remaining, absolute_deadline - asyncio.get_event_loop().time())
        if cap <= 0:
            break
        event.clear()
        try:
            await asyncio.wait_for(event.wait(), timeout=cap)
            # Event was set -- comment arrived, reset timer (but respect max cap)
            remaining = cooldown_seconds
        except TimeoutError:
            # Timer expired naturally
            break

    self._cooldown_events.pop(pr_number, None)
```

### Pattern 3: Divergence Recovery with Retry
**What:** On push failure due to divergence, hard reset to remote HEAD and retry fresh
**When to use:** Inside `_run_fix_cycle` when `safe_push` raises ValueError with "diverged"

```python
async def _run_fix_cycle(self, pr_number: int, profile: Profile) -> None:
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            git_ops = GitOperations(profile.repo_root)
            # Always start fresh: fetch and reset to remote HEAD
            await git_ops._run_git("fetch", "origin", head_branch)
            await git_ops._run_git("reset", "--hard", f"origin/{head_branch}")

            # Run the pipeline (classify -> develop -> commit -> push -> resolve)
            await self._execute_pipeline(pr_number, profile)
            return  # Success

        except ValueError as e:
            if "diverged" in str(e) and attempt < max_retries:
                # Emit divergence event, retry
                continue
            elif attempt >= max_retries:
                # Emit retries_exhausted event + GitHub PR comment
                raise
```

### Anti-Patterns to Avoid
- **Global lock for all PRs:** Different PRs must run concurrently. Only lock per PR number.
- **Accumulating queued triggers:** Since fresh scan covers everything, only one pending flag per PR is needed. A list/queue of triggers wastes memory and adds complexity.
- **Cancelling cooldown tasks:** Use `asyncio.Event.set()` to wake the cooldown coroutine rather than cancelling tasks. Task cancellation is messy with cleanup.
- **Blocking sleep in cooldown:** Must use `asyncio.wait_for(event.wait(), timeout=...)` not `asyncio.sleep()` -- sleep cannot be interrupted by new comments.
- **Putting orchestration inside pipeline nodes:** The orchestrator wraps the pipeline, not the other way around. Pipeline nodes should remain pure (classify -> develop -> commit -> resolve) without concurrency awareness.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-resource locking | Custom semaphore system | `dict[int, asyncio.Lock]` with `_get_lock()` helper | Pattern already proven in brainstorm service and orchestrator |
| Interruptible timer | `asyncio.sleep` + task cancel | `asyncio.Event` + `asyncio.wait_for` | Clean reset semantics without task cancellation edge cases |
| Divergence detection | Manual SHA comparison | `GitOperations.safe_push` (already detects) + catch ValueError | Phase 2 already built robust detection |
| Event emission | Custom pub/sub | Existing `EventBus.emit()` + `WorkflowEvent` | Established pattern for all dashboard events |

**Key insight:** The codebase already has all the concurrency primitives in use. This phase composes them into a new orchestration layer -- it does not invent new primitives.

## Common Pitfalls

### Pitfall 1: Lock dict memory leak
**What goes wrong:** Locks and pending flags accumulate for PRs that are no longer active.
**Why it happens:** PRs are closed/merged but their entries remain in the dicts.
**How to avoid:** Cleanup dict entries when a fix cycle completes and no pending cycle exists. Or accept the leak since it's tiny (one Lock + one bool per PR seen, ever) and clean up on service restart.
**Warning signs:** Dict grows unboundedly over weeks of operation.

### Pitfall 2: Cooldown event race between set() and wait()
**What goes wrong:** New comment arrives after cooldown check but before `event.wait()` starts, so the set() is missed.
**Why it happens:** `event.clear()` then `event.wait()` has a gap where `set()` can fire.
**How to avoid:** The `asyncio.Event` pattern is safe because both sides run on the same event loop (single-threaded). `event.set()` from `trigger_fix_cycle` and `event.wait()` in cooldown cannot interleave within an await boundary. But if `event.clear()` is called before `wait_for()`, and `set()` fires between them, the event stays set and `wait()` returns immediately. This is correct behavior (timer should reset).
**Warning signs:** None -- this is actually safe in asyncio's cooperative model.

### Pitfall 3: Git state corruption from concurrent git commands
**What goes wrong:** Two coroutines run git commands in the same repo directory simultaneously.
**Why it happens:** Different PR branches share the same repo_path. Even with per-PR locks, if two PRs run concurrently in the same working directory, git state corrupts.
**How to avoid:** The per-PR lock prevents concurrent operations on the SAME PR. For different PRs, each must either use a separate worktree or serialize all git operations. Since the user decision says "Different PRs can run fix cycles concurrently," the implementation MUST ensure git isolation. Options: (a) use git worktrees per PR, (b) add a repo-level lock that serializes git operations across all PRs while allowing non-git work to parallelize.
**Warning signs:** "fatal: Unable to create lock file" errors from git.

### Pitfall 4: Hard reset discards uncommitted work from other features
**What goes wrong:** `git reset --hard origin/branch` in divergence recovery discards changes from other running processes.
**How to avoid:** The per-PR lock ensures only one fix cycle runs per PR at a time, and each cycle starts with fetch+reset. Since Amelia's changes for a PR are always on the PR's head branch, and the reset targets that specific branch, this is safe. But the repo must be checked out to the correct branch before reset.
**Warning signs:** Changes disappearing from the working directory.

### Pitfall 5: Cooldown max cap bypass
**What goes wrong:** If `post_push_cooldown_seconds` > `max_cooldown_seconds`, the cooldown immediately exceeds the cap.
**Why it happens:** Config validation doesn't enforce the relationship.
**How to avoid:** Add a Pydantic `model_validator` that ensures `post_push_cooldown_seconds <= max_cooldown_seconds`.
**Warning signs:** Cooldown timer behaving unexpectedly with misconfigured values.

## Code Examples

### Adding new event types to EventType enum
```python
# In amelia/server/models/events.py, add to EventType class:

# PR Auto-Fix orchestration
PR_FIX_QUEUED = "pr_fix_queued"
PR_FIX_DIVERGED = "pr_fix_diverged"
PR_FIX_COOLDOWN_STARTED = "pr_fix_cooldown_started"
PR_FIX_COOLDOWN_RESET = "pr_fix_cooldown_reset"
PR_FIX_RETRIES_EXHAUSTED = "pr_fix_retries_exhausted"
```

### Adding cooldown fields to PRAutoFixConfig
```python
# In amelia/core/types.py, add to PRAutoFixConfig:
post_push_cooldown_seconds: int = Field(
    default=300, ge=0, le=3600,
    description="Seconds to wait after push before next cycle",
)
max_cooldown_seconds: int = Field(
    default=900, ge=0, le=7200,
    description="Maximum cooldown duration (caps resets)",
)

# Add model_validator to enforce post_push <= max_cooldown
@model_validator(mode="after")
def _validate_cooldown_bounds(self) -> Self:
    if self.post_push_cooldown_seconds > self.max_cooldown_seconds:
        raise ValueError(
            f"post_push_cooldown_seconds ({self.post_push_cooldown_seconds}) "
            f"must be <= max_cooldown_seconds ({self.max_cooldown_seconds})"
        )
    return self
```

### Emitting an event (existing pattern from orchestrator service)
```python
# Pattern from OrchestratorService._emit_event
event = WorkflowEvent(
    id=uuid4(),
    workflow_id=workflow_id,
    sequence=0,  # Orchestration events don't need sequence
    timestamp=datetime.now(UTC),
    agent="pr_auto_fix",
    event_type=EventType.PR_FIX_QUEUED,
    message=f"Fix cycle queued for PR #{pr_number}",
    data={"pr_number": pr_number},
)
self._event_bus.emit(event)
```

### Git fetch + hard reset for fresh start
```python
async def _reset_to_remote(self, git_ops: GitOperations, branch: str) -> None:
    """Fetch remote and hard reset to remote HEAD."""
    await git_ops._run_git("fetch", "origin", branch)
    await git_ops._run_git("checkout", branch)
    await git_ops._run_git("reset", "--hard", f"origin/{branch}")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Threading locks | asyncio.Lock | Project inception | All concurrency is cooperative async |
| Queue of triggers | Pending flag (latest wins) | Phase 6 design decision | Simpler, since fresh scan makes queued triggers redundant |

**Deprecated/outdated:**
- None relevant -- asyncio patterns have been stable since Python 3.10+

## Open Questions

1. **Git working directory isolation for concurrent PRs**
   - What we know: Per-PR locks prevent concurrent access to the same PR. Different PRs can run concurrently per design.
   - What's unclear: If two PRs share the same `profile.repo_root`, concurrent git operations will conflict. Do profiles use separate worktrees per PR?
   - Recommendation: For v1, serialize ALL git operations behind a repo-level lock (in addition to per-PR locks). This sacrifices git parallelism but avoids corruption. Git operations are fast (fetch, reset, commit, push) so the serialization cost is negligible compared to LLM calls. Different PRs still parallelize for the classify/develop steps -- only the git operations serialize.

2. **Workflow ID for orchestration events**
   - What we know: `WorkflowEvent` requires a `workflow_id: UUID`. The PR fix orchestrator doesn't naturally map to the existing workflow concept.
   - What's unclear: Should orchestration events use the pipeline's workflow_id, or a synthetic one?
   - Recommendation: Use the pipeline run's workflow_id for events emitted during a cycle. For events emitted outside a cycle (queued, cooldown), create a per-PR synthetic UUID that persists across cycles.

3. **Where the orchestrator gets instantiated**
   - What we know: `ServerLifecycle` manages startup/shutdown. `OrchestratorService` is created in server setup.
   - What's unclear: Whether `PRAutoFixOrchestrator` is a standalone service or nested inside `OrchestratorService`.
   - Recommendation: Standalone service, similar to `BrainstormService`. Registered in the same dependency injection point where `OrchestratorService` is created. Phase 7 (triggers) and Phase 8 (polling) will call `trigger_fix_cycle` on this service.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (auto mode) |
| Config file | `pyproject.toml` ([tool.pytest.ini_options]) |
| Quick run command | `uv run pytest tests/unit/pipelines/pr_auto_fix/ -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ORCH-01 | Only one fix cycle per PR at a time; concurrent triggers queued | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_concurrent_triggers_same_pr -x` | Wave 0 |
| ORCH-01 | Different PRs can run concurrently | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_concurrent_different_prs -x` | Wave 0 |
| ORCH-02 | New comments during active fix are captured in next cycle via pending flag | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_pending_flag_triggers_next_cycle -x` | Wave 0 |
| ORCH-02 | Cooldown timer resets on new comments | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_cooldown_resets_on_new_comment -x` | Wave 0 |
| ORCH-02 | Max cooldown cap prevents infinite deferral | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_cooldown_max_cap -x` | Wave 0 |
| ORCH-03 | Orchestrator resets to remote HEAD before each cycle | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_resets_to_remote_head -x` | Wave 0 |
| ORCH-03 | Divergence recovery retries up to 2 times then fails | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_divergence_retry_and_exhaustion -x` | Wave 0 |
| Config | post_push_cooldown_seconds <= max_cooldown_seconds validation | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_cooldown_config_validation -x` | Wave 0 |
| Events | New event types registered in EventType | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_orchestrator.py::test_event_types_exist -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/pipelines/pr_auto_fix/ -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/pipelines/pr_auto_fix/test_orchestrator.py` -- covers ORCH-01, ORCH-02, ORCH-03 and config validation
- [ ] No new framework install needed -- pytest-asyncio already configured

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `amelia/server/orchestrator/service.py` (lines 186-191, 1510-1538) -- existing lock patterns
- Codebase inspection: `amelia/server/services/brainstorm.py` (lines 341-364) -- session lock pattern
- Codebase inspection: `amelia/tools/git_utils.py` -- GitOperations with divergence detection
- Codebase inspection: `amelia/pipelines/pr_auto_fix/` -- full pipeline code
- Codebase inspection: `amelia/server/models/events.py` -- EventType enum
- Codebase inspection: `amelia/core/types.py` -- PRAutoFixConfig model
- Codebase inspection: `amelia/server/events/bus.py` -- EventBus emit pattern
- Codebase inspection: `amelia/server/lifecycle/server.py` -- lifecycle management pattern

### Secondary (MEDIUM confidence)
- Python asyncio documentation (stable since 3.10+) -- Lock, Event, wait_for semantics

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all stdlib asyncio, no new dependencies
- Architecture: HIGH - all patterns already exist in codebase, just composed differently
- Pitfalls: HIGH - identified through direct code analysis (git isolation is the main concern)

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable domain, no external dependencies)
