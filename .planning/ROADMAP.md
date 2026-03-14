# Roadmap: PR Auto-Fix

## Overview

Amelia's PR Auto-Fix feature autonomously detects GitHub review comments, classifies them by aggressiveness level, applies fixes via the Developer agent, pushes commits, and resolves threads. The roadmap builds bottom-up following the dependency graph: data models first, then GitHub API integration, then classification, then the core pipeline, then orchestration safety, then user-facing triggers (CLI, API, polling), and finally dashboard visibility and metrics. Each phase delivers a testable, coherent capability.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Data Models & Configuration** - Pydantic models and config structures that every other component depends on (completed 2026-03-13)
- [x] **Phase 2: GitHub API Layer** - Fetch PR comments, list PRs, and execute git operations via `gh` CLI (completed 2026-03-13)
- [ ] **Phase 3: Comment Classification** - LLM-based classification with aggressiveness spectrum
- [ ] **Phase 4: Core Fix Pipeline** - LangGraph pipeline wiring classify, develop, and commit/push into a state machine
- [ ] **Phase 5: Thread Resolution & Composition** - Reply to comments, resolve threads, handle partial fixes, compose with review pipeline
- [ ] **Phase 6: Orchestration & Safety** - Per-PR concurrency control, queuing, and branch safety guards
- [ ] **Phase 7: CLI & API Triggers** - Manual trigger points: CLI commands and REST API endpoints
- [ ] **Phase 8: Polling Service** - Background polling for new unresolved comments with rate limit awareness
- [ ] **Phase 9: Events & Dashboard** - Event types for PR auto-fix lifecycle and dashboard UI integration
- [ ] **Phase 10: Metrics & Benchmarking** - Track fix latency, success rates, classification accuracy, and expose via API/dashboard

## Phase Details

### Phase 1: Data Models & Configuration
**Goal**: All data structures and configuration models exist so every downstream component has typed interfaces to build against
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, CONF-01, CONF-02, CONF-03, CONF-04
**Success Criteria** (what must be TRUE):
  1. A `PRSummary` model can represent any GitHub PR with number, title, head branch, author, and timestamps
  2. A `PRReviewComment` model can represent any inline or general review comment with all GitHub metadata (thread ID, path, line, diff hunk)
  3. A `PRAutoFixConfig` model validates and provides defaults for all configuration fields (aggressiveness, polling interval, auto-resolve, max iterations, commit prefix)
  4. An `AggressivenessLevel` enum defines exactly three levels: critical, standard, thorough
  5. Configuration is loadable per-profile with per-PR override capability
**Plans:** 3/3 plans complete

Plans:
- [ ] 01-01-PLAN.md -- TDD: PR auto-fix Pydantic models and AggressivenessLevel enum
- [ ] 01-02-PLAN.md -- Database integration: migration, repository, API routes, server settings
- [ ] 01-03-PLAN.md -- Gap closure: fix nullable pr_autofix update via model_fields_set

### Phase 2: GitHub API Layer
**Goal**: The system can fetch PR data from GitHub and perform git operations, providing the I/O foundation for the fix pipeline
**Depends on**: Phase 1
**Requirements**: GHAPI-01, GHAPI-02, GHAPI-03, GHAPI-04, GHAPI-05, GIT-01, GIT-02, GIT-03, GIT-04
**Success Criteria** (what must be TRUE):
  1. System can fetch all unresolved review comments on a given PR number and return them as `PRReviewComment` model instances
  2. System can list open PRs for a repository and return them as `PRSummary` model instances
  3. System can resolve a review thread via GraphQL and reply to a comment via REST
  4. System correctly detects and filters out bot-authored and self-authored comments
  5. System can stage, commit, pull-before-push, verify SHA, and push to a branch without overwriting human work
**Plans:** 2/2 plans complete

Plans:
- [ ] 02-01-PLAN.md -- TDD: GitHubPRService (fetch comments, list PRs, resolve threads, reply, bot detection)
- [ ] 02-02-PLAN.md -- TDD: GitOperations (stage/commit, safe push with divergence detection and branch protection)

