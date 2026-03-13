# Domain Pitfalls: PR Auto-Fix Automation

**Domain:** Autonomous PR review comment resolution
**Researched:** 2026-03-13
**Confidence:** HIGH (verified against GitHub docs, community issues, and existing codebase patterns)

## Critical Pitfalls

Mistakes that cause runaway behavior, data loss, or require architectural rework.

---

### Pitfall 1: Infinite Fix Loops

**What goes wrong:** The bot pushes a fix, which triggers new review comments (from CI, linters, or the reviewer re-reviewing), which triggers another fix cycle, ad infinitum. Alternatively, the bot's own fix introduces a new issue that it then tries to fix, creating a self-reinforcing loop.

**Why it happens:**
- No hard ceiling on fix iterations per thread or per PR.
- The bot processes its own push events as "new activity" and re-polls comments.
- A fix for comment A breaks something that produces comment B, which when fixed breaks A again.
- GitHub Actions workflows triggered by the bot's push (if using a PAT instead of GITHUB_TOKEN) can post new review comments that re-enter the loop.

**Consequences:** Hundreds of commits on a PR. GitHub API rate limits exhausted. Reviewer inbox flooded with notifications. Potential secondary rate limit ban (GitHub enforces max 80 content-creation requests/minute, 500/hour).

**Prevention:**
1. **Hard max iterations per thread** -- configurable, default 3. After N attempts to fix a single thread, mark it as "needs human" and stop.
2. **Hard max iterations per PR per polling cycle** -- e.g., 5 total fix rounds before backing off.
3. **Cooldown after push** -- after pushing fixes, skip the next polling cycle for that PR (the reviewer needs time to re-review anyway).
4. **Track fix lineage** -- store which comment IDs triggered which commits. If a commit created to fix comment X produces a new comment that leads back to fixing X again, break the cycle.
5. **Bot self-detection** -- the poller must skip comments authored by Amelia's own GitHub identity. This is listed in PROJECT.md requirements but is critical-path -- if it fails, loops are guaranteed.

**Detection (warning signs):**
- More than 3 commits in rapid succession on a single PR from the bot.
- The same file being modified in consecutive fix cycles.
- Rate limit headers showing rapid consumption.

**Phase mapping:** Must be implemented in the core polling/orchestration phase, before any fix logic ships. This is a phase-1 gate -- do not ship fix capability without loop guards.

---

### Pitfall 2: GitHub API Rate Limit Exhaustion

**What goes wrong:** Polling multiple PRs at a configurable interval burns through the 5,000 requests/hour primary rate limit or 900 points/minute secondary limit. GraphQL mutations cost 5 points each (vs 1 for queries), so resolving threads is 5x more expensive than reading them.

**Why it happens:**
- Polling interval set too aggressively (e.g., every 30 seconds across 10 PRs).
- Each poll requires multiple API calls: list PRs, fetch comments per PR, fetch thread state, check resolution status.
- The `gh` CLI does not expose rate limit headers to the caller -- it makes the HTTP request and returns stdout. There is no built-in retry/backoff in `gh api` for secondary rate limits (confirmed via gh CLI issue tracker).
- GraphQL has a separate point-based rate limit (5,000 points/hour) where mutations cost 5 points and queries cost 1 point minimum plus complexity cost.

**Consequences:** All GitHub API calls fail for the remainder of the rate limit window (up to 1 hour). This affects not just PR auto-fix but any other Amelia feature using `gh` (issue fetching, etc.). Secondary rate limit violations return 403 with Retry-After header and can escalate to temporary IP blocks.

**Prevention:**
1. **Parse rate limit state from `gh` output** -- use `gh api rate_limit` periodically to check remaining quota, or parse stderr from failed calls for 403/rate-limit indicators.
2. **Budget-based polling** -- calculate API calls per poll cycle, multiply by number of monitored PRs, and ensure the total stays well under limits. Example: 10 PRs * 4 calls/PR * 60 polls/hour = 2,400 requests/hour (ok for primary, but tight).
3. **Adaptive backoff** -- if remaining quota drops below 20%, double the polling interval. If it drops below 5%, pause polling entirely until reset.
4. **Batch GraphQL queries** -- fetch comments for multiple PRs in a single GraphQL query instead of one REST call per PR. A single GraphQL request can query multiple PR nodes.
5. **Cache aggressively** -- store the last-seen comment timestamp/ID per PR. Only fetch comments newer than the last seen.

