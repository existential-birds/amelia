# Requirements: PR Auto-Fix

**Defined:** 2026-03-13
**Core Value:** When a reviewer leaves comments on a PR, Amelia detects them, fixes the code, pushes the update, and resolves the comments — without manual intervention.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### GitHub API

- [x] **GHAPI-01**: System can fetch unresolved review comments on a PR via `gh api` REST endpoint
- [x] **GHAPI-02**: System can list open PRs for a profile's repository via `gh pr list`
- [x] **GHAPI-03**: System can resolve review threads via `gh api graphql` mutation (`resolveReviewThread`)
- [x] **GHAPI-04**: System can reply to review comments with fix explanation via `gh api` REST endpoint
- [x] **GHAPI-05**: System can detect and skip bot/self-authored comments to prevent infinite loops

### Comment Processing

- [x] **CMNT-01**: System classifies review comments as actionable vs non-actionable using LLM
- [x] **CMNT-02**: Classification respects configurable aggressiveness level (critical-only / standard / thorough / exemplary)
- [x] **CMNT-03**: System tracks processed comment IDs to prevent re-fixing already-handled comments
- [x] **CMNT-04**: System enforces max fix iterations per thread (configurable, default 3) to prevent infinite loops
- [x] **CMNT-05**: System groups comments by file/function for efficient batching to Developer agent

### Fix Pipeline

- [x] **PIPE-01**: New PR_AUTO_FIX LangGraph pipeline registered in pipeline registry
- [x] **PIPE-02**: Pipeline nodes: classify → develop → commit/push → reply/resolve
- [x] **PIPE-03**: Developer agent receives PR review comments with file path, line number, diff hunk, and comment body as context
- [x] **PIPE-04**: Pipeline commits all fixes in a single commit with configurable message prefix (default `fix(review):`)
- [x] **PIPE-05**: Pipeline pushes commit to the PR's head branch (never main)
- [ ] **PIPE-06**: Pipeline replies to each fixed comment and resolves the thread
- [ ] **PIPE-07**: Pipeline handles partial fixes — replies to unfixable comments explaining why, marks as needing human attention
- [ ] **PIPE-08**: Existing review pipeline can optionally invoke PR_AUTO_FIX when PR context is available

### Triggers

- [ ] **TRIG-01**: CLI `fix-pr <number>` command triggers one-shot fix for a PR's unresolved comments
- [ ] **TRIG-02**: CLI `watch-pr <number>` command polls a single PR at configurable interval
- [ ] **TRIG-03**: API endpoint `POST /api/github/prs/{number}/auto-fix` triggers fix manually
- [ ] **TRIG-04**: API endpoint `GET /api/github/prs` lists open PRs for a profile
- [ ] **TRIG-05**: API endpoint `GET /api/github/prs/{number}/comments` returns unresolved comments

### Polling Service

- [ ] **POLL-01**: Background service polls all GitHub-type profiles for new unresolved PR comments
- [ ] **POLL-02**: Polling interval is configurable (default 60 seconds)
- [ ] **POLL-03**: Poller uses start/stop lifecycle pattern (registered in server lifespan)
- [ ] **POLL-04**: Poller is resilient to exceptions (logs and continues, does not crash)
- [ ] **POLL-05**: Poller respects GitHub API rate limits with backoff

### Orchestration

- [ ] **ORCH-01**: Only one auto-fix workflow runs per PR at a time
- [ ] **ORCH-02**: New comments arriving during an active fix are queued for the next cycle
- [ ] **ORCH-03**: Developer agent operates on the PR's head branch, not main

### Configuration

- [x] **CONF-01**: `PRAutoFixConfig` Pydantic model with aggressiveness, polling interval, auto-resolve, max iterations, commit prefix
- [x] **CONF-02**: Fix aggressiveness is configurable per-profile (default: standard)
- [x] **CONF-03**: Fix aggressiveness can be overridden per-PR when triggering manually
- [x] **CONF-04**: PR polling can be enabled/disabled globally via server settings

### Events & Dashboard

- [ ] **DASH-01**: New event types: `pr_comments_detected`, `pr_auto_fix_started`, `pr_auto_fix_completed`, `pr_comments_resolved`, `pr_poll_error`
- [ ] **DASH-02**: PR auto-fix workflows appear in dashboard workflow list with distinct badge/icon
- [ ] **DASH-03**: Dashboard shows which PR comments triggered a workflow
- [ ] **DASH-04**: Dashboard shows resolution status per comment (fixed / failed / skipped)
- [ ] **DASH-05**: Dashboard UI for viewing and configuring fix aggressiveness per profile

### Data Models

- [x] **DATA-01**: `PRSummary` Pydantic model (number, title, head_branch, author, updated_at)
- [x] **DATA-02**: `PRReviewComment` Pydantic model (id, thread_id, pr_number, path, line, body, author, created_at, in_reply_to_id, diff_hunk)
- [x] **DATA-03**: `PRAutoFixConfig` Pydantic model (enabled, poll_interval, auto_resolve, max_iterations, commit_prefix, aggressiveness)
- [x] **DATA-04**: `AggressivenessLevel` enum (critical, standard, thorough, exemplary)

### Git Operations

- [x] **GIT-01**: Utility to stage all changes and commit with a message
- [x] **GIT-02**: Utility to push current branch to origin
- [x] **GIT-03**: Pull-before-push discipline to prevent overwriting human work
- [x] **GIT-04**: SHA verification against remote before pushing

