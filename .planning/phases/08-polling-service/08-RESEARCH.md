# Phase 8: Polling Service - Research

**Researched:** 2026-03-14
**Domain:** asyncio background service, GitHub API rate limiting, lifecycle management
**Confidence:** HIGH

## Summary

The polling service is a background asyncio task that discovers all pr_autofix-enabled profiles, lists their labeled PRs, checks for unresolved comments, and dispatches fix cycles via the existing `PRAutoFixOrchestrator`. The implementation follows the proven `WorktreeHealthChecker` lifecycle pattern already in the codebase: `__init__`/`start()`/`stop()` with an `asyncio.Task` and `contextlib.suppress(asyncio.CancelledError)`.

Rate limit awareness is the primary new concern beyond the health checker pattern. The `gh api /rate_limit` endpoint returns a clean JSON payload with `resources.core.remaining` and `resources.core.reset` fields, which is far more reliable than parsing `--include` headers from every call. The poller should check rate limit state periodically (e.g., before each profile poll cycle) and sleep until the reset timestamp when remaining budget drops below 10%.

All building blocks exist: `ProfileRepository.list_profiles()`, `GitHubPRService.list_open_prs()` and `fetch_review_comments()`, `PRAutoFixOrchestrator.trigger_fix_cycle()`, `SettingsRepository.get_server_settings()` for the `pr_polling_enabled` toggle, and the `EventBus` for dashboard events.

**Primary recommendation:** Build a single `PRCommentPoller` class in `amelia/server/lifecycle/pr_poller.py` following the `WorktreeHealthChecker` pattern, with rate limit checking via `gh api /rate_limit` JSON endpoint, per-profile next-poll tracking, and fire-and-forget fix cycle dispatch.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Only poll profiles where `pr_autofix` config is set (not None) -- pr_autofix=None means feature disabled
- Label-based PR filtering: only poll PRs with a configurable GitHub label (default `amelia`)
- New `poll_label` field on `PRAutoFixConfig` (default `"amelia"`, configurable per profile)
- PRs with zero unresolved comments are skipped silently (no log, no event)
- Parse `X-RateLimit-Remaining` and `X-RateLimit-Reset` headers from `gh` CLI responses
- Back off when <10% of hourly rate limit budget remains
- On backoff: sleep until the `X-RateLimit-Reset` timestamp, then resume normal polling
- Emit a `pr_poll_rate_limited` dashboard event (warning level) when backing off
- Per-profile intervals using existing `PRAutoFixConfig.poll_interval` field (default 60s)
- Poller tracks a next-poll timestamp per profile and polls each profile on its own schedule
- Profiles polled sequentially within each tick (one at a time)
- No overlap: if a cycle hasn't finished, skip the next scheduled tick for that profile
- Fix cycle dispatch is fire-and-forget concurrent -- triggers `PRAutoFixOrchestrator.trigger_fix_cycle()` without waiting
- Immediate first poll on startup
- Runtime toggle: updating `pr_polling_enabled` starts/stops the poller without server restart
- Follows `WorktreeHealthChecker` lifecycle pattern
- Cycle summaries at INFO level: "Polled profile X: N PRs checked, M fix cycles triggered"
- Silent when nothing found
- Errors logged and swallowed -- poller never crashes

### Claude's Discretion
- Internal loop structure (single asyncio.Task with per-profile timers, or one task per profile)
- How to parse X-RateLimit headers from `gh` CLI subprocess output
- Whether rate limit state is shared across profiles or tracked independently
- Exact mechanism for runtime start/stop toggle (periodic config check, event subscription, etc.)

