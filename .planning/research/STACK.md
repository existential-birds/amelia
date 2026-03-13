# Technology Stack: PR Auto-Fix

**Project:** Amelia PR Auto-Fix (Autonomous Review Comment Resolution)
**Researched:** 2026-03-13

## Guiding Constraint

The PROJECT.md explicitly scopes out PyGithub, Octokit, and any REST client library. All GitHub operations go through `gh` CLI subprocess calls, consistent with the existing `GithubTracker` and `amelia/server/routes/github.py` patterns. This stack document therefore focuses on **how to use `gh` CLI effectively**, not which GitHub client library to pick.

## Recommended Stack

### GitHub Data Fetching (via `gh` CLI)

| Command Pattern | Purpose | Confidence | Why |
|----------------|---------|------------|-----|
| `gh api repos/{owner}/{repo}/pulls/{pr}/comments --paginate` | Fetch all inline review comments (REST) | HIGH | Returns full review comment objects with `path`, `line`, `body`, `id`, `node_id`, `in_reply_to_id`, `user.login`, `created_at`, `updated_at`. Supports `--paginate` for complete results. The `since` query parameter enables incremental polling. |
| `gh api repos/{owner}/{repo}/pulls/{pr}/reviews --paginate` | Fetch review submissions (approve/request changes/comment) | HIGH | Returns review-level data: `state`, `body`, `user`. Needed to understand review context (e.g., "changes requested"). Does NOT include inline comments -- those come from the comments endpoint above. |
| `gh pr view {pr} --json headRefName,headRefOid,baseRefName,number,url,state` | Get PR metadata (branch, SHA, status) | HIGH | Already-proven pattern in codebase. Gives branch name for checkout. |
| `gh pr list --json number,title,state,reviewDecision,updatedAt --state open` | List open PRs for polling | HIGH | Same pattern as existing issue list endpoint. `reviewDecision` field filters to PRs with pending reviews. |
| `gh api graphql` | Resolve review threads, add review comments | HIGH | Required -- REST API cannot resolve review threads. GraphQL is the only path. |

**Critical distinction:** GitHub has three separate comment types on PRs, each with its own endpoint:
1. **PR review comments** (`/pulls/{pr}/comments`) -- inline code comments. This is the primary target.
2. **Issue comments** (`/issues/{pr}/comments`) -- general discussion comments on the PR. Secondary target.
3. **Review bodies** (`/pulls/{pr}/reviews`) -- the top-level review text. Context only.

The auto-fix feature primarily consumes type 1 (inline review comments) and optionally type 2 (general comments that request changes).

### GraphQL Operations (via `gh api graphql`)

| Operation | GraphQL | Confidence | Why |
|-----------|---------|------------|-----|
| Fetch review threads with resolution status | `query { repository { pullRequest { reviewThreads { nodes { id, isResolved, isOutdated, path, line, comments { nodes { body, author } } } } } } }` | HIGH | REST API does not expose `isResolved` or thread grouping. GraphQL is the only way to know which threads are already resolved. |
| Resolve a review thread | `mutation { resolveReviewThread(input: { threadId: $id }) { thread { id, isResolved } } }` | HIGH | Documented mutation. Requires `Contents: Read and Write` permission on the `gh` auth token. |
| Add a reply to a review thread | `mutation { addPullRequestReviewComment }` or REST `POST /pulls/{pr}/comments` with `in_reply_to` | MEDIUM | For explaining what Amelia fixed. REST `in_reply_to` field works for replies; GraphQL needed only if threading is complex. |

**Pagination:** Review threads endpoint supports cursor-based pagination (`after` parameter). For PRs with >100 threads, must paginate. Use `pageInfo { hasNextPage, endCursor }`.

### Async Subprocess Pattern (existing)

| Component | Location | Confidence | Why |
|-----------|----------|------------|-----|
| `asyncio.create_subprocess_exec` | `amelia/server/routes/github.py` | HIGH | Already the established async pattern for `gh` CLI calls. Use this, not `subprocess.run`. |
| `asyncio.create_subprocess_shell` | `amelia/tools/git_utils.py` | HIGH | Used for git commands. Prefer `_exec` over `_shell` for `gh` commands (safer, no shell injection). |
| `json.loads()` on stdout | Both files above | HIGH | Standard JSON parsing of `gh` output. |