### Metrics & Benchmarking

- [ ] **METR-01**: Track time from comment detection to fix pushed (end-to-end latency)
- [ ] **METR-02**: Track fix success rate per aggressiveness level (fixed / failed / skipped per comment)
- [ ] **METR-03**: Track classification accuracy — log LLM classification decisions with comment text for review
- [ ] **METR-04**: Track fix acceptance rate — whether resolved comments stay resolved or get re-opened with new feedback
- [ ] **METR-05**: Track per-pipeline-run metrics: comments processed, fixes applied, commits pushed, threads resolved
- [ ] **METR-06**: Persist metrics to database for historical analysis and trend reporting
- [ ] **METR-07**: Expose metrics via API endpoint `GET /api/github/pr-autofix/metrics`
- [ ] **METR-08**: Dashboard view showing fix success rates, latency trends, and per-aggressiveness-level breakdown

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Advanced Tracing

- **TRACE-01**: Comment-to-fix traceability — map each comment ID to the specific diff that addressed it
- **TRACE-02**: Display traceability mapping in dashboard and in GitHub reply

### Multi-Forge Support

- **FORGE-01**: GitLab merge request comment support
- **FORGE-02**: Bitbucket PR comment support
- **FORGE-03**: Abstract forge interface for pluggable backends

### Advanced Scheduling

- **SCHED-01**: Schedule PR polling windows (e.g., only during business hours)
- **SCHED-02**: Priority queue for PRs based on labels or reviewers

## Out of Scope

| Feature | Reason |
|---------|--------|
| Auto-merging PRs | Merging is a human decision involving business context and approval requirements |
| Generating new review comments (AI reviewer on GitHub) | Amelia has local review pipeline; generating GitHub comments would conflict with human reviewers |
| Cross-repo PR monitoring | Massively increases complexity; scope to profile's configured repository |
| Webhook-based triggers | Requires public endpoint; polling is simpler, works behind firewalls |
| Full issue-to-PR creation | Different product category (Sweep AI territory); focus on review response |
| PyGithub/Octokit library | Inconsistent with existing `gh` CLI subprocess pattern |
| Automatic test generation for fixes | Separate concern; inflates scope. Developer agent can add tests if review comment requests them |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Complete |
| DATA-02 | Phase 1 | Complete |
| DATA-03 | Phase 1 | Complete |
| DATA-04 | Phase 1 | Complete |
| CONF-01 | Phase 1 | Complete |
| CONF-02 | Phase 1 | Complete |
| CONF-03 | Phase 1 | Complete |
| CONF-04 | Phase 1 | Complete |
| GHAPI-01 | Phase 2 | Complete |
| GHAPI-02 | Phase 2 | Complete |
| GHAPI-03 | Phase 2 | Complete |
| GHAPI-04 | Phase 2 | Complete |
| GHAPI-05 | Phase 2 | Complete |
| GIT-01 | Phase 2 | Complete |
| GIT-02 | Phase 2 | Complete |
| GIT-03 | Phase 2 | Complete |
| GIT-04 | Phase 2 | Complete |
| CMNT-01 | Phase 3 | Complete |
| CMNT-02 | Phase 3 | Complete |
| CMNT-03 | Phase 3 | Complete |
| CMNT-04 | Phase 3 | Complete |
| CMNT-05 | Phase 3 | Complete |
| PIPE-01 | Phase 4 | Complete |
| PIPE-02 | Phase 4 | Complete |
| PIPE-03 | Phase 4 | Complete |
| PIPE-04 | Phase 4 | Complete |
| PIPE-05 | Phase 4 | Complete |
| PIPE-06 | Phase 5 | Pending |
| PIPE-07 | Phase 5 | Pending |
| PIPE-08 | Phase 5 | Pending |
| ORCH-01 | Phase 6 | Pending |
| ORCH-02 | Phase 6 | Pending |
| ORCH-03 | Phase 6 | Pending |
| TRIG-01 | Phase 7 | Pending |
| TRIG-02 | Phase 7 | Pending |
| TRIG-03 | Phase 7 | Pending |
| TRIG-04 | Phase 7 | Pending |
| TRIG-05 | Phase 7 | Pending |
| POLL-01 | Phase 8 | Pending |
| POLL-02 | Phase 8 | Pending |
| POLL-03 | Phase 8 | Pending |
| POLL-04 | Phase 8 | Pending |
| POLL-05 | Phase 8 | Pending |
| DASH-01 | Phase 9 | Pending |
| DASH-02 | Phase 9 | Pending |
| DASH-03 | Phase 9 | Pending |
| DASH-04 | Phase 9 | Pending |
| DASH-05 | Phase 9 | Pending |
| METR-01 | Phase 10 | Pending |
| METR-02 | Phase 10 | Pending |
| METR-03 | Phase 10 | Pending |
| METR-04 | Phase 10 | Pending |
| METR-05 | Phase 10 | Pending |
| METR-06 | Phase 10 | Pending |
| METR-07 | Phase 10 | Pending |
| METR-08 | Phase 10 | Pending |

**Coverage:**
- v1 requirements: 56 total
- Mapped to phases: 56
- Unmapped: 0

---
*Requirements defined: 2026-03-13*
*Last updated: 2026-03-13 after roadmap creation*
