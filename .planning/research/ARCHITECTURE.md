# Architecture Patterns: PR Auto-Fix

**Domain:** Autonomous PR review comment resolution
**Researched:** 2026-03-13

## Recommended Architecture

The PR auto-fix system adds five new components to Amelia's existing architecture. The design follows Amelia's established patterns: a lifecycle service for polling, a LangGraph pipeline for the fix workflow, Pydantic models for all data, `gh` CLI for GitHub operations, and the event bus for observability.

### High-Level Data Flow

```
GitHub PR (review comments)
        |
        v
[PR Comment Poller]  <-- lifecycle service, like WorktreeHealthChecker
        |
        | fetches unresolved comments via `gh` CLI
        v
[Comment Classifier]  <-- LLM node, filters by aggressiveness level
        |
        | actionable comments only
        v
[PR Fix Lock Manager]  <-- ensures one fix workflow per PR
        |
        v
[PR_AUTO_FIX Pipeline]  <-- LangGraph state machine
        |  classify -> develop -> commit/push -> resolve threads
        v
[GitHub Thread Resolver]  <-- GraphQL via `gh api graphql`
        |
        v
Event Bus --> Dashboard (real-time updates)
```

### Component Boundaries

| Component | Responsibility | Communicates With | New/Existing |
|-----------|---------------|-------------------|--------------|
| **PRCommentPoller** | Background polling for unresolved review comments on watched PRs | GitHub (via `gh` CLI), PRFixOrchestrator | New lifecycle service |
| **PRCommentFetcher** | Fetch and parse PR review comments, detect bot comments, deduplicate | GitHub (via `gh` CLI) | New service (stateless) |
| **CommentClassifier** | LLM-based classification of comments by aggressiveness level | LLM driver | New LangGraph node |
| **PRFixOrchestrator** | Concurrency control (one fix per PR), queue management, delegates to pipeline | PR_AUTO_FIX pipeline, Event Bus | New coordination layer |
| **PR_AUTO_FIX Pipeline** | LangGraph state machine: classify -> fix -> commit -> push -> resolve | Developer agent, CommentClassifier, GitOps, ThreadResolver | New pipeline |
| **GitOps** | Git commit and push operations on PR branch | Git CLI | New service (thin) |
| **ThreadResolver** | Resolve GitHub review threads, post reply comments | GitHub GraphQL (via `gh api graphql`) | New service |
| **OrchestratorService** | Existing workflow orchestration | All pipelines | Existing (extended) |
| **EventBus** | Broadcast PR auto-fix lifecycle events | Dashboard via WebSocket | Existing (new event types) |
| **Pipeline Registry** | Register PR_AUTO_FIX pipeline | OrchestratorService | Existing (new entry) |
| **Profile** | Store aggressiveness config per-profile | PRCommentPoller, CommentClassifier | Existing (extended) |

## Component Detail

### 1. PRCommentPoller (Lifecycle Service)

Follows the `WorktreeHealthChecker` pattern exactly: `start()` / `stop()` lifecycle, `asyncio.Task` with a loop, exception resilience, configurable interval.

```python
class PRCommentPoller:
    """Polls GitHub for new unresolved review comments on watched PRs."""

    def __init__(
        self,
        pr_fix_orchestrator: PRFixOrchestrator,
        comment_fetcher: PRCommentFetcher,
        poll_interval: float = 120.0,  # 2 minutes default
    ) -> None: ...

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def watch_pr(self, profile: str, pr_number: int) -> None: ...
    async def unwatch_pr(self, profile: str, pr_number: int) -> None: ...
```

**Key decisions:**
- Polling over webhooks (per PROJECT.md) -- no public endpoint needed, works behind firewalls.
- Polls all watched PRs in a single loop iteration. Each PR is a separate fetch call.
- Tracks `processed_comment_ids: set[str]` to avoid re-processing. This set is per-PR and cleared when the PR is unwatched.
- Respects GitHub rate limits by checking `X-RateLimit-Remaining` from `gh` stderr/headers and backing off with exponential delay.

### 2. PRCommentFetcher (Stateless Service)