### Deferred Ideas (OUT OF SCOPE)
None
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| POLL-01 | Background service polls all GitHub-type profiles for new unresolved PR comments | Profile discovery via `ProfileRepository.list_profiles()` filtering on `pr_autofix is not None`, label filtering via `gh pr list --label`, comment fetching via `GitHubPRService.fetch_review_comments()` |
| POLL-02 | Polling interval is configurable (default 60 seconds) | `PRAutoFixConfig.poll_interval` field already exists (default 60, range 10-3600). Per-profile next-poll timestamp tracking. |
| POLL-03 | Poller uses start/stop lifecycle pattern (registered in server lifespan) | `WorktreeHealthChecker` pattern: `start()`/`stop()`, `asyncio.Task`, registered in `lifespan()` in `main.py` |
| POLL-04 | Poller is resilient to exceptions (logs and continues, does not crash) | `try/except Exception` in loop body with loguru error logging, identical to `WorktreeHealthChecker._check_loop()` |
| POLL-05 | Poller respects GitHub API rate limits with backoff | `gh api /rate_limit` JSON endpoint for clean rate limit checking, sleep until reset timestamp when <10% remaining |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncio | stdlib | Task lifecycle, sleep, event loop | Already used for WorktreeHealthChecker, orchestrator |
| contextlib | stdlib | `suppress(CancelledError)` in stop() | Established pattern in health_checker.py |
| loguru | existing | Structured logging with kwargs | Project convention per CLAUDE.md |
| pydantic | existing | `PRAutoFixConfig` model extension | All data structures are Pydantic models |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| gh CLI | system | GitHub API calls (rate limit, PR list) | All GitHub operations use `gh` subprocess |
| json | stdlib | Parse `gh api /rate_limit` JSON response | Rate limit budget checking |
| time | stdlib | `time.time()` for next-poll timestamps | Per-profile schedule tracking |
| asyncio.create_task | stdlib | Fire-and-forget fix cycle dispatch | Non-blocking trigger_fix_cycle calls |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `gh api /rate_limit` endpoint | `gh api --include` header parsing | `/rate_limit` returns clean JSON; `--include` mixes headers with body requiring fragile string parsing. Use `/rate_limit` for dedicated checks. |
| Single asyncio.Task | One task per profile | Single task is simpler, easier to stop, matches health checker pattern. Multiple tasks add complexity for marginal benefit since profiles are polled sequentially anyway. |
| Periodic config polling for toggle | Event subscription | Config polling is simpler, requires no new event infrastructure. Check `pr_polling_enabled` every loop iteration from the settings repo. |

## Architecture Patterns

### Recommended Project Structure
```
amelia/server/lifecycle/
    pr_poller.py          # PRCommentPoller class (new)
    health_checker.py     # Existing template to follow
amelia/core/types.py      # Add poll_label to PRAutoFixConfig
amelia/server/models/events.py  # Add pr_poll_rate_limited EventType
amelia/server/main.py     # Register poller in lifespan
tests/unit/server/lifecycle/
    test_pr_poller.py     # Unit tests (new)
```

### Pattern 1: Lifecycle Service (from WorktreeHealthChecker)
**What:** Background service with `start()`/`stop()` methods wrapping an `asyncio.Task`
**When to use:** Any long-running background loop that should start/stop with the server
**Example:**
```python
# Source: amelia/server/lifecycle/health_checker.py (existing code)
class PRCommentPoller:
    def __init__(self, ...) -> None:
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("PRCommentPoller started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            logger.info("PRCommentPoller stopped")
```

### Pattern 2: Per-Profile Schedule Tracking
**What:** Track next-poll timestamp per profile name, skip profiles whose time hasn't arrived
**When to use:** Multiple entities with independent polling intervals
**Example:**
```python
import time

class PRCommentPoller:
    def __init__(self, ...) -> None:
        self._next_poll: dict[str, float] = {}  # profile_name -> timestamp

    async def _poll_loop(self) -> None:
        # Immediate first poll: don't set any next_poll times initially
        while True:
            try:
                await self._poll_all_profiles()
            except Exception as e:
                logger.error("Poll cycle failed - continuing", error=str(e))
            await asyncio.sleep(5)  # Tick interval (check schedule frequently)

    async def _poll_all_profiles(self) -> None:
        now = time.monotonic()
        profiles = await self._profile_repo.list_profiles()
        for profile in profiles:
            if profile.pr_autofix is None:
                continue
            if now < self._next_poll.get(profile.name, 0):
                continue  # Not time yet
            await self._poll_profile(profile)
            self._next_poll[profile.name] = now + profile.pr_autofix.poll_interval
```

### Pattern 3: Fire-and-Forget Fix Cycle Dispatch
**What:** Create asyncio tasks for fix cycles without awaiting them
**When to use:** Poller should not block on fix cycle execution
**Example:**
```python
async def _poll_profile(self, profile: Profile) -> None:
    config = profile.pr_autofix
    service = GitHubPRService(profile.repo_root)
    prs = await self._list_labeled_prs(service, config.poll_label)

    triggered = 0
    for pr in prs:
        comments = await service.fetch_review_comments(
            pr.number, ignore_authors=config.ignore_authors
        )
        if not comments:
            continue  # Silent skip per decision
        # Fire-and-forget: orchestrator handles locking
        asyncio.create_task(
            self._orchestrator.trigger_fix_cycle(
                pr_number=pr.number,
                repo=self._get_repo(profile),
                profile=profile,
                head_branch=pr.head_branch,
                config=config,
            )
        )
        triggered += 1

    if triggered > 0 or len(prs) > 0:
        logger.info(
            "Polled profile",
            profile=profile.name,
            prs_checked=len(prs),
            fix_cycles_triggered=triggered,
        )
```

