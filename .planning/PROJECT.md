# PR Auto-Fix: Autonomous Review Comment Resolution

## What This Is

A feature for Amelia that autonomously detects new code review comments on GitHub pull requests, applies fixes using the Developer agent, pushes changes, and resolves the review threads — creating a fully autonomous review-fix loop. Includes background polling, manual trigger via API/dashboard, adjustable fix aggressiveness, and full dashboard visibility.

## Core Value

When a human reviewer leaves comments on a PR, Amelia detects them, fixes the code, pushes the update, and resolves the comments — without any manual intervention.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ LangGraph pipeline orchestration — existing
- ✓ GitHub CLI integration via `gh` subprocess — existing
- ✓ Event bus + WebSocket broadcasting — existing
- ✓ Background lifecycle services pattern — existing
- ✓ Review-fix workflow (local code review) — existing
- ✓ Developer agent agentic execution — existing
- ✓ Dashboard with real-time workflow updates — existing

### Active

<!-- Current scope. Building toward these. -->

- [ ] Fetch PR review comments via `gh` CLI
- [ ] Fetch open PRs for a repository
- [ ] Resolve review threads via GitHub GraphQL API
- [ ] Reply to review comments explaining fixes
- [ ] Background polling service for new unresolved comments
- [ ] Configurable polling interval
- [ ] New PR_AUTO_FIX pipeline (composable with existing review workflow)
- [ ] Adjustable fix aggressiveness (spectrum: critical-only → exemplary codebase)
- [ ] Aggressiveness configurable per-profile with per-PR override
- [ ] LLM-based comment classification (actionable vs discussion)
- [ ] Git commit and push after fixes
- [ ] Comment deduplication (track processed comment IDs)
- [ ] One auto-fix workflow per PR at a time (queue if in progress)
- [ ] Bot comment detection (skip Amelia's own replies)
- [ ] Max fix iterations per thread (prevent infinite loops)
- [ ] Manual trigger via API endpoint
- [ ] Manual trigger via dashboard UI
- [ ] Dashboard: PR auto-fix workflows with distinct badge/icon
- [ ] Dashboard: show which PR comments triggered a workflow
- [ ] Dashboard: show resolution status per comment
- [ ] Dashboard: UI for configuring fix aggressiveness
- [ ] CLI: `watch-pr` command (poll single PR)
- [ ] CLI: `fix-pr` command (one-shot fix)
- [ ] New event types for PR auto-fix lifecycle
- [ ] PR-related API endpoints (list PRs, get comments, trigger fix)
- [ ] PR auto-fix configuration model (profile-level)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- PyGithub or Octokit — using `gh` CLI subprocess pattern consistent with existing codebase
- Cross-repo PR monitoring — only PRs in the profile's configured repository
- Auto-merging PRs — fixing review comments only, not approving/merging
- GitHub webhooks — polling-based approach avoids infrastructure requirements for webhook receivers
- Non-GitHub forges (GitLab, Bitbucket) — GitHub only for v1

## Context

Amelia already has a review pipeline (`amelia/pipelines/review/`) that runs autonomous review-fix loops on local code. This feature extends that pattern to GitHub PRs: instead of generating reviews locally, it consumes review comments from GitHub and feeds them to the Developer agent.

The existing `GithubTracker` in `amelia/trackers/github.py` handles issue fetching via `gh` CLI. PR comment fetching follows the same subprocess pattern but targets different GitHub API endpoints (REST for fetching, GraphQL for resolving threads).

The `WorktreeHealthChecker` in `amelia/server/lifecycle/health_checker.py` provides the proven pattern for background polling services with start/stop lifecycle, configurable intervals, and exception resilience.

The new PR_AUTO_FIX pipeline should be a standalone LangGraph pipeline registered in the pipeline registry, but designed so the existing review pipeline can optionally invoke it when PR context is available.

### Fix Aggressiveness Spectrum

The aggressiveness setting controls how the Developer agent classifies and handles review comments:

- **Critical only** — fix bugs, security issues, broken functionality
- **Standard** — fix bugs + style issues + explicit change requests
- **Thorough** — fix everything above + suggestions + "nit" comments
- **Exemplary** — treat every comment as an opportunity to improve code quality, no compromises

An LLM classification step determines which comments are actionable at the configured level before passing them to the Developer agent.

## Constraints

- **GitHub CLI (`gh`)**: Must be installed and authenticated — all GitHub operations go through `gh` subprocess (no REST client library)
- **GraphQL requirement**: Resolving review threads requires GitHub GraphQL API (`gh api graphql`), REST API cannot resolve threads
- **Rate limits**: GitHub API rate limits apply — poller must respect `X-RateLimit-Remaining` headers and back off
- **Branch context**: Developer agent must operate on the PR's head branch, not main
- **Existing patterns**: Must follow established patterns (Pydantic models, async throughout, event bus, protocol abstractions)

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| New PR_AUTO_FIX pipeline (not extending review) | Clean separation; composable — existing review workflow can optionally invoke it | — Pending |
| `gh` CLI for all GitHub operations | Consistent with existing `GithubTracker` pattern, avoids new dependencies | — Pending |
| LLM-based comment classification | Enables adjustable aggressiveness without brittle keyword matching | — Pending |
| Per-profile aggressiveness with per-PR override | Flexible — teams can set defaults, individual PRs can override for specific needs | — Pending |
| Polling over webhooks | Simpler infrastructure — no public endpoint needed, works behind firewalls | — Pending |

---
*Last updated: 2026-03-13 after initialization*