Wraps `gh` CLI calls for fetching PR review comments. Follows the `GithubTracker` subprocess pattern but uses `asyncio.create_subprocess_exec` (like the existing GitHub routes do) instead of sync `subprocess.run`.

```python
class PRCommentFetcher:
    """Fetches and parses PR review comments via gh CLI."""

    async def fetch_review_comments(
        self, pr_number: int, *, cwd: str
    ) -> list[ReviewComment]: ...

    async def fetch_pr_info(
        self, pr_number: int, *, cwd: str
    ) -> PRInfo: ...
```

**Data models:**

```python
class ReviewComment(BaseModel):
    """A single review comment from a GitHub PR."""
    id: str
    thread_id: str
    author: str
    body: str
    path: str | None  # file path if inline comment
    line: int | None  # line number if inline comment
    is_resolved: bool
    created_at: datetime
    in_reply_to_id: str | None  # for threaded discussions

class PRInfo(BaseModel):
    """Metadata about a pull request."""
    number: int
    title: str
    head_branch: str
    head_sha: str
    base_branch: str
    state: str  # open, closed, merged
```

**Bot detection:** Filter comments where `author` matches a configurable bot list (default: `["amelia", "amelia[bot]"]`). This prevents infinite loops where Amelia replies to its own comments.

### 3. CommentClassifier (LangGraph Node)

An LLM call that classifies each review comment against the configured aggressiveness level.

```python
class ClassifiedComment(BaseModel):
    """A review comment with classification metadata."""
    comment: ReviewComment
    category: CommentCategory  # bug, security, style, suggestion, nit, discussion, praise
    is_actionable: bool  # True if it should be fixed at current aggressiveness
    fix_description: str  # What the LLM thinks needs to change
    confidence: float  # 0-1, how confident the classifier is

class CommentCategory(StrEnum):
    BUG = "bug"
    SECURITY = "security"
    STYLE = "style"
    CHANGE_REQUEST = "change_request"
    SUGGESTION = "suggestion"
    NIT = "nit"
    DISCUSSION = "discussion"  # not actionable at any level
    PRAISE = "praise"  # not actionable at any level
```

**Aggressiveness mapping:**

| Level | Fixes |
|-------|-------|
| CRITICAL_ONLY | bug, security |
| STANDARD | bug, security, style, change_request |
| THOROUGH | bug, security, style, change_request, suggestion, nit |
| EXEMPLARY | everything except discussion, praise |

This is a single LLM call with structured output (Pydantic model parsing), not a multi-step chain. Batch all comments in one call to reduce latency.

### 4. PRFixOrchestrator (Concurrency Controller)

The critical coordination layer. Ensures exactly one fix workflow runs per PR at any time. If a fix is requested while one is in progress, it queues.

```python
class PRFixOrchestrator:
    """Coordinates PR fix workflows with per-PR concurrency control."""

    def __init__(
        self,
        orchestrator: OrchestratorService,
        event_bus: EventBus,
    ) -> None:
        self._active_fixes: dict[str, uuid.UUID] = {}  # "profile:pr_number" -> workflow_id
        self._queued: dict[str, list[ClassifiedComment]] = {}  # pending comments
        self._lock = asyncio.Lock()  # protects _active_fixes and _queued

    async def request_fix(
        self,
        profile: str,
        pr_number: int,
        comments: list[ClassifiedComment],
    ) -> uuid.UUID | None: ...
```

**Concurrency strategy:** Use `asyncio.Lock` (not threading lock -- Amelia is single-event-loop async). The lock protects the `_active_fixes` dict during check-and-set. This mirrors how `OrchestratorService` uses `WorkflowConflictError` for worktree-level concurrency.

**Queue behavior:** When a fix is already running for a PR:
1. New comments are added to `_queued[pr_key]`.
2. When the active fix completes, check the queue. If non-empty, start a new fix with the queued comments.
3. This handles the case where a reviewer adds more comments while Amelia is fixing earlier ones.

**Max iterations:** Track fix iteration count per PR per polling session. Default cap: 3 iterations. After that, stop and log a warning. This prevents infinite loops where the reviewer keeps commenting on Amelia's fixes.