**New utility needed:** A shared `GhClient` class wrapping `asyncio.create_subprocess_exec` for `gh` CLI calls with:
- JSON response parsing
- Error handling (non-zero exit, stderr capture)
- Rate limit awareness (parse `X-RateLimit-Remaining` from `gh api --include` headers)
- Timeout support (reuse the `asyncio.wait_for` pattern from `git_utils.py`)
- GraphQL query execution helper

This avoids duplicating the subprocess boilerplate across every new endpoint.

### Polling Service Pattern (existing)

| Component | Location | Confidence | Why |
|-----------|----------|------------|-----|
| `WorktreeHealthChecker` | `amelia/server/lifecycle/health_checker.py` | HIGH | Proven pattern: `asyncio.Task` with `while True` / `await asyncio.sleep(interval)` / exception resilience. Clone this for the PR comment poller. |
| `LogRetentionService` | `amelia/server/lifecycle/retention.py` | HIGH | Shows the Protocol-based dependency injection pattern for testability. |

The PR comment poller should follow the `WorktreeHealthChecker` pattern exactly:
- `start()` / `stop()` lifecycle methods
- `asyncio.create_task` for the polling loop
- Broad exception catch in the loop body (never crash the poller)
- Configurable interval via constructor parameter

### Git Operations (existing)

| Operation | Tool | Confidence | Why |
|-----------|------|------------|-----|
| Checkout PR branch | `git checkout` or `git switch` via `_run_git_command` | HIGH | Existing async git utility handles this. |
| Commit changes | `git commit` via `_run_git_command` | HIGH | Same pattern. |
| Push to remote | `git push` via `_run_git_command` | HIGH | Same pattern. Must push to the PR's head branch. |
| Create worktree for PR | `git worktree add` | HIGH | Amelia already uses worktrees for workflow isolation. Each PR fix should operate in its own worktree to avoid conflicts with other running workflows. |

### Comment Classification (LLM)

| Component | Technology | Confidence | Why |
|-----------|-----------|------------|-----|
| LLM classification | Existing LangChain/LangGraph pipeline | HIGH | Amelia already has LLM orchestration. Classification is a single LLM call with structured output (Pydantic model). No new dependencies needed. |
| Structured output | Pydantic model with `actionable: bool`, `category: Literal[...]`, `priority: int` | HIGH | Consistent with codebase conventions. LangChain supports Pydantic structured output natively. |

### State Tracking

| Component | Technology | Confidence | Why |
|-----------|-----------|------------|-----|
| Processed comment IDs | PostgreSQL (existing `asyncpg` connection) | HIGH | Amelia already has Postgres for workflow state. Add a `pr_comment_tracker` table for deduplication. |
| Workflow state | LangGraph checkpointer (existing) | HIGH | PR auto-fix is a new pipeline type -- LangGraph handles state persistence automatically. |

### No New Dependencies Required

The entire PR auto-fix feature can be built with **zero new pip dependencies**. Everything needed is already in `pyproject.toml`:

| Existing Dependency | Used For |
|-------------------|----------|
| `asyncio` (stdlib) | Subprocess execution, polling loops, task management |
| `json` (stdlib) | Parsing `gh` CLI JSON output |
| `pydantic` | Review comment models, classification output models, config models |
| `langgraph` | PR auto-fix pipeline definition and state management |
| `fastapi` | New API endpoints for manual trigger, PR listing |
| `asyncpg` | Comment tracking table, deduplication state |
| `loguru` | Structured logging throughout |
| `httpx` | NOT needed -- using `gh` CLI instead of HTTP client |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| GitHub client | `gh` CLI subprocess | PyGithub, ghapi, httpx to REST API | Explicitly out of scope per PROJECT.md. `gh` CLI handles auth, pagination, rate limiting. Consistent with existing codebase. |
| GraphQL client | `gh api graphql` subprocess | gql, sgqlc, httpx + manual queries | Adding a GraphQL client library is unnecessary when `gh api graphql` handles auth and transport. One fewer dependency to maintain. |
| Polling | `asyncio.Task` loop | APScheduler, Celery Beat, cron | Existing pattern works. APScheduler adds dependency for no benefit. Celery is massive overkill for a single polling loop. |
| Comment parsing | Manual JSON parsing | Pydantic model validation of raw API response | Actually, DO use Pydantic: parse `gh` JSON output into Pydantic models immediately. This is the "alternative" that should be the standard. |
| State storage | PostgreSQL | SQLite, Redis, in-memory dict | Postgres is already running for workflow state. Adding another store is unnecessary complexity. |
| Webhook delivery | Polling | GitHub Webhooks | Explicitly out of scope per PROJECT.md. Polling avoids public endpoint requirement, works behind firewalls. |