**Detection:** Log rate limit remaining after each `gh` call. Alert when below 500 remaining.

**Phase mapping:** Rate limit awareness must be in the polling service from day one. The existing `WorktreeHealthChecker` pattern does not handle rate limits -- the PR poller needs this as a new concern on top of the health-check lifecycle pattern.

---

### Pitfall 3: Race Conditions with Concurrent Pushes

**What goes wrong:** While Amelia is applying fixes and preparing to push, the human developer (or another bot) pushes to the same branch. Amelia's push either fails (non-fast-forward) or succeeds and overwrites the human's changes. Alternatively, two polling cycles overlap and both try to fix the same PR simultaneously.

**Why it happens:**
- The fix workflow takes minutes (LLM calls, code generation, testing). The branch state can change during this window.
- No mutex on "one fix workflow per PR" -- two polling triggers could start concurrently.
- `git push` from a worktree that is behind the remote silently fails or requires force-push.
- Force-push overwrites the human's work and invalidates their review comments (GitHub marks all previous reviews as "outdated" on force-push).

**Consequences:** Lost human commits. Corrupted PR state. Reviewer confusion when their comments reference code that no longer exists. Trust destruction -- a bot that overwrites human work will be immediately disabled.

**Prevention:**
1. **Mutex per PR** -- the project already requires "one auto-fix workflow per PR at a time (queue if in progress)." Implement this as an asyncio lock or semaphore keyed by PR number, not just a boolean flag.
2. **Pull before push** -- always `git pull --rebase` before pushing. If rebase fails (conflict), abort the fix and report the conflict rather than force-pushing.
3. **Never force-push** -- the bot must never use `git push --force`. If the push fails, fetch, rebase, and retry once. If it fails again, back off and let the human resolve.
4. **Check head SHA before pushing** -- fetch the PR's head SHA via API before pushing. If it differs from the local HEAD's parent, someone else pushed. Abort and re-poll.
5. **Worktree isolation** -- use a dedicated git worktree per PR (the existing worktree pattern supports this). This prevents branch-switching conflicts but does not prevent remote push races.

**Detection:**
- Non-zero exit code from `git push`.
- PR head SHA mismatch between local and remote.
- Merge conflicts during rebase.

**Phase mapping:** The per-PR mutex must be in the orchestration layer from the start. The pull-before-push and SHA-check patterns go in the git operations module, which should be built before the fix pipeline can push.

---

### Pitfall 4: Review Thread Resolution Edge Cases

**What goes wrong:** The bot resolves a thread that it did not actually fix, or fails to resolve a thread it did fix. Threads attached to force-pushed commits become "orphaned" -- they reference code lines that no longer exist but remain unresolved in the GitHub UI.

**Why it happens:**
- GitHub's `resolveReviewThread` GraphQL mutation requires the thread ID, not the comment ID. Thread IDs must be fetched separately -- they are not in the REST API at all.
- A single review thread can contain multiple comments (a conversation). The bot might fix the original comment but not address a follow-up in the same thread.
- After a rebase or force-push, review comments become "outdated" in GitHub's UI but the threads remain unresolved. The bot may not find the relevant code to fix because the diff context has changed.
- The `PullRequestReviewThread` GraphQL connection has documented pagination bugs -- it may return incomplete comment counts or miss replies.
- Permissions: resolving threads requires Contents read+write permission on the repository. A misconfigured token silently fails or returns a generic error.

**Consequences:** False resolution -- human reviewer sees thread marked resolved but the issue persists. Missed resolution -- bot fixed the code but the thread stays open, confusing the reviewer. Orphaned threads accumulate on long-lived PRs.