### Pattern 4: Rate Limit Check via /rate_limit Endpoint
**What:** Call `gh api /rate_limit` to get clean JSON rate limit data
**When to use:** Before each polling cycle to decide whether to proceed or back off
**Example:**
```python
import json

async def _check_rate_limit(self, repo_root: str) -> tuple[int, int, int]:
    """Check GitHub rate limit. Returns (remaining, limit, reset_timestamp)."""
    proc = await asyncio.create_subprocess_exec(
        "gh", "api", "/rate_limit",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=repo_root,
    )
    stdout, _ = await proc.communicate()
    data = json.loads(stdout.decode())
    core = data["resources"]["core"]
    return core["remaining"], core["limit"], core["reset"]

async def _should_back_off(self, repo_root: str) -> float | None:
    """Returns sleep duration if rate limited, None if OK."""
    remaining, limit, reset_ts = await self._check_rate_limit(repo_root)
    threshold = int(limit * 0.10)  # 10% of budget
    if remaining <= threshold:
        sleep_duration = max(0, reset_ts - time.time())
        return sleep_duration
    return None
```

### Pattern 5: Runtime Toggle via Settings Check
**What:** Check `pr_polling_enabled` setting each loop iteration
**When to use:** Simple runtime on/off without restart
**Example:**
```python
async def _poll_loop(self) -> None:
    while True:
        try:
            settings = await self._settings_repo.get_server_settings()
            if settings.pr_polling_enabled:
                await self._poll_all_profiles()
            # else: silently skip (poller stays alive but idle)
        except Exception as e:
            logger.error("Poll cycle failed - continuing", error=str(e))
        await asyncio.sleep(5)
```

### Anti-Patterns to Avoid
- **One task per profile:** Increases complexity for stop/cleanup, risk of leaked tasks when profiles are added/removed. Use single task with per-profile schedule instead.
- **Awaiting trigger_fix_cycle:** Blocks the poller for the entire fix cycle duration (classify -> develop -> commit -> push -> resolve). Use fire-and-forget `asyncio.create_task`.
- **Parsing `--include` headers from every gh call:** Fragile string parsing, mixes concerns. Use dedicated `/rate_limit` endpoint.
- **`time.time()` for schedule tracking:** Use `time.monotonic()` to avoid clock drift issues from NTP adjustments.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Lifecycle management | Custom signal handlers, atexit hooks | `start()`/`stop()` with `asyncio.Task` + lifespan registration | Proven pattern in WorktreeHealthChecker, clean cancellation |
| PR listing with label filter | Custom GitHub REST API calls | `gh pr list --label X --json ...` | gh CLI handles auth, pagination, and returns clean JSON |
| Rate limit data | Parse HTTP headers from subprocess stderr | `gh api /rate_limit` JSON endpoint | Returns structured JSON with all rate limit categories |
| Per-PR concurrency control | Locks in the poller | `PRAutoFixOrchestrator.trigger_fix_cycle()` | Orchestrator already handles per-PR locking, pending flags, cooldown |
| Comment filtering (resolved, self-authored) | Custom filtering logic | `GitHubPRService.fetch_review_comments()` | Already filters resolved threads and bot comments |

**Key insight:** The poller is thin coordination glue -- it discovers profiles, checks PRs, and dispatches to the orchestrator. All complex logic (classification, fixing, pushing, locking, cooldown) already exists in downstream components.

## Common Pitfalls

### Pitfall 1: Rate Limit Exhaustion Across All gh Users
**What goes wrong:** Polling burns through the 5,000 requests/hour limit, breaking all `gh` CLI usage (not just PR auto-fix).
**Why it happens:** Multiple profiles with aggressive intervals. Each poll cycle: 1 rate_limit check + 1 pr list + N*(2-3 comment fetch calls).
**How to avoid:** Check `/rate_limit` before each profile cycle. Back off at <10% remaining. Share rate limit state across profiles (they share the same GitHub token).
**Warning signs:** `remaining` dropping faster than expected. Log remaining budget at DEBUG level.

### Pitfall 2: Fire-and-Forget Task Exceptions Silently Lost
**What goes wrong:** `asyncio.create_task` for fix cycles means exceptions are only logged when the task is garbage collected, often with confusing "Task exception was never retrieved" warnings.
**Why it happens:** Nobody awaits the task.
**How to avoid:** Store task references in a set, add a done callback that logs exceptions:
```python
self._active_tasks: set[asyncio.Task[None]] = set()

task = asyncio.create_task(self._orchestrator.trigger_fix_cycle(...))
self._active_tasks.add(task)
task.add_done_callback(self._active_tasks.discard)
```
The orchestrator already catches all exceptions internally, but the defensive pattern prevents warnings.

