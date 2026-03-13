# Phase 2: GitHub API Layer - Research

**Researched:** 2026-03-13
**Domain:** GitHub API (REST + GraphQL) via `gh` CLI subprocess, async git operations
**Confidence:** HIGH

## Summary

This phase builds the I/O foundation for PR auto-fix: fetching PR review comments, listing PRs, resolving threads, replying to comments, detecting self/bot comments, and performing safe git commit/push operations. All GitHub API calls use the `gh` CLI via `asyncio.create_subprocess_exec`, following the established pattern in `amelia/server/routes/github.py`.

The codebase already has: (1) `PRReviewComment` and `PRSummary` Pydantic models in `amelia/core/types.py`, (2) `PRAutoFixConfig` needing an `ignore_authors` field addition, (3) an async `_run_git_command` helper in `amelia/tools/git_utils.py`, and (4) `GithubTracker` as a sync pattern reference. The work is to create a new async `GitHubPRService` class and extend the git utility module with stage/commit/push/pull/SHA-verify operations.

**Primary recommendation:** Create two new modules -- `amelia/services/github_pr.py` (GitHubPRService) and extend `amelia/tools/git_utils.py` (git operations) -- both using `asyncio.create_subprocess_exec` with the existing error handling patterns (CalledProcessError -> ValueError, JSONDecodeError -> ValueError).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Fix explanation replies: concise & factual tone, no diff snippets, footer signature `---\n_Amelia (automated fix)_`, unfixable comments get "Could not auto-fix: [reason]. Flagging for human review."
- Bot & self detection: self-detection via footer signature match, allow all comments by default, configurable `ignore_authors: list[str]` on PRAutoFixConfig, exact username matching only
- Git push safety: abort on remote divergence (never rebase), force-push never allowed, push failures via event bus + loguru, hard guard against main/master/protected branches
- All `gh` CLI calls use `asyncio.create_subprocess_exec` (not sync subprocess.run)
- Existing `GithubTracker` remains sync and untouched
- New `GitHubPRService` class in a new module for all PR-related GitHub API operations
- Separate async git utility class/module for stage, commit, push, pull, SHA verification

### Claude's Discretion
- Exact module file paths and class naming
- Internal helper method decomposition
- GraphQL query structure for thread resolution
- Timeout and subprocess error handling details
- Whether git utility uses a protocol/ABC or concrete class

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| GHAPI-01 | Fetch unresolved review comments on a PR via `gh api` REST | REST endpoint `GET /repos/{owner}/{repo}/pulls/{pull_number}/comments` with `--paginate`; GraphQL query for thread resolution status |
| GHAPI-02 | List open PRs for a profile's repository via `gh pr list` | `gh pr list --json number,title,headRefName,author,updatedAt --state open`; follows existing issue list pattern in `server/routes/github.py` |
| GHAPI-03 | Resolve review threads via `gh api graphql` mutation | `resolveReviewThread` GraphQL mutation with `threadId` input; requires thread node_id from GraphQL query |
| GHAPI-04 | Reply to review comments with fix explanation via `gh api` REST | `POST /repos/{owner}/{repo}/pulls/{pull_number}/comments/{comment_id}/replies` with `body` field |
| GHAPI-05 | Detect and skip bot/self-authored comments | Footer signature match (`_Amelia (automated fix)_` in body) + configurable `ignore_authors` list on PRAutoFixConfig |
| GIT-01 | Stage all changes and commit with a message | `git add -A` + `git commit -m` via existing `_run_git_command` pattern |
| GIT-02 | Push current branch to origin | `git push origin HEAD` via async subprocess |
| GIT-03 | Pull-before-push discipline | `git fetch origin` + compare local/remote SHA; abort if diverged (never rebase) |
| GIT-04 | SHA verification against remote before pushing | `git rev-parse HEAD` vs `git rev-parse origin/{branch}`; refuse push if remote has advanced |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `gh` CLI | 2.x (system) | All GitHub API calls | Already used throughout codebase; authenticated subprocess pattern established |
| asyncio | stdlib | Async subprocess execution | Project convention for all I/O operations |
| Pydantic | 2.x (existing) | Data models | All project models are Pydantic; PRReviewComment/PRSummary already defined |
| loguru | existing | Structured logging | Project-wide logging standard |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json | stdlib | Parse `gh` CLI JSON output | Every subprocess call with `--json` flag |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `gh` CLI subprocess | PyGithub/Octokit | Explicitly out of scope per REQUIREMENTS.md -- inconsistent with established pattern |
| `asyncio.create_subprocess_exec` | `asyncio.create_subprocess_shell` | exec is safer (no shell injection), use exec for `gh` commands; existing `_run_git_command` uses shell but new code should prefer exec |