### 5. PR_AUTO_FIX Pipeline (LangGraph State Machine)

A new pipeline registered in the pipeline registry alongside `implementation` and `review`.

```
Entry: classify_comments
  |
  v
classify_comments --> [no actionable] --> post_summary --> END
  |
  [has actionable]
  v
develop_fixes --> commit_and_push --> resolve_threads --> END
```

**State:**

```python
class PRAutoFixState(BasePipelineState):
    """State for PR auto-fix pipeline."""
    pipeline_type: Literal["pr_auto_fix"] = "pr_auto_fix"

    # Input
    pr_number: int
    pr_info: PRInfo
    raw_comments: list[ReviewComment]
    aggressiveness: AggressivenessLevel

    # Classification output
    classified_comments: list[ClassifiedComment] = Field(default_factory=list)
    actionable_comments: list[ClassifiedComment] = Field(default_factory=list)

    # Fix output
    fix_results: Annotated[list[FixResult], operator.add] = Field(default_factory=list)

    # Git output
    commit_sha: str | None = None
    push_success: bool = False

    # Resolution output
    resolved_thread_ids: list[str] = Field(default_factory=list)
    reply_comment_ids: list[str] = Field(default_factory=list)
```

**Nodes:**

1. **classify_comments** -- Calls CommentClassifier. Filters to actionable. If none actionable, routes to post_summary.
2. **develop_fixes** -- Invokes the existing Developer agent (same `call_developer_node` used by review pipeline). Passes actionable comments as the "task" with file paths and line numbers as context.
3. **commit_and_push** -- GitOps: `git add`, `git commit` (with message referencing comment IDs), `git push` to PR branch.
4. **resolve_threads** -- For each fixed comment: post a reply explaining the fix, then resolve the thread via GraphQL.
5. **post_summary** -- Posts a summary comment on the PR (optional, for non-actionable comments or when all are discussion/praise).

### 6. GitOps (Thin Service)

```python
class GitOps:
    """Git commit and push operations."""

    async def commit_and_push(
        self,
        *,
        cwd: str,
        message: str,
        branch: str,
    ) -> CommitResult: ...
```

Uses `asyncio.create_subprocess_exec` for `git add -A`, `git commit`, `git push`. Returns the new commit SHA. Operates on the PR's head branch.

**Branch context:** The Developer agent must operate on the PR's head branch, not main. The orchestrator checks out the correct branch before starting the pipeline. This aligns with how existing workflows use worktrees -- each workflow gets its own worktree on the correct branch.

### 7. ThreadResolver (GitHub GraphQL)

```python
class ThreadResolver:
    """Resolves GitHub PR review threads via GraphQL."""

    async def resolve_thread(self, thread_id: str, *, cwd: str) -> bool: ...
    async def reply_to_comment(
        self, pr_number: int, comment_id: str, body: str, *, cwd: str
    ) -> str: ...
```

Thread resolution requires GraphQL because the REST API does not support it. Uses `gh api graphql` subprocess:

```bash
gh api graphql -f query='mutation { resolveReviewThread(input: {threadId: "..."}) { thread { isResolved } } }'
```

Reply uses REST via `gh`:

```bash
gh api repos/{owner}/{repo}/pulls/{pr_number}/comments/{comment_id}/replies -f body="..."
```

## Patterns to Follow

### Pattern 1: Lifecycle Service (from WorktreeHealthChecker)

All background services follow the same pattern: `__init__` with config, `start()` creates `asyncio.Task`, `stop()` cancels it, loop catches exceptions and continues. The `PRCommentPoller` follows this exactly.

### Pattern 2: Pipeline Protocol (from base.py)

New pipeline implements the `Pipeline` protocol: `metadata` property, `create_graph()`, `get_initial_state()`, `get_state_class()`. Registered in `PIPELINES` dict in `registry.py`.

### Pattern 3: gh CLI Subprocess (from GithubTracker and routes/github.py)