### Pitfall 3: Stale Profile Data
**What goes wrong:** Profile or config changes (new label, disabled pr_autofix) aren't picked up until the next full cycle.
**Why it happens:** Caching profiles or reading them once at startup.
**How to avoid:** Fetch fresh profile list from `ProfileRepository.list_profiles()` every tick. The DB query is cheap (single table, few rows).

### Pitfall 4: gh CLI Not Available in All Profile repo_roots
**What goes wrong:** `GitHubPRService(repo_root)` assumes `gh` is authenticated and the directory is a valid repo. Profiles with misconfigured `repo_root` cause subprocess failures.
**Why it happens:** Profile config may point to non-existent or non-repo directories.
**How to avoid:** Wrap per-profile polling in try/except, log the error with profile name, continue to next profile. Never let one bad profile kill polling for all profiles.

### Pitfall 5: `list_open_prs` Doesn't Support Label Filtering
**What goes wrong:** The existing `GitHubPRService.list_open_prs()` method does NOT pass `--label` flag. It fetches all open PRs.
**Why it happens:** It was built for Phase 7 general PR listing, not polling.
**How to avoid:** Add a new method `list_labeled_prs(label: str)` or add an optional `label` parameter to `list_open_prs`. Alternatively, call `gh pr list --label X` directly in the poller via a helper method.

## Code Examples

### Adding poll_label to PRAutoFixConfig
```python
# Source: amelia/core/types.py (modification)
class PRAutoFixConfig(BaseModel):
    # ... existing fields ...
    poll_label: str = Field(
        default="amelia",
        description="GitHub label to filter PRs for polling",
    )
```

### Adding pr_poll_rate_limited EventType
```python
# Source: amelia/server/models/events.py (modification)
class EventType(StrEnum):
    # ... existing entries ...
    PR_POLL_RATE_LIMITED = "pr_poll_rate_limited"
```
Also add to the appropriate severity/category sets (`_WARNING_EVENTS`, `_INFO_EVENTS`).

### Label-Filtered PR List
```python
# New method on GitHubPRService or helper in poller
async def list_labeled_prs(self, label: str) -> list[PRSummary]:
    """List open PRs filtered by label."""
    raw = await self._run_gh(
        "pr", "list",
        "--json", "number,title,headRefName,author,updatedAt",
        "--state", "open",
        "--label", label,
        "--limit", "100",
    )
    pr_data: list[dict[str, Any]] = json.loads(raw)
    return [
        PRSummary(
            number=pr["number"],
            title=pr["title"],
            head_branch=pr["headRefName"],
            author=pr["author"]["login"],
            updated_at=pr["updatedAt"],
        )
        for pr in pr_data
    ]
```

### Lifespan Registration
```python
# Source: amelia/server/main.py (modification to lifespan function)
from amelia.server.lifecycle.pr_poller import PRCommentPoller

# After health_checker creation:
pr_poller = PRCommentPoller(
    profile_repo=profile_repo,
    settings_repo=settings_repo,
    orchestrator=orchestrator,  # PRAutoFixOrchestrator, not OrchestratorService
    event_bus=event_bus,
)

# Start (after health_checker.start()):
await pr_poller.start()

# Stop (before health_checker.stop() in shutdown):
await pr_poller.stop()
```

Note: The poller needs `PRAutoFixOrchestrator` which is NOT currently created in `main.py`. It needs to be instantiated in the lifespan with `event_bus` and a `GitHubPRService`. However, `GitHubPRService` requires a `repo_root` per profile -- so the poller should create `GitHubPRService` instances per-profile during polling, not at startup.

