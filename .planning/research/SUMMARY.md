# Project Research Summary

**Project:** Amelia PR Auto-Fix (Autonomous Review Comment Resolution)
**Domain:** Developer tooling / CI automation
**Researched:** 2026-03-13
**Confidence:** HIGH

## Executive Summary

PR auto-fix is the automation of resolving human review comments on GitHub pull requests -- fetching inline comments, classifying which ones are actionable, applying code fixes, pushing commits, and resolving review threads. The competitive landscape (CodeRabbit, Qodo, Copilot Autofix, agent-reviews) validates the category but most tools are either webhook-dependent or lack configurability. Amelia's approach -- polling-based, aggressiveness-configurable, built on existing LangGraph pipelines and `gh` CLI patterns -- is well-differentiated and requires zero new dependencies.

The recommended approach is a bottom-up build: data models and GitHub API wrappers first, then LLM-based comment classification with the aggressiveness spectrum, then a LangGraph pipeline that wires classify-fix-push-resolve into a state machine, then orchestration with per-PR concurrency control, and finally triggers (CLI one-shot, polling service, API routes). This order follows the dependency graph exactly and lets each layer be tested in isolation. The existing codebase provides strong patterns for every layer -- lifecycle services from `WorktreeHealthChecker`, pipeline protocol from `base.py`, subprocess execution from `GithubTracker`, and event broadcasting from `EventBus`.