**Prevention:**
1. **Only resolve threads where the fix was verified** -- after pushing the fix, do a lightweight check (e.g., the file was modified in the fix commit, the relevant line range was touched). Do not resolve threads purely based on "the LLM said it fixed it."
2. **Fetch full thread conversations** -- paginate through all comments in a thread before deciding if the fix addresses the complete conversation, not just the first comment.
3. **Handle outdated/orphaned threads explicitly** -- if a thread references a commit SHA that is no longer in the PR's history, classify it separately. Either skip it or attempt to map it to the current code.
4. **Validate GraphQL permissions early** -- on startup, make a dry-run GraphQL query to verify the token has the required scopes. Fail fast with a clear error message.
5. **Reply before resolving** -- post a comment explaining what was fixed before resolving the thread. This creates an audit trail and lets the reviewer quickly verify.

**Detection:**
- Thread resolution mutation returns an error.
- Resolved thread count does not match expected count after a fix cycle.
- Comments reference file paths or line numbers not present in the current PR diff.

**Phase mapping:** Thread resolution is a later phase (after basic fix-and-push works). But the data model for tracking thread state (thread ID, comment IDs, resolution status, orphaned flag) should be designed in the first phase.

---

## Moderate Pitfalls

### Pitfall 5: Comment Deduplication Failures

**What goes wrong:** The bot processes the same review comment multiple times, creating duplicate fix commits. Or the bot misses a comment because it was already "seen" in a previous cycle but was not actually addressed (e.g., the fix failed silently).

**Why it happens:**
- Comment IDs are stable, but the bot's "processed" state is in-memory and lost on restart.
- A comment can be edited after processing -- the edit changes the meaning but the ID stays the same.
- GitHub does not provide a "last modified" timestamp on review comments via the REST API fields commonly fetched.
- Multiple comments from different reviewers may describe the same issue. Semantic deduplication is hard.

**Prevention:**
1. **Persist processed comment state** -- store processed comment IDs with their content hash (not just the ID). On restart, reload state from disk/database.
2. **Content hash for edit detection** -- hash the comment body when processing. On re-poll, if the same ID has a different hash, treat it as a new comment.
3. **Idempotent fix operations** -- design fixes so that applying the same fix twice is harmless (the second application is a no-op because the code already matches the desired state).
4. **State machine per comment** -- track states: `new -> classified -> fixing -> fixed -> resolved` and `new -> classified -> skipped`. Never regress state without explicit reason.

**Detection:**
- Two consecutive commits that modify the same file in the same way.
- A comment in "fixed" state whose thread is still unresolved.

**Phase mapping:** The deduplication data model and persistence layer should be designed alongside the polling service. In-memory-only tracking is acceptable for MVP but must be flagged as a known limitation.

---

### Pitfall 6: Branch Context Mismatch