### Extracting repo from Profile
```python
# The orchestrator.trigger_fix_cycle() needs a repo string (owner/repo format).
# This isn't directly on Profile. Need to derive it from repo_root or
# have the poller fetch it via gh CLI.
async def _get_repo_slug(self, repo_root: str) -> str:
    """Get owner/repo slug from local repo using gh CLI."""
    proc = await asyncio.create_subprocess_exec(
        "gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=repo_root,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode().strip()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `time.time()` for scheduling | `time.monotonic()` | Python best practice | Immune to NTP clock adjustments |
| Parse `--include` headers | `gh api /rate_limit` JSON | Always available | Clean structured data, no string parsing |
| One poll task per profile | Single task, per-profile schedule | Architecture decision | Simpler lifecycle, easier to stop/debug |

**Verified:** `gh api /rate_limit` returns clean JSON with `resources.core.remaining`, `resources.core.limit`, `resources.core.reset` (unix timestamp). Tested live 2026-03-14 -- `remaining: 4936, limit: 5000`.

## Open Questions

1. **PRAutoFixOrchestrator instantiation in lifespan**
   - What we know: The orchestrator needs `EventBus` and `GitHubPRService`. EventBus is already created in lifespan.
   - What's unclear: `GitHubPRService` requires a `repo_root` specific to each profile. The orchestrator is currently instantiated per-call in CLI commands.
   - Recommendation: Create a single `PRAutoFixOrchestrator` in lifespan with just `event_bus` and `github_pr_service=None` (or make service optional), then have the poller pass profile-specific services when calling `trigger_fix_cycle`. OR have the poller create orchestrator instances per-profile. Simplest: create one shared orchestrator in lifespan, and have it accept `GitHubPRService` or `repo` as parameters per call (already does via `profile` param).

2. **Repo slug derivation**
   - What we know: `trigger_fix_cycle` needs `repo` in `owner/repo` format. Profile has `repo_root` (local path) but not `repo` slug.
   - What's unclear: Whether to call `gh repo view` each time or cache the slug per profile.
   - Recommendation: Fetch once per profile per poll cycle and cache in a dict. The slug won't change during a session.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (auto mode) |
| Config file | pyproject.toml (existing) |
| Quick run command | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| POLL-01 | Polls all pr_autofix-enabled profiles, fetches labeled PRs, triggers fix cycles for PRs with unresolved comments | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_polls_enabled_profiles -x` | No -- Wave 0 |
| POLL-01 | Skips profiles where pr_autofix is None | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_skips_disabled_profiles -x` | No -- Wave 0 |
| POLL-01 | Skips PRs with zero unresolved comments silently | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_skips_prs_no_comments -x` | No -- Wave 0 |
| POLL-02 | Respects per-profile poll_interval via next-poll timestamps | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_per_profile_interval -x` | No -- Wave 0 |
| POLL-03 | start()/stop() lifecycle creates and cancels asyncio task | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_start_stop_lifecycle -x` | No -- Wave 0 |
| POLL-04 | Exceptions logged and swallowed, polling continues | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_exception_resilience -x` | No -- Wave 0 |
| POLL-05 | Backs off when rate limit <10%, sleeps until reset | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_rate_limit_backoff -x` | No -- Wave 0 |
| POLL-05 | Emits pr_poll_rate_limited event on backoff | unit | `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py::test_rate_limit_event -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/server/lifecycle/test_pr_poller.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/server/lifecycle/test_pr_poller.py` -- covers POLL-01 through POLL-05
- [ ] Mock fixtures for `ProfileRepository`, `SettingsRepository`, `PRAutoFixOrchestrator`, and `gh` subprocess calls

*(No framework gaps -- pytest + pytest-asyncio already installed and configured)*

## Sources

### Primary (HIGH confidence)
- `amelia/server/lifecycle/health_checker.py` -- lifecycle pattern template (read directly)
- `amelia/pipelines/pr_auto_fix/orchestrator.py` -- trigger_fix_cycle API (read directly)
- `amelia/services/github_pr.py` -- list_open_prs, fetch_review_comments API (read directly)
- `amelia/core/types.py` -- PRAutoFixConfig, Profile models (read directly)
- `amelia/server/database/settings_repository.py` -- ServerSettings, pr_polling_enabled (read directly)
- `amelia/server/main.py` -- lifespan registration pattern (read directly)
- `gh api /rate_limit` -- live test confirmed JSON structure with resources.core.{remaining,limit,reset} (2026-03-14)
- `gh pr list --label` -- confirmed via `gh pr list --help` (2026-03-14)

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` -- rate limit exhaustion patterns and prevention strategies
- `.planning/research/STACK.md` -- rate limit strategy documentation

### Tertiary (LOW confidence)
- Rate limit 10% threshold -- user decision, needs real-world validation per STATE.md research flag

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all components are existing codebase patterns, no new dependencies
- Architecture: HIGH -- direct extension of WorktreeHealthChecker, all integration points verified in source
- Pitfalls: HIGH -- rate limit behavior verified live, fire-and-forget patterns well-understood in asyncio
- Rate limit threshold: LOW -- 10% is a starting point per STATE.md; may need tuning with real-world usage

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable -- no external dependencies, all patterns internal)