## Key `gh` CLI Commands Reference

```bash
# List open PRs with review status
gh pr list --json number,title,state,reviewDecision,updatedAt --state open --repo owner/repo

# Get PR metadata
gh pr view 123 --json headRefName,headRefOid,baseRefName,number,url,state

# Fetch all inline review comments (paginated)
gh api repos/{owner}/{repo}/pulls/123/comments --paginate

# Fetch review comments since a timestamp (incremental polling)
gh api "repos/{owner}/{repo}/pulls/123/comments?since=2026-03-13T00:00:00Z" --paginate

# Fetch review threads with resolution status (GraphQL)
gh api graphql -F owner='{owner}' -F repo='{repo}' -F pr=123 -f query='
  query($owner: String!, $repo: String!, $pr: Int!) {
    repository(owner: $owner, name: $repo) {
      pullRequest(number: $pr) {
        reviewThreads(first: 100) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id
            isResolved
            isOutdated
            path
            line
            startLine
            comments(last: 10) {
              nodes {
                id
                body
                author { login }
                createdAt
              }
            }
          }
        }
      }
    }
  }
'

# Resolve a review thread
gh api graphql -F threadId='THREAD_NODE_ID' -f query='
  mutation($threadId: ID!) {
    resolveReviewThread(input: { threadId: $threadId }) {
      thread { id isResolved }
    }
  }
'

# Reply to a review comment (REST)
gh api repos/{owner}/{repo}/pulls/123/comments \
  -f body="Fixed in latest commit." \
  -F in_reply_to=COMMENT_ID

# Push changes
git push origin HEAD
```

## Rate Limit Strategy

GitHub API rate limits: 5,000 requests/hour for authenticated users.

| Approach | Implementation |
|----------|---------------|
| Monitor remaining quota | Parse headers from `gh api --include` (first line contains HTTP headers) |
| Exponential backoff | On 403/rate-limit response, double the polling interval temporarily |
| Incremental fetching | Use `since` parameter on comment endpoints to fetch only new/updated comments |
| Batch GraphQL | Fetch all review threads in one GraphQL query instead of per-thread REST calls |
| Configurable interval | Default 60s polling, configurable per-profile. Minimum 30s to stay well within limits. |

A single PR poll cycle uses approximately 2-3 API calls (list comments, list threads, PR metadata). At 60s intervals watching 5 PRs, that is ~15 calls/minute = 900 calls/hour, well within the 5,000/hour limit.

## Sources

- [GitHub REST API: Pull Request Review Comments](https://docs.github.com/en/rest/pulls/comments)
- [GitHub REST API: Pull Request Reviews](https://docs.github.com/en/rest/pulls/reviews)
- [GitHub GraphQL Mutations (resolveReviewThread)](https://docs.github.com/en/graphql/reference/mutations)
- [gh pr view manual](https://cli.github.com/manual/gh_pr_view)
- [gh pr list manual](https://cli.github.com/manual/gh_pr_list)
- [GraphQL resolveReviewThread permissions discussion](https://github.com/orgs/community/discussions/44650)
- [Bulk resolve PR comments via API](https://nesin.io/blog/bulk-resolve-github-pr-comments-api)
- [gh CLI inline review comments feature request](https://github.com/cli/cli/issues/12273)
- [Retrieving PR reviews discussion](https://github.com/cli/cli/discussions/3993)