All GitHub operations use `gh` CLI subprocess. Routes use `asyncio.create_subprocess_exec` (async). The fetcher and resolver follow this pattern.

### Pattern 4: Event Bus Broadcasting (from EventBus)

New event types added to `EventType` enum. All PR auto-fix lifecycle transitions emit events. Dashboard subscribes via WebSocket.

### Pattern 5: Pydantic Models for All Data (from core/types.py)

`ReviewComment`, `PRInfo`, `ClassifiedComment`, `PRAutoFixState`, `CommitResult` -- all Pydantic with `frozen=True` where appropriate.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Shared Mutable State Between Poller and Pipeline
**What:** Letting the poller directly mutate pipeline state or bypass the orchestrator.
**Why bad:** Race conditions, lost updates, untestable coupling.
**Instead:** Poller calls `PRFixOrchestrator.request_fix()` which creates a proper workflow through `OrchestratorService`. Clean ownership boundary.

### Anti-Pattern 2: Resolving Threads Before Push Succeeds
**What:** Marking review threads as resolved before confirming the fix commit is pushed.
**Why bad:** Resolved threads with no actual fix. Reviewer sees "resolved" but code unchanged.
**Instead:** Pipeline is sequential: develop -> commit -> push -> verify push -> resolve. If push fails, do not resolve.

### Anti-Pattern 3: Polling Inside the Pipeline
**What:** Putting the polling loop inside the LangGraph state machine.
**Why bad:** LangGraph pipelines should be single-invocation workflows. Polling is infrastructure concern, not workflow logic.
**Instead:** Poller is a separate lifecycle service. It creates pipeline invocations when new comments are found.

### Anti-Pattern 4: One Big Comment Batch With No Grouping
**What:** Sending all unresolved comments to the Developer agent as one undifferentiated blob.
**Why bad:** Developer agent loses context. Changes to file A get confused with changes to file B.
**Instead:** Group actionable comments by file path. Developer agent processes file-groups sequentially or the pipeline batches by proximity.

### Anti-Pattern 5: No Max Iteration Guard
**What:** Allowing unlimited fix-review-fix cycles.
**Why bad:** Reviewer keeps commenting, Amelia keeps fixing, infinite loop.
**Instead:** Track iteration count per PR. Cap at configurable max (default 3). After cap, post summary comment explaining remaining items and stop.

## Integration Points With Existing Architecture

### OrchestratorService Changes

Minimal. The `PR_AUTO_FIX` pipeline registers like any other. The key addition is that `PRFixOrchestrator` sits between the poller and the `OrchestratorService`, adding PR-level concurrency on top of the existing worktree-level concurrency.

```
PRCommentPoller
    --> PRFixOrchestrator (PR-level lock)
        --> OrchestratorService (worktree-level lock)
            --> PR_AUTO_FIX Pipeline (LangGraph)
```

### WorkflowType Extension

Add `PR_AUTO_FIX = "pr_auto_fix"` to the `WorkflowType` enum. Dashboard uses this to show distinct badge/icon.

### Profile Extension

Add `auto_fix` config section to `Profile`:

```python
class AutoFixConfig(BaseModel):
    aggressiveness: AggressivenessLevel = AggressivenessLevel.STANDARD
    poll_interval: float = 120.0
    max_iterations: int = 3
    bot_authors: list[str] = Field(default_factory=lambda: ["amelia", "amelia[bot]"])
```

### EventType Extension

New event types:

```python
# PR Auto-Fix
PR_COMMENTS_DETECTED = "pr_comments_detected"
PR_COMMENTS_CLASSIFIED = "pr_comments_classified"
PR_FIX_STARTED = "pr_fix_started"
PR_FIX_COMMITTED = "pr_fix_committed"
PR_FIX_PUSHED = "pr_fix_pushed"
PR_THREADS_RESOLVED = "pr_threads_resolved"
PR_FIX_COMPLETED = "pr_fix_completed"
PR_FIX_SKIPPED = "pr_fix_skipped"  # no actionable comments
PR_FIX_QUEUED = "pr_fix_queued"  # another fix in progress
```

### API Routes