**Installation:**
No new dependencies needed. All tools are already in the project.

## Architecture Patterns

### Recommended Project Structure
```
amelia/
  services/
    __init__.py
    github_pr.py          # GitHubPRService class (GHAPI-01 through GHAPI-05)
  tools/
    git_utils.py           # Extended with GitOperations class (GIT-01 through GIT-04)
  core/
    types.py               # PRAutoFixConfig gets ignore_authors field
tests/
  unit/
    services/
      __init__.py
      test_github_pr.py    # Unit tests for GitHubPRService
    tools/
      test_git_utils.py    # Unit tests for GitOperations
```

### Pattern 1: Async gh CLI Subprocess (established pattern)
**What:** All GitHub API calls go through `asyncio.create_subprocess_exec` with `gh` CLI
**When to use:** Every GitHub API interaction
**Example:**
```python
# Source: amelia/server/routes/github.py (existing pattern)
async def _run_gh(
    *args: str,
    cwd: str | None = None,
    timeout: float = 30.0,
) -> str:
    """Run gh CLI command and return stdout."""
    proc = await asyncio.create_subprocess_exec(
        "gh", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout,
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise ValueError(f"gh command timed out after {timeout}s: gh {' '.join(args)}")

    if proc.returncode != 0:
        raise ValueError(f"gh command failed: {stderr_bytes.decode().strip()}")
    return stdout_bytes.decode()
```

### Pattern 2: GraphQL via gh api
**What:** GraphQL queries and mutations through `gh api graphql`
**When to use:** Thread resolution (GHAPI-03), fetching thread node IDs
**Example:**
```python
# Resolve a review thread
query = """
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread { isResolved }
  }
}
"""
result = await self._run_gh(
    "api", "graphql",
    "-f", f"query={query}",
    "-f", f"threadId={thread_id}",
    cwd=self._repo_root,
)
```

### Pattern 3: REST API via gh api
**What:** REST calls through `gh api` for endpoints not covered by gh subcommands
**When to use:** Fetching review comments (GHAPI-01), replying to comments (GHAPI-04)
**Example:**
```python
# Fetch review comments on a PR
result = await self._run_gh(
    "api", "--paginate",
    f"/repos/{{owner}}/{{repo}}/pulls/{pr_number}/comments",
    cwd=self._repo_root,
)
comments_data = json.loads(result)

# Reply to a comment
await self._run_gh(
    "api", "--method", "POST",
    f"/repos/{{owner}}/{{repo}}/pulls/{pr_number}/comments/{comment_id}/replies",
    "-f", f"body={reply_body}",
    cwd=self._repo_root,
)
```

### Pattern 4: Git Operations with Safety Guards
**What:** Async git commands with branch protection and divergence detection
**When to use:** All GIT-* requirements
**Example:**
```python
PROTECTED_BRANCHES = frozenset({"main", "master", "develop", "release"})

async def push(self, branch: str) -> str:
    """Push current branch to origin with safety guards."""
    if branch in PROTECTED_BRANCHES:
        raise ValueError(f"Refusing to push to protected branch: {branch}")

    # Fetch latest remote state
    await self._run_git("fetch", "origin", branch)

    # Compare SHAs
    local_sha = await self._run_git("rev-parse", "HEAD")
    try:
        remote_sha = await self._run_git("rev-parse", f"origin/{branch}")
    except ValueError:
        remote_sha = None  # Branch doesn't exist on remote yet

    if remote_sha:
        # Check if local is ahead of remote (not diverged)
        merge_base = await self._run_git("merge-base", local_sha, remote_sha)
        if merge_base != remote_sha:
            raise ValueError(
                f"Remote branch has diverged. Local: {local_sha[:8]}, "
                f"Remote: {remote_sha[:8]}, Base: {merge_base[:8]}. "
                "Aborting push -- manual intervention required."
            )

    result = await self._run_git("push", "origin", "HEAD")
    return local_sha
```