**What goes wrong:** The Developer agent operates on the wrong branch (e.g., main instead of the PR's head branch), or the worktree is checked out to a stale commit that does not reflect the latest PR state.

**Why it happens:**
- The PR's head branch name must be fetched from the GitHub API and checked out locally. If the local repo does not have the remote branch, `git checkout` fails.
- Worktrees created for a PR may not be updated when new commits are pushed to the PR branch by the human.
- The Developer agent's context (file contents, diff) is based on the local worktree state, which may not match what the reviewer saw when they left the comment.
- Renamed or deleted branches (e.g., after a squash-merge of a dependency PR) leave dangling worktrees.

**Prevention:**
1. **Always fetch before checkout** -- `git fetch origin <branch>` before `git checkout <branch>` in the worktree.
2. **Verify HEAD matches PR head** -- after checkout, compare local HEAD SHA with the PR's `headRefOid` from the GraphQL API. If they differ, reset to the remote state.
3. **Include diff context in LLM prompt** -- pass the specific diff hunk that the review comment references, not just the file path. This anchors the LLM to the right code even if the local state is slightly off.
4. **Clean up stale worktrees** -- the existing `WorktreeHealthChecker` handles deleted directories. Extend it to also detect worktrees for closed/merged PRs and clean them up.

**Detection:**
- `git status` showing unexpected uncommitted changes in the worktree.
- Fix commits that do not apply to the lines referenced in the review comment.
- PR head SHA mismatch warnings.

**Phase mapping:** Branch checkout and worktree management should be implemented and tested before the Developer agent is connected to PR context. This is infrastructure that the fix pipeline depends on.

---

### Pitfall 7: LLM Comment Classification Errors

**What goes wrong:** The LLM misclassifies a discussion comment as actionable (wasting a fix cycle) or misclassifies an actionable comment as discussion (leaving a real issue unfixed). At the "exemplary" aggressiveness level, the LLM treats every comment as actionable and makes unnecessary changes.

**Why it happens:**
- Review comments are ambiguous -- "Maybe we should use X here?" could be a suggestion or a question.
- The aggressiveness spectrum is subjective and hard to calibrate consistently.
- The LLM lacks repository context (coding standards, team conventions) needed to judge severity.
- Bot-generated comments from CI tools, linters, or other bots look like human comments but should not trigger fixes (or should be handled differently).

**Prevention:**
1. **Structured classification output** -- require the LLM to output a structured decision (actionable/discussion/question/bot) with a confidence score. Only act on high-confidence classifications.
2. **Bot detection heuristics** -- check comment author against known bot patterns (`[bot]` suffix, app installations, specific usernames). The PROJECT.md already requires bot detection.
3. **Dry-run mode** -- before the bot starts fixing, log what it would do for each comment. Let the team validate the classification accuracy on real comments before enabling auto-fix.
4. **Classification review in dashboard** -- show the classification decision in the dashboard UI so humans can override incorrect classifications.

**Detection:**
- Fix commits that make no meaningful changes (LLM acted on a non-actionable comment).
- Comments classified as "discussion" that the reviewer later explicitly asks to be addressed.

**Phase mapping:** LLM classification should be built and validated before the fix pipeline can act on it. This is a prerequisite for the aggressiveness spectrum feature.

---

### Pitfall 8: Notification Storm

**What goes wrong:** Every push, comment, and thread resolution generates GitHub notifications for all PR participants. A fix cycle that touches 5 threads generates 5+ notifications. Rapid polling amplifies this.

**Why it happens:**
- Each `resolveReviewThread` mutation notifies thread participants.
- Each commit push notifies PR subscribers.
- Each bot reply comment notifies the thread.
- A single fix cycle can generate 15+ notifications (5 replies + 5 resolutions + push notification + CI status updates).

**Prevention:**
1. **Batch fixes into a single commit** -- fix all actionable comments in one commit, push once. Do not commit-per-comment.
2. **Single summary comment** -- post one PR comment summarizing all fixes rather than replying to each thread individually. Then resolve threads without individual replies.
3. **Configurable verbosity** -- let teams choose between "reply to each thread" (detailed) and "single summary" (quiet) modes.
4. **Rate-limit bot actions** -- space out thread resolutions to avoid a burst of notifications.

**Detection:**
- Reviewer complaints about notification volume.
- Multiple push events within a short window on the same PR.

**Phase mapping:** Batching strategy should be decided during architecture design. The "fix all comments in one commit" pattern must be the default from the first working version.

---

## Minor Pitfalls

### Pitfall 9: `gh` CLI Subprocess Error Handling

**What goes wrong:** The `gh` subprocess fails silently or returns partial output. The bot proceeds with incomplete data.

**Why it happens:**
- `gh` returns exit code 0 for some error conditions (e.g., empty result sets).
- JSON parsing succeeds on partial output if the truncation happens at a valid JSON boundary.
- Network timeouts produce stderr output but the existing `GithubTracker` pattern uses `check=True` which only catches non-zero exit codes.
- `gh api graphql` returns 200 with an `errors` array in the JSON body for GraphQL errors -- the HTTP status is still success.

**Prevention:**
1. **Always validate GraphQL response structure** -- check for `errors` key in the response JSON, not just the exit code.
2. **Validate expected fields** -- after parsing JSON, verify that required fields are present before proceeding.
3. **Timeout subprocess calls** -- add `timeout` parameter to `subprocess.run()` calls. The existing `GithubTracker` does not set timeouts.
4. **Structured error types** -- create specific exception types for rate-limit errors, auth errors, and data errors so the caller can handle each appropriately.

**Phase mapping:** Build a robust `gh` CLI wrapper early (before the polling service). The existing `GithubTracker` pattern is too simple for the volume and variety of API calls PR auto-fix requires.

---

### Pitfall 10: Stale Comment Context After Force-Push

**What goes wrong:** A reviewer leaves a comment on line 42 of `foo.py`. Before the bot processes it, someone force-pushes the branch. Line 42 now contains different code. The bot's fix targets the wrong code.

**Prevention:**
1. **Fetch the original diff hunk** -- GitHub stores the `diff_hunk` on review comments. Pass this to the LLM alongside the current file content so it can reconcile the difference.
2. **Detect position drift** -- compare the comment's `original_line` and `line` fields. If they differ, the code has shifted. Use `path` + `diff_hunk` to locate the relevant code in the current file.
3. **Skip outdated comments** -- if the comment is marked `outdated` in GitHub's API response and no mapping to current code can be made, skip it and log a warning.

**Phase mapping:** This is an edge case for the second iteration. The first version can skip outdated comments and handle them in a follow-up.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Polling service | Rate limit exhaustion (#2) | Build rate-limit awareness into poller from day one |
| Polling service | Infinite loop (#1) | Hard iteration caps before any fix logic ships |
| Git operations (push/pull) | Race conditions (#3) | Per-PR mutex, pull-before-push, never force-push |
| Git operations (worktree) | Branch context mismatch (#6) | Fetch-before-checkout, SHA verification |
| Comment processing | Deduplication failure (#5) | Persistent state with content hashing |
| Comment processing | Classification errors (#7) | Structured output, bot detection, dry-run mode |
| Thread resolution | Resolution edge cases (#4) | Full thread pagination, verify-before-resolve |
| Thread resolution | Notification storm (#8) | Batch fixes into single commit, summary comment |
| `gh` CLI integration | Subprocess errors (#9) | Robust wrapper with GraphQL error checking |
| Fix application | Stale context (#10) | Use diff_hunk, handle outdated comments |

## Sources

- [GitHub REST API Rate Limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) -- PRIMARY/SECONDARY limits, headers, GraphQL point costs
- [GitHub GraphQL Mutations](https://docs.github.com/en/graphql/reference/mutations) -- resolveReviewThread mutation reference
- [GitHub Community: Workflow Infinite Loop](https://github.com/orgs/community/discussions/26970) -- GITHUB_TOKEN vs PAT loop behavior
- [GitHub Community: resolveReviewThread Permissions](https://github.com/orgs/community/discussions/44650) -- required Contents read+write scope
- [GitHub Community: GraphQL Review Thread Bugs](https://github.com/orgs/community/discussions/24666) -- incomplete comment retrieval in GraphQL
- [GitHub Community: Force Push Impact on PRs](https://github.com/orgs/community/discussions/142466) -- outdated reviews after force-push
- [gh CLI Rate Limit Discussion](https://github.com/cli/cli/discussions/7754) -- gh CLI does not handle rate limits automatically
- [gh CLI GraphQL Rate Limit Issue](https://github.com/cli/cli/issues/8321) -- GraphQL rate limit exceeded errors
- [GitHub Actions Concurrency Control](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency) -- concurrency groups pattern
- [Avoiding Workflow Loops on Protected Branches](https://blog.shounakmulay.dev/avoid-workflow-loops-on-github-actions-when-committing-to-a-protected-branch) -- practical loop prevention
- [Bulk Resolve GitHub PR Comments via API](https://nesin.io/blog/bulk-resolve-github-pr-comments-api) -- GraphQL thread resolution pattern
- [Reviewdog Issue #1720](https://github.com/reviewdog/reviewdog/issues/1720) -- thread resolution marking challenges