New routes in `routes/pr_autofix.py`:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/prs` | List open PRs for a profile |
| GET | `/api/prs/{number}/comments` | Get review comments for a PR |
| POST | `/api/prs/{number}/fix` | One-shot trigger fix for a PR |
| POST | `/api/prs/{number}/watch` | Start polling a PR |
| DELETE | `/api/prs/{number}/watch` | Stop polling a PR |
| GET | `/api/prs/watching` | List currently watched PRs |

### CLI Commands

| Command | Maps To |
|---------|---------|
| `amelia fix-pr <number>` | One-shot: fetch comments, classify, fix, push, resolve |
| `amelia watch-pr <number>` | Start poller for a single PR (foreground, Ctrl+C to stop) |

## Suggested Build Order

Components have clear dependencies. Build bottom-up:

```
Phase 1: Foundation (no dependencies)
  - Pydantic models (ReviewComment, PRInfo, ClassifiedComment, etc.)
  - PRCommentFetcher (gh CLI wrapper, testable in isolation)
  - ThreadResolver (gh GraphQL wrapper, testable in isolation)
  - GitOps service (git commit/push wrapper)

Phase 2: Classification (depends on models)
  - CommentClassifier (LLM node)
  - Aggressiveness filtering logic
  - AutoFixConfig on Profile

Phase 3: Pipeline (depends on Phase 1 + 2)
  - PRAutoFixState
  - PR_AUTO_FIX LangGraph graph (classify -> develop -> commit -> resolve)
  - Pipeline registration in registry
  - WorkflowType.PR_AUTO_FIX

Phase 4: Orchestration (depends on Phase 3)
  - PRFixOrchestrator (per-PR concurrency)
  - Queue management
  - Max iteration guards
  - New EventType variants

Phase 5: Triggers (depends on Phase 4)
  - PRCommentPoller lifecycle service
  - CLI commands (fix-pr, watch-pr)
  - API routes
  - Dashboard integration
```

Each phase is independently testable. Phase 1 needs only `gh` CLI mocking. Phase 2 needs LLM driver mocking. Phase 3 needs the LangGraph test harness. Phase 4 needs async concurrency testing. Phase 5 is integration.

## Scalability Considerations

| Concern | At 1 PR | At 10 PRs | At 50 PRs |
|---------|---------|-----------|-----------|
| Polling load | 1 `gh` call / interval | 10 `gh` calls / interval | Batch into single GraphQL query |
| Concurrency | Single workflow | 10 concurrent (within `max_concurrent` limit) | Queue, prioritize by comment age |
| Rate limits | Not a concern | Monitor `X-RateLimit-Remaining` | Mandatory backoff, spread polls |
| Worktree usage | 1 worktree per active fix | Reuse worktrees, branch switch | Pool worktrees, limit active fixes |

For v1, the 1-10 PR range is the target. The architecture supports scaling to 50+ but does not optimize for it.

## Sources

- Existing codebase: `amelia/server/lifecycle/health_checker.py` (lifecycle service pattern)
- Existing codebase: `amelia/trackers/github.py` (gh CLI subprocess pattern)
- Existing codebase: `amelia/pipelines/review/graph.py` (LangGraph pipeline pattern)
- Existing codebase: `amelia/pipelines/base.py` (Pipeline protocol)
- Existing codebase: `amelia/pipelines/registry.py` (pipeline registration)
- Existing codebase: `amelia/server/orchestrator/service.py` (concurrency control, WorkflowConflictError)
- Existing codebase: `amelia/server/events/bus.py` (event broadcasting)
- Existing codebase: `amelia/server/models/state.py` (WorkflowType, WorkflowStatus)
- Existing codebase: `amelia/server/routes/github.py` (async gh CLI subprocess in routes)
- Project spec: `.planning/PROJECT.md` (requirements, constraints, decisions)
- GitHub GraphQL API: thread resolution requires `resolveReviewThread` mutation (HIGH confidence, well-documented GitHub API)
- GitHub REST API: PR review comments endpoint `GET /repos/{owner}/{repo}/pulls/{number}/comments` (HIGH confidence)