### Anti-Patterns to Avoid
- **Shell injection in subprocess calls:** Use `create_subprocess_exec` (list args), not `create_subprocess_shell` with string interpolation. The existing `_run_git_command` uses `create_subprocess_shell` -- new git operations should prefer exec.
- **Mixing sync and async:** All new code must be async. Do NOT call sync `subprocess.run` in async context.
- **Rebasing on divergence:** User decision is firm -- abort and report, never rebase.
- **Force push:** Never, under any circumstances.
- **Parsing unstructured gh output:** Always use `--json` flag for structured output from `gh pr list`. Use `gh api` for REST endpoints that return JSON natively.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| GitHub API authentication | Token management | `gh` CLI handles auth | Already authenticated, handles token refresh, respects GH_TOKEN env |
| Pagination | Manual page traversal | `gh api --paginate` | Handles Link headers, merges JSON arrays automatically |
| GraphQL query building | String template library | Direct f-string with `gh api graphql -f` | Queries are simple, static; no need for a query builder |
| Branch protection detection | Custom rule engine | Hard-coded frozenset + configurable patterns | Simple for v1; GitHub's branch protection API is overkill |
| JSON response parsing | Custom deserializers | Pydantic `model_validate` | Models already defined in types.py |

**Key insight:** The `gh` CLI abstracts away authentication, pagination, and API version negotiation. Do not bypass it.

## Common Pitfalls

### Pitfall 1: REST vs GraphQL Comment IDs
**What goes wrong:** GitHub REST API returns numeric `id` fields, but GraphQL uses `node_id` (base64-encoded global ID). The `resolveReviewThread` mutation needs the GraphQL thread ID, not the REST comment ID.
**Why it happens:** Two different ID systems across REST and GraphQL APIs.
**How to avoid:** REST review comments include a `node_id` field -- store it in `PRReviewComment.node_id`. For thread resolution, need the review thread's node_id (not the comment's node_id). Must query threads via GraphQL to get thread-level node IDs.
**Warning signs:** "Could not resolve thread" errors with numeric IDs.

### Pitfall 2: Paginated Response Format
**What goes wrong:** `gh api --paginate` for REST endpoints returns a JSON array that is the concatenation of all pages' arrays. But for a single page, it returns just the array. The output is always a valid JSON array.
**Why it happens:** `gh api` handles pagination transparently.
**How to avoid:** Always `json.loads()` the result and expect a list. This works for both single-page and multi-page responses.
**Warning signs:** Empty results when PR has many comments.

### Pitfall 3: Review Comments vs Issue Comments
**What goes wrong:** GitHub has two comment types on PRs: (1) review comments (inline on code diffs) via `/pulls/{n}/comments`, and (2) issue comments (general discussion) via `/issues/{n}/comments`. Auto-fix should focus on review comments (code-specific feedback).
**Why it happens:** GitHub's dual comment system is not obvious.
**How to avoid:** Use `/repos/{owner}/{repo}/pulls/{pull_number}/comments` for review comments. Do NOT use `/issues/{n}/comments`.
**Warning signs:** Getting general discussion comments mixed with code review feedback.

### Pitfall 4: Thread Resolution Requires Thread ID, Not Comment ID
**What goes wrong:** Trying to resolve a thread using a comment's node_id instead of the thread's node_id.
**Why it happens:** Comments belong to threads, but the resolveReviewThread mutation needs the thread's ID.
**How to avoid:** Use GraphQL to query `pullRequest.reviewThreads.nodes` which returns `{ id, isResolved, comments { nodes { databaseId } } }`. Map comment IDs to thread IDs. Store thread node_id on PRReviewComment during fetch.
**Warning signs:** GraphQL mutation returns "Could not resolve to a node" error.

### Pitfall 5: `gh api` Placeholder Expansion
**What goes wrong:** `gh api` automatically expands `{owner}` and `{repo}` placeholders based on the git remote of the cwd. If cwd is wrong, wrong repo is targeted.
**Why it happens:** `gh` uses the git remote of the working directory.
**How to avoid:** Always pass `cwd=self._repo_root` to subprocess calls. The `{owner}` and `{repo}` placeholders in REST URLs will resolve correctly from the repo's git remote.
**Warning signs:** 404 errors or operations on wrong repository.

### Pitfall 6: Git Fetch Before SHA Comparison
**What goes wrong:** Comparing local HEAD against `origin/{branch}` without fetching first gives stale remote SHA.
**Why it happens:** `origin/{branch}` is a local tracking ref that is only updated on fetch/pull.
**How to avoid:** Always `git fetch origin {branch}` before comparing SHAs.
**Warning signs:** Push succeeds but overwrites remote commits that arrived between fetch and push.