### Phase 3: Comment Classification
**Goal**: The system can take raw review comments and classify each as actionable or non-actionable based on the configured aggressiveness level
**Depends on**: Phase 1, Phase 2
**Requirements**: CMNT-01, CMNT-02, CMNT-03, CMNT-04, CMNT-05
**Success Criteria** (what must be TRUE):
  1. Given a review comment, the LLM classifier returns a structured classification (actionable/non-actionable) with category and confidence
  2. At "critical" aggressiveness, only bug/security comments are classified as actionable; at "exemplary", all substantive comments are
  3. System tracks which comment IDs have been processed and skips them on subsequent runs
  4. System enforces a configurable max fix iteration count per thread (default 3) and stops retrying after the limit
  5. Comments are grouped by file/function for efficient batching to the Developer agent
**Plans:** 2 plans

Plans:
- [ ] 03-01-PLAN.md -- TDD: Classification schemas, CATEGORY_THRESHOLD mapping, is_actionable helper, config update, prompt registration
- [ ] 03-02-PLAN.md -- TDD: Classifier service with pre-filtering, LLM classification, post-filtering, and file grouping

### Phase 4: Core Fix Pipeline
**Goal**: A working LangGraph pipeline that takes classified comments, feeds them to the Developer agent, and produces a commit with fixes pushed to the PR branch
**Depends on**: Phase 1, Phase 2, Phase 3
**Requirements**: PIPE-01, PIPE-02, PIPE-03, PIPE-04, PIPE-05
**Success Criteria** (what must be TRUE):
  1. A PR_AUTO_FIX pipeline is registered in the pipeline registry and can be invoked programmatically
  2. The pipeline flows through nodes: classify, develop, commit/push
  3. The Developer agent receives review comment context including file path, line number, diff hunk, and comment body
  4. All fixes from one pipeline run are committed in a single commit with configurable message prefix
  5. The commit is pushed to the PR's head branch, never to main
**Plans:** 2 plans

Plans:
- [ ] 04-01-PLAN.md -- TDD: State models, pipeline shell, graph topology, registry entry, PR-fix prompt
- [ ] 04-02-PLAN.md -- TDD: Node implementations (classify, develop, commit/push)

### Phase 5: Thread Resolution & Composition
**Goal**: The pipeline completes the feedback loop by replying to reviewers, resolving fixed threads, and gracefully handling comments it cannot fix
**Depends on**: Phase 4
**Requirements**: PIPE-06, PIPE-07, PIPE-08
**Success Criteria** (what must be TRUE):
  1. After pushing fixes, the pipeline replies to each addressed comment explaining what was changed
  2. After replying, the pipeline resolves the corresponding review thread via GraphQL
  3. For comments the Developer agent cannot fix, the pipeline replies explaining why and marks them as needing human attention (does not resolve the thread)
  4. The existing review pipeline can optionally invoke PR_AUTO_FIX when PR context is available
**Plans:** 1/2 plans executed

Plans:
- [ ] 05-01-PLAN.md -- TDD: reply_resolve_node with per-comment replies, conditional thread resolution, error isolation
- [ ] 05-02-PLAN.md -- Document PIPE-08 deferral (review pipeline composition deferred to future phase)

### Phase 6: Orchestration & Safety
**Goal**: The system safely handles concurrent and repeated fix attempts without race conditions, infinite loops, or branch corruption
**Depends on**: Phase 5
**Requirements**: ORCH-01, ORCH-02, ORCH-03
**Success Criteria** (what must be TRUE):
  1. Only one auto-fix workflow runs per PR at a time; concurrent triggers for the same PR are queued
  2. New comments arriving during an active fix cycle are captured and processed in the next cycle, not lost
  3. The Developer agent always operates on the PR's head branch with a fresh pull before making changes
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD

### Phase 7: CLI & API Triggers
**Goal**: Users can trigger PR auto-fix manually from the command line or via HTTP API
**Depends on**: Phase 6
**Requirements**: TRIG-01, TRIG-02, TRIG-03, TRIG-04, TRIG-05
**Success Criteria** (what must be TRUE):
  1. Running `amelia fix-pr 123` fetches unresolved comments on PR #123 and runs the fix pipeline once
  2. Running `amelia watch-pr 123` starts polling PR #123 for new comments at a configurable interval
  3. `POST /api/github/prs/{number}/auto-fix` triggers the fix pipeline and returns a workflow ID
  4. `GET /api/github/prs` returns a list of open PRs for the current profile
  5. `GET /api/github/prs/{number}/comments` returns unresolved comments for a specific PR
**Plans**: TBD

Plans:
- [ ] 07-01: TBD
- [ ] 07-02: TBD
- [ ] 07-03: TBD

### Phase 8: Polling Service
**Goal**: The system autonomously detects new review comments across all configured profiles without manual intervention
**Depends on**: Phase 6
**Requirements**: POLL-01, POLL-02, POLL-03, POLL-04, POLL-05
**Success Criteria** (what must be TRUE):
  1. A background service polls all GitHub-type profiles for new unresolved PR comments at a configurable interval
  2. The polling service follows the start/stop lifecycle pattern and is registered in the server lifespan
  3. The service is resilient to exceptions -- it logs errors and continues polling, never crashes
  4. The service respects GitHub API rate limits and backs off when limits are approached
**Plans**: TBD

Plans:
- [ ] 08-01: TBD
- [ ] 08-02: TBD

### Phase 9: Events & Dashboard
**Goal**: Users can see PR auto-fix activity in real-time through the dashboard with clear status for each comment and workflow
**Depends on**: Phase 7, Phase 8
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04, DASH-05
**Success Criteria** (what must be TRUE):
  1. PR auto-fix lifecycle events (detected, started, completed, resolved, error) are broadcast via the event bus
  2. PR auto-fix workflows appear in the dashboard workflow list with a distinct badge distinguishing them from other workflows
  3. Users can see which specific PR comments triggered a given workflow
  4. Each comment shows its resolution status: fixed, failed, or skipped
  5. Users can view and configure fix aggressiveness per profile from the dashboard
**Plans**: TBD

Plans:
- [ ] 09-01: TBD
- [ ] 09-02: TBD
- [ ] 09-03: TBD

### Phase 10: Metrics & Benchmarking
**Goal**: The system tracks and exposes performance data so users can evaluate fix quality and tune aggressiveness settings
**Depends on**: Phase 9
**Requirements**: METR-01, METR-02, METR-03, METR-04, METR-05, METR-06, METR-07, METR-08
**Success Criteria** (what must be TRUE):
  1. End-to-end latency (comment detection to fix pushed) is tracked for every pipeline run
  2. Fix success rate is tracked per aggressiveness level (fixed / failed / skipped per comment)
  3. LLM classification decisions are logged with comment text for auditability
  4. Metrics are persisted to database and exposed via `GET /api/github/pr-autofix/metrics`
  5. Dashboard shows fix success rates, latency trends, and per-aggressiveness-level breakdown
**Plans**: TBD

Plans:
- [ ] 10-01: TBD
- [ ] 10-02: TBD
- [ ] 10-03: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7/8 (parallel) -> 9 -> 10

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Models & Configuration | 3/3 | Complete   | 2026-03-13 |
| 2. GitHub API Layer | 2/2 | Complete   | 2026-03-13 |
| 3. Comment Classification | 0/2 | Not started | - |
| 4. Core Fix Pipeline | 0/2 | Not started | - |
| 5. Thread Resolution & Composition | 1/2 | In Progress|  |
| 6. Orchestration & Safety | 0/2 | Not started | - |
| 7. CLI & API Triggers | 0/3 | Not started | - |
| 8. Polling Service | 0/2 | Not started | - |
| 9. Events & Dashboard | 0/3 | Not started | - |
| 10. Metrics & Benchmarking | 0/3 | Not started | - |