The dominant risks are infinite fix loops (bot's own pushes trigger re-processing), GitHub API rate limit exhaustion (polling multiple PRs compounds quickly), and race conditions on concurrent pushes to the same branch. All three are preventable with safeguards that must ship in the first working version: hard iteration caps, bot self-detection, rate-limit-aware polling with adaptive backoff, per-PR mutexes, and pull-before-push with SHA verification. Thread resolution via GraphQL has documented edge cases (orphaned threads, incomplete pagination) that need careful handling but are deferrable to a second iteration.

## Key Findings

### Recommended Stack

The entire feature builds on Amelia's existing dependency set with zero new pip packages. All GitHub operations use `gh` CLI subprocess calls (per PROJECT.md constraint), with `gh api` for REST endpoints and `gh api graphql` for thread resolution and thread state queries. A new `GhClient` utility class should wrap `asyncio.create_subprocess_exec` with JSON parsing, error handling, rate-limit awareness, and timeout support to avoid duplicating subprocess boilerplate.

**Core technologies:**
- **`gh` CLI (REST + GraphQL):** All GitHub data fetching and mutations -- handles auth, pagination, and transport with no library dependency
- **LangGraph:** PR_AUTO_FIX pipeline as a registered state machine alongside existing `implementation` and `review` pipelines
- **Pydantic:** Data models for review comments, PR info, classification output, pipeline state -- consistent with codebase conventions
- **asyncio:** Polling loops, subprocess execution, per-PR concurrency locks -- no new concurrency primitives needed
- **PostgreSQL (asyncpg):** Persistent comment tracking for deduplication across restarts

### Expected Features

**Must have (table stakes):**
- Fetch and parse PR review comments (inline + general)
- LLM classification of comments as actionable vs non-actionable
- Apply code fixes via Developer agent
- Commit, push, reply to comments, and resolve threads
- Bot/self comment filtering (prevent infinite loops)
- Deduplication and max iteration limits
- Manual CLI trigger (`amelia fix-pr <number>`)

**Should have (differentiators):**
- Adjustable aggressiveness spectrum (critical-only / standard / thorough / exemplary)
- Background polling with configurable interval
- Dashboard with real-time fix visibility via event bus
- Comment-to-fix traceability (which comment led to which code change)
- Profile-scoped configuration

**Defer (v2+):**
- Dashboard integration (high complexity, core loop works without it)
- Comment-to-fix traceability visualization
- Per-PR aggressiveness override (profile-level default is enough for v1)
- Non-GitHub forge support
- Cross-repo monitoring

### Architecture Approach

Five new components integrate into Amelia's existing architecture: PRCommentPoller (lifecycle service), PRCommentFetcher (stateless `gh` CLI wrapper), CommentClassifier (LangGraph node with structured LLM output), PRFixOrchestrator (per-PR concurrency controller with queue), and the PR_AUTO_FIX pipeline (LangGraph state machine: classify -> develop -> commit/push -> resolve). Each follows an established codebase pattern. The data flow is: poller detects new comments, fetcher retrieves them, classifier filters by aggressiveness, orchestrator ensures one-fix-per-PR, pipeline executes the fix workflow, and events broadcast to the dashboard.

**Major components:**
1. **PRCommentFetcher** -- Fetches and parses review comments via `gh` CLI, filters bots, handles pagination
2. **CommentClassifier** -- Single LLM call with Pydantic structured output; maps comment categories to aggressiveness levels
3. **PR_AUTO_FIX Pipeline** -- LangGraph state machine: classify -> develop_fixes -> commit_and_push -> resolve_threads
4. **PRFixOrchestrator** -- Per-PR asyncio.Lock concurrency control, queues new comments while a fix is in progress, enforces max iterations
5. **PRCommentPoller** -- Lifecycle service following WorktreeHealthChecker pattern, configurable interval, rate-limit aware
6. **ThreadResolver** -- GraphQL mutations for thread resolution, REST for reply comments
7. **GitOps** -- Thin wrapper for commit/push with pull-before-push and SHA verification

### Critical Pitfalls

1. **Infinite fix loops** -- Bot processes its own push events or enters fix-review-fix cycles. Prevent with hard max iterations (default 3 per thread, 5 per PR per cycle), bot self-detection, and post-push cooldown. This is a phase-1 gate.
2. **GitHub API rate limit exhaustion** -- Polling multiple PRs compounds API calls; GraphQL mutations cost 5x. Prevent with adaptive backoff (pause at <5% remaining), incremental fetching via `since` parameter, and batched GraphQL queries. Must be in polling service from day one.
3. **Race conditions on concurrent pushes** -- Human pushes while bot is fixing; bot's push overwrites or fails. Prevent with per-PR mutex, pull-before-push, never force-push, and head SHA verification before push.
4. **Thread resolution edge cases** -- Resolving threads the bot did not actually fix, or missing threads due to GraphQL pagination bugs. Prevent by verifying the fix touched the relevant file/lines before resolving, and replying before resolving for audit trail.
5. **Notification storms** -- Each fix cycle can generate 15+ GitHub notifications. Prevent by batching all fixes into a single commit and offering configurable verbosity (per-thread replies vs single summary).

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Foundation -- Data Models and GitHub API Layer
**Rationale:** Everything depends on the data models and the ability to fetch/parse GitHub data. This is zero-risk, well-patterned work that unblocks all subsequent phases.
**Delivers:** Pydantic models (ReviewComment, PRInfo, ClassifiedComment, PRAutoFixState, CommitResult), PRCommentFetcher service, ThreadResolver service, GitOps service, GhClient utility wrapper, AutoFixConfig on Profile.
**Addresses:** Fetch/parse PR comments, bot detection, deduplication data model
**Avoids:** Pitfall #9 (gh CLI error handling) by building a robust wrapper with GraphQL error checking, timeouts, and structured error types from the start

### Phase 2: Classification and Aggressiveness
**Rationale:** Depends on Phase 1 models. Classification is the decision layer -- nothing downstream makes sense without knowing which comments to act on. Building the aggressiveness spectrum early establishes the core differentiator.
**Delivers:** CommentClassifier LangGraph node, aggressiveness level mapping, structured LLM output with confidence scores, bot detection heuristics
**Addresses:** LLM comment classification, aggressiveness spectrum (differentiator)
**Avoids:** Pitfall #7 (classification errors) by requiring structured output with confidence scores and supporting dry-run mode for validation

### Phase 3: Fix Pipeline
**Rationale:** Depends on Phase 1 (GitOps, ThreadResolver) and Phase 2 (ClassifiedComment output). This is the core value delivery -- wiring classify -> develop -> commit -> push -> resolve into a LangGraph state machine.
**Delivers:** PR_AUTO_FIX LangGraph pipeline, pipeline registration in registry, WorkflowType.PR_AUTO_FIX, Developer agent integration for fix application, thread resolution after push, reply comments
**Addresses:** Apply fixes, commit/push, reply to comments, resolve threads
**Avoids:** Pitfall #4 (thread resolution edge cases) by verifying fixes before resolving; Pitfall #8 (notification storm) by batching fixes into single commit

### Phase 4: Orchestration and Safety
**Rationale:** Depends on Phase 3 pipeline existing. Adds the concurrency and safety layer that makes the system production-safe. Without this, running the pipeline on multiple PRs or re-running on the same PR is dangerous.
**Delivers:** PRFixOrchestrator with per-PR mutex, queue management, max iteration guards, new EventType variants for dashboard observability
**Addresses:** Deduplication, max iteration limits, per-PR concurrency
**Avoids:** Pitfall #1 (infinite loops) with hard caps; Pitfall #3 (race conditions) with per-PR locks and SHA checks; Pitfall #5 (deduplication failures) with persistent state

### Phase 5: Triggers and Integration
**Rationale:** Depends on Phase 4 orchestration being safe. Adds the user-facing entry points: CLI command, API routes, polling service. Dashboard integration is optional stretch.
**Delivers:** `amelia fix-pr` CLI command, API routes (`/api/prs/{number}/fix`, watch/unwatch), PRCommentPoller lifecycle service, optional dashboard views
**Addresses:** Manual trigger, background polling, API endpoints
**Avoids:** Pitfall #2 (rate limits) with adaptive backoff in poller; Pitfall #6 (branch context mismatch) with fetch-before-checkout in worktree setup

### Phase Ordering Rationale

- Phases follow the dependency graph: models -> classification -> pipeline -> orchestration -> triggers. Each phase is independently testable.
- Safety mechanisms (loop guards, rate limits, concurrency locks) are split between Phase 4 (orchestration-level) and Phase 1 (API-level). This ensures that when the pipeline first runs in Phase 3, the foundational safety (robust gh wrapper, bot detection) is already in place, and production-grade safety (iteration caps, mutexes) lands in Phase 4 before any polling or multi-PR usage.
- The aggressiveness spectrum (Phase 2) is built before the pipeline (Phase 3) because it is both a dependency and the primary differentiator -- getting classification right early avoids rework.
- Triggers are last because the fix pipeline must be correct and safe before exposing it via CLI, API, or background polling.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Fix Pipeline):** The Developer agent integration needs research -- how to pass review comment context (file path, line number, diff hunk) as a task. The existing `call_developer_node` may need adaptation for PR-fix-specific prompting.
- **Phase 5 (Triggers - Polling):** Rate limit budget calculation needs validation against real-world API usage. The 2,400 requests/hour estimate for 10 PRs is theoretical.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** All patterns are directly cloned from existing codebase (GithubTracker, Pydantic models, async subprocess). Well-documented GitHub API endpoints.
- **Phase 2 (Classification):** Standard LLM structured output pattern. Amelia already does this in other pipelines.
- **Phase 4 (Orchestration):** Follows OrchestratorService concurrency pattern with asyncio.Lock. Straightforward adaptation.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Zero new dependencies. All patterns verified against existing codebase. GitHub API endpoints confirmed via official docs. |
| Features | HIGH | Competitive landscape well-documented. Clear separation of table stakes vs differentiators validated against 6+ competitor tools. |
| Architecture | HIGH | Every component maps to an existing codebase pattern. Build order validated against dependency graph. |
| Pitfalls | HIGH | All critical pitfalls verified against GitHub community discussions, official rate limit docs, and real-world reports from similar tools. |