### Pitfall 7: Reply Endpoint Requires Top-Level Comment ID
**What goes wrong:** The reply endpoint `POST /pulls/{n}/comments/{comment_id}/replies` requires the top-level comment ID. If you pass a reply's ID (a comment that itself is a reply), it fails.
**Why it happens:** GitHub only supports one level of threading for review comments.
**How to avoid:** When replying, use the original comment's ID. If `in_reply_to_id` is set, that's the parent -- reply to the parent, not the child.
**Warning signs:** 422 error from GitHub API.

## Code Examples

### Fetching PR Review Comments (GHAPI-01)

```python
# Two-step approach: REST for comment data, GraphQL for thread resolution status

# Step 1: REST -- get all review comments
raw = await self._run_gh(
    "api", "--paginate",
    f"/repos/{{owner}}/{{repo}}/pulls/{pr_number}/comments",
    cwd=self._repo_root,
)
comments_data = json.loads(raw)

# Step 2: GraphQL -- get thread IDs and resolution status
query = """
query($owner: String!, $repo: String!, $pr: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          comments(first: 1) {
            nodes { databaseId }
          }
        }
      }
    }
  }
}
"""
# Map thread info to comments, filter resolved threads
```

### Listing Open PRs (GHAPI-02)

```python
# gh pr list returns JSON with --json flag
raw = await self._run_gh(
    "pr", "list",
    "--json", "number,title,headRefName,author,updatedAt",
    "--state", "open",
    "--limit", "100",
    cwd=self._repo_root,
)
pr_data = json.loads(raw)
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

### Self/Bot Detection (GHAPI-05)

```python
AMELIA_FOOTER = "_Amelia (automated fix)_"

def _should_skip_comment(
    self,
    comment: PRReviewComment,
    ignore_authors: list[str],
) -> bool:
    """Check if comment should be skipped."""
    # Always skip Amelia's own comments (footer match)
    if AMELIA_FOOTER in comment.body:
        return True
    # Skip configured authors (exact match)
    if comment.author in ignore_authors:
        return True
    return False
```

### Safe Git Push (GIT-01 through GIT-04)

```python
async def stage_and_commit(self, message: str) -> str:
    """Stage all changes and commit. Returns commit SHA."""
    await self._run_git("add", "-A")
    await self._run_git("commit", "-m", message)
    return await self._run_git("rev-parse", "HEAD")

async def safe_push(self, branch: str) -> str:
    """Push with pull-before-push and SHA verification. Returns pushed SHA."""
    # Guard: protected branches
    if branch in self._protected_branches:
        raise ValueError(f"Refusing to push to protected branch: {branch}")

    # Fetch remote state
    await self._run_git("fetch", "origin", branch, check=False)

    local_sha = await self._run_git("rev-parse", "HEAD")

    # Check if remote branch exists
    try:
        remote_sha = await self._run_git("rev-parse", f"origin/{branch}")
    except (ValueError, RuntimeError):
        remote_sha = None  # New branch, no remote tracking yet

    if remote_sha and remote_sha != local_sha:
        # Check if local contains remote (local is ahead)
        merge_base = await self._run_git("merge-base", local_sha, remote_sha)
        if merge_base != remote_sha:
            raise ValueError(
                f"Remote has diverged (local={local_sha[:8]}, remote={remote_sha[:8]}). "
                "Aborting -- manual intervention required."
            )

    await self._run_git("push", "origin", "HEAD")
    return local_sha
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `subprocess.run` (sync) | `asyncio.create_subprocess_exec` (async) | Project convention | All new I/O code must be async |
| `create_subprocess_shell` (string) | `create_subprocess_exec` (list) | Security best practice | Prevents shell injection; new code should use exec |
| PyGithub library | `gh` CLI subprocess | Project architecture decision | Out of scope per REQUIREMENTS.md |
| REST-only for threads | REST + GraphQL hybrid | GitHub API design | Thread resolution requires GraphQL; comment data comes from REST |

**Deprecated/outdated:**
- `position` parameter on review comment creation endpoint (replaced by `line` + `side`)
- The existing `_run_git_command` in `git_utils.py` uses `create_subprocess_shell` -- new operations should use `create_subprocess_exec` for safety, but can coexist

## Open Questions

1. **GraphQL Pagination for Review Threads**
   - What we know: `reviewThreads(first: 100)` handles most PRs. Very large PRs with 100+ threads would need cursor-based pagination.
   - What's unclear: Whether any PR in practice will exceed 100 threads.
   - Recommendation: Start with `first: 100`, add pagination if needed. Log a warning if `pageInfo.hasNextPage` is true.