**Overall confidence:** HIGH

### Gaps to Address

- **Developer agent prompting for PR fixes:** How to structure the LLM prompt so the Developer agent understands it is fixing a specific review comment (with file path, line, diff hunk context) rather than implementing a feature. Needs experimentation during Phase 3.
- **GraphQL pagination reliability:** GitHub community reports incomplete comment retrieval in review thread GraphQL queries. Need to validate pagination behavior with real PRs that have 100+ threads during Phase 1 testing.
- **Rate limit budget under real load:** The theoretical calculation (10 PRs * 4 calls * 60 polls/hour = 2,400/hour) needs validation. GraphQL point costs for complex queries may be higher than estimated.
- **Deduplication persistence strategy:** In-memory tracking is acceptable for MVP but loses state on restart. The transition to PostgreSQL-backed tracking should be planned but can be deferred past initial phases.

## Sources

### Primary (HIGH confidence)
- [GitHub REST API: Pull Request Review Comments](https://docs.github.com/en/rest/pulls/comments)
- [GitHub REST API: Pull Request Reviews](https://docs.github.com/en/rest/pulls/reviews)
- [GitHub GraphQL Mutations (resolveReviewThread)](https://docs.github.com/en/graphql/reference/mutations)
- [GitHub REST API Rate Limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- [gh CLI manual (pr view, pr list)](https://cli.github.com/manual/)
- Existing codebase patterns: `health_checker.py`, `GithubTracker`, `routes/github.py`, `pipelines/base.py`, `registry.py`, `orchestrator/service.py`, `events/bus.py`

### Secondary (MEDIUM confidence)
- [CodeRabbit Documentation](https://docs.coderabbit.ai/) -- competitor feature analysis
- [Qodo PR-Agent Review Docs](https://qodo-merge-docs.qodo.ai/tools/review/) -- competitor feature analysis
- [agent-reviews on GitHub](https://github.com/pbakaus/agent-reviews) -- competitor implementation reference
- [State of AI Code Review Tools 2025](https://www.devtoolsacademy.com/blog/state-of-ai-code-review-tools-2025) -- market landscape

### Tertiary (LOW confidence)
- [GitHub Community: GraphQL Review Thread Bugs](https://github.com/orgs/community/discussions/24666) -- pagination issues, needs validation
- [gh CLI Rate Limit Discussion](https://github.com/cli/cli/discussions/7754) -- gh CLI rate limit handling limitations

---
*Research completed: 2026-03-13*
*Ready for roadmap: yes*