2. **`_run_git_command` Refactor vs Extension**
   - What we know: Existing `_run_git_command` uses `create_subprocess_shell`. New git operations should use `create_subprocess_exec`.
   - What's unclear: Whether to refactor existing function or add new one.
   - Recommendation: Add new `_run_git_exec` helper alongside existing one. Don't refactor -- `get_current_commit` callers shouldn't break.

3. **`ignore_authors` Field on PRAutoFixConfig**
   - What we know: Need to add `ignore_authors: list[str] = Field(default_factory=list)` to `PRAutoFixConfig`.
   - What's unclear: Database migration impact (JSONB field, nullable).
   - Recommendation: Since `PRAutoFixConfig` is stored as JSONB and defaults handle missing keys, Pydantic's default_factory should handle existing records gracefully with no migration needed.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (auto mode) |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/unit/ -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GHAPI-01 | Fetch unresolved review comments | unit | `uv run pytest tests/unit/services/test_github_pr.py::test_fetch_review_comments -x` | Wave 0 |
| GHAPI-02 | List open PRs | unit | `uv run pytest tests/unit/services/test_github_pr.py::test_list_open_prs -x` | Wave 0 |
| GHAPI-03 | Resolve review thread via GraphQL | unit | `uv run pytest tests/unit/services/test_github_pr.py::test_resolve_thread -x` | Wave 0 |
| GHAPI-04 | Reply to review comment | unit | `uv run pytest tests/unit/services/test_github_pr.py::test_reply_to_comment -x` | Wave 0 |
| GHAPI-05 | Detect and skip bot/self comments | unit | `uv run pytest tests/unit/services/test_github_pr.py::test_skip_self_comments -x` | Wave 0 |
| GIT-01 | Stage and commit | unit | `uv run pytest tests/unit/tools/test_git_operations.py::test_stage_and_commit -x` | Wave 0 |
| GIT-02 | Push to origin | unit | `uv run pytest tests/unit/tools/test_git_operations.py::test_push -x` | Wave 0 |
| GIT-03 | Pull-before-push / abort on divergence | unit | `uv run pytest tests/unit/tools/test_git_operations.py::test_divergence_abort -x` | Wave 0 |
| GIT-04 | SHA verification before push | unit | `uv run pytest tests/unit/tools/test_git_operations.py::test_sha_verification -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/services/__init__.py` -- new package
- [ ] `tests/unit/services/test_github_pr.py` -- covers GHAPI-01 through GHAPI-05
- [ ] `tests/unit/tools/test_git_operations.py` -- covers GIT-01 through GIT-04
- [ ] `amelia/services/__init__.py` -- new package

## Sources

### Primary (HIGH confidence)
- `amelia/server/routes/github.py` -- existing `gh` CLI async subprocess pattern with `create_subprocess_exec`
- `amelia/trackers/github.py` -- existing sync `gh` CLI pattern (GithubTracker)
- `amelia/tools/git_utils.py` -- existing async git utility with `_run_git_command`
- `amelia/core/types.py` -- PRReviewComment, PRSummary, PRAutoFixConfig models
- `amelia/server/events/bus.py` -- EventBus for push failure events
- `amelia/server/models/events.py` -- EventType enum (will need new event types in later phase)

### Secondary (MEDIUM confidence)
- [GitHub REST API: Pull Request Review Comments](https://docs.github.com/en/rest/pulls/comments) -- endpoint paths, parameters
- [GitHub GraphQL Mutations: resolveReviewThread](https://docs.github.com/en/graphql/reference/mutations) -- mutation structure, input type
- [GitHub Community Discussion: resolveReviewThread permissions](https://github.com/orgs/community/discussions/44650) -- permissions requirements
- [Gist: resolve-pr-comments.md](https://gist.github.com/kieranklaassen/0c91cfaaf99ab600e79ba898918cea8a) -- GraphQL query/mutation examples for thread resolution

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries/tools already in use in the codebase
- Architecture: HIGH -- clear patterns from existing code (github.py routes, git_utils.py)
- Pitfalls: HIGH -- verified via GitHub API docs and existing codebase patterns
- GitHub API specifics: MEDIUM -- REST endpoints verified, GraphQL thread ID mapping verified via multiple sources

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable domain -- gh CLI and GitHub API are mature)
