# Phase 5: Thread Resolution & Composition - Research

**Researched:** 2026-03-14
**Domain:** LangGraph pipeline node, GitHub PR API (reply + resolve), async Python
**Confidence:** HIGH

## Summary

Phase 5 adds a single `reply_resolve_node` to the existing PR auto-fix LangGraph pipeline, wired after `commit_push_node`. This node iterates over `group_results` from the state, maps each result's `comment_ids` back to the original `PRReviewComment` objects, and performs two GitHub API operations per comment: (1) reply with a status-specific message, (2) optionally resolve the thread. The existing `GitHubPRService` already implements both `reply_to_comment()` and `resolve_thread()` -- no new API methods are needed.

PIPE-08 (review pipeline composition) is explicitly deferred per user decision. The only code deliverables are: the new node function, a state extension for tracking resolution results, a config flag for no_changes resolve behavior, graph wiring update, and tests.

**Primary recommendation:** Implement `reply_resolve_node` as a single async function following the established node pattern (`async def reply_resolve_node(state, config) -> dict[str, Any]`), with per-comment error isolation matching the pattern established by `develop_node`.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Per-comment replies -- each addressed comment gets its own reply, not grouped summaries
- Replies must `@mention` the comment author so they get a GitHub notification
- Fix replies include the commit SHA as a clickable reference (e.g., `@author Fixed: [what_changed]. Commit: abc1234`)
- Unfixable replies include a specific reason why Amelia couldn't fix it (not a generic message)
- Reply format follows Phase 2 convention: concise & factual tone, footer signature `---\n_Amelia (automated fix)_`
- No_changes replies explain that Amelia reviewed the comment but no code changes were needed
- Single `reply_resolve_node` added after `commit_push_node` in the LangGraph graph
- New graph flow: classify -> develop -> commit_push -> reply_resolve -> END
- Single pass over all comments, branching on GroupFixResult status: fixed/failed/no_changes
- Node always runs, even when commit_push had zero changes (all no_changes groups)
- Always resolve threads on successful fix (ignore `auto_resolve` config flag)
- Unfixable comment threads are left open (signals human attention needed)
- No_changes thread resolution controlled by a new config flag (default: true)
- Comments with no `node_id`: post reply but skip resolve, log a warning
- Resolve failures are non-fatal: log the error, continue with remaining threads
- Pipeline status is `completed` as long as it ran to the end
- No new status enum values -- consumers check `group_results` for mixed outcomes
- Reply_resolve node processes all comments regardless of mixed outcomes

### Claude's Discretion
- Exact reply message templates (wording within the decided format)
- How to map comment_ids in GroupFixResult back to original PRReviewComment objects for reply context
- Error handling structure within reply_resolve_node
- Config field name and placement for no_changes resolve behavior
- Whether to use asyncio.gather for concurrent replies or sequential processing

### Deferred Ideas (OUT OF SCOPE)
- PIPE-08: Review pipeline composition -- deferred until PR creation capability is built
- Concurrent reply posting -- Claude's discretion for v1; optimize later if needed

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PIPE-06 | Pipeline replies to each fixed comment and resolves the thread | reply_resolve_node handles fixed status: builds reply with commit SHA, calls reply_to_comment(), calls resolve_thread() |
| PIPE-07 | Pipeline handles partial fixes -- replies to unfixable comments explaining why, marks as needing human attention | reply_resolve_node handles failed status: builds reply with error reason, posts reply, leaves thread open |
| PIPE-08 | Existing review pipeline can optionally invoke PR_AUTO_FIX when PR context is available | **DEFERRED** per user decision -- no implementation in this phase |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langgraph | (existing) | Pipeline graph with nodes and edges | Already used for pr_auto_fix pipeline |
| pydantic | (existing) | State models, config models | Project convention -- frozen models with ConfigDict |
| loguru | (existing) | Structured logging | Project convention -- logger with kwargs |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| langchain-core | (existing) | RunnableConfig type | Node function signatures |
| pytest / pytest-asyncio | (existing) | Testing async node functions | All node tests |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Sequential reply posting | asyncio.gather for concurrency | Simpler debugging vs. lower latency; user deferred concurrency |

**Installation:** No new dependencies required. All libraries already in project.

## Architecture Patterns

### Recommended Project Structure
```
amelia/pipelines/pr_auto_fix/
    nodes.py          # Add reply_resolve_node function here
    state.py          # Add ResolutionResult model, extend PRAutoFixState
    graph.py          # Update edge: commit_push -> reply_resolve -> END
amelia/core/
    types.py          # Add resolve_no_changes config field to PRAutoFixConfig
tests/unit/pipelines/pr_auto_fix/
    test_nodes.py     # Add TestReplyResolveNode class
```

### Pattern 1: Node Function Signature
**What:** All pipeline nodes follow the same async function signature
**When to use:** Always -- this is the established pattern for all LangGraph nodes in this project
**Example:**
```python
# Source: amelia/pipelines/pr_auto_fix/nodes.py (existing pattern)
async def reply_resolve_node(
    state: PRAutoFixState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Reply to comments and resolve threads based on fix results."""
    ...
```

### Pattern 2: Per-Item Error Isolation
**What:** Catch exceptions per comment, log, continue with remaining comments
**When to use:** When processing multiple independent items where one failure should not block others
**Example:**
```python
# Source: develop_node pattern in nodes.py
for comment in comments_to_process:
    try:
        await github_service.reply_to_comment(...)
        await github_service.resolve_thread(...)
    except Exception as e:
        logger.error("Reply/resolve failed", comment_id=comment.id, error=str(e))
        # Record failure, continue with next comment
```

### Pattern 3: Config Extraction
**What:** Use `extract_config_params(config)` to get event_bus, workflow_id, profile
**When to use:** Every node function that needs profile or workflow context
**Example:**
```python
_event_bus, _workflow_id, profile = extract_config_params(config or {})
```

### Pattern 4: Comment ID to Object Mapping
**What:** Build lookup dict from state.comments for O(1) access by ID
**When to use:** When GroupFixResult.comment_ids need to be resolved to full PRReviewComment objects
**Example:**
```python
comments_by_id: dict[int, PRReviewComment] = {c.id: c for c in state.comments}
for result in state.group_results:
    for cid in result.comment_ids:
        comment = comments_by_id.get(cid)
        if comment:
            # Build reply using comment.author, comment.body, etc.
```

### Anti-Patterns to Avoid
- **Grouping replies:** User explicitly decided per-comment replies, not grouped summaries per file
- **Using auto_resolve config flag for fixed comments:** User decided always resolve on fix, regardless of config
- **Fatal resolve failures:** Resolve errors must be caught and logged, not propagated -- fix is already pushed
- **Adding new status enum values:** User decided against this -- consumers check group_results directly

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Reply posting | Custom HTTP/GraphQL call | `GitHubPRService.reply_to_comment()` | Already handles Amelia footer, parent ID for nested replies |
| Thread resolution | Custom GraphQL mutation | `GitHubPRService.resolve_thread()` | Already handles the resolveReviewThread mutation |
| Footer signature | Manual string concatenation | `reply_to_comment()` appends `AMELIA_FOOTER` automatically | Don't duplicate footer -- method already appends `---\n_Amelia (automated fix)_` |
| Config extraction | Manual dict access | `extract_config_params(config)` | Handles missing keys, consistent error messages |

**Key insight:** The `reply_to_comment()` method already appends the Amelia footer. The node only builds the body text BEFORE the footer. Do NOT include the footer in the message body passed to the method.

## Common Pitfalls

### Pitfall 1: Double Footer
**What goes wrong:** Node includes `---\n_Amelia (automated fix)_` in the body, then `reply_to_comment()` appends it again
**Why it happens:** Not reading the existing service method which already adds the footer
**How to avoid:** Only pass the message body (without footer) to `reply_to_comment()`. The method concatenates `f"{body}\n\n---\n{AMELIA_FOOTER}"`
**Warning signs:** Replies showing two footer separators

### Pitfall 2: Wrong Comment ID for Reply
**What goes wrong:** Using `comment.id` directly when the comment is a reply (has `in_reply_to_id`)
**Why it happens:** GitHub requires the top-level comment ID for the reply endpoint
**How to avoid:** `reply_to_comment()` already handles this -- it uses `in_reply_to_id` when available. Pass both `comment_id=comment.id` and `in_reply_to_id=comment.in_reply_to_id`
**Warning signs:** 404 errors from GitHub API

### Pitfall 3: Missing node_id for Resolve
**What goes wrong:** Calling `resolve_thread()` with None node_id
**Why it happens:** Some comments may not have a GraphQL node_id (e.g., if GraphQL fetch failed or comment structure changed)
**How to avoid:** Check `comment.node_id is not None` before calling resolve. Log warning if missing. The CONTEXT.md explicitly requires this check.
**Warning signs:** GraphQL errors about null threadId

### Pitfall 4: Resolve Thread vs Comment node_id
**What goes wrong:** Using `comment.node_id` (the comment's GraphQL node ID) instead of `comment.thread_id` for thread resolution
**Why it happens:** Confusion between node_id and thread_id fields on PRReviewComment
**How to avoid:** `resolve_thread()` expects a thread node ID. The `PRReviewComment.thread_id` field is the review thread ID. However, looking at the existing `fetch_review_comments` code, `thread_id` stores the thread's `id` from GraphQL, which IS the thread node ID. Use `comment.thread_id` for resolve, NOT `comment.node_id`.
**Warning signs:** GraphQL type mismatch errors

### Pitfall 5: Frozen State Mutation
**What goes wrong:** Trying to mutate PRAutoFixState directly
**Why it happens:** Forgetting state has `frozen=True`
**How to avoid:** Return dict from node function -- LangGraph handles state updates
**Warning signs:** Pydantic ValidationError about frozen fields

### Pitfall 6: GitHubPRService Instantiation
**What goes wrong:** Creating GitHubPRService without repo_root
**Why it happens:** Service needs a repo_root for `gh` CLI cwd
**How to avoid:** Get repo_root from profile: `GitHubPRService(profile.repo_root)`
**Warning signs:** gh CLI errors about not being in a git repo

## Code Examples

### Reply Body Construction (No Footer)
```python
# Source: CONTEXT.md decisions + github_pr.py analysis
def _build_reply_body(
    status: GroupFixStatus,
    author: str,
    commit_sha: str | None,
    error: str | None,
) -> str:
    """Build reply body WITHOUT footer (reply_to_comment adds it)."""
    if status == GroupFixStatus.FIXED:
        short_sha = commit_sha[:7] if commit_sha else "unknown"
        return f"@{author} Fixed in {short_sha}."
    elif status == GroupFixStatus.FAILED:
        reason = error or "Unknown error"
        return f"@{author} Could not auto-fix: {reason}. Flagging for human review."
    else:  # NO_CHANGES
        return f"@{author} Reviewed this comment -- no code changes needed."
```

### Node Structure
```python
# Source: existing node patterns in nodes.py
async def reply_resolve_node(
    state: PRAutoFixState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    _event_bus, _workflow_id, profile = extract_config_params(config or {})
    github_service = GitHubPRService(profile.repo_root)

    comments_by_id = {c.id: c for c in state.comments}
    resolution_results: list[ResolutionResult] = []

    for result in state.group_results:
        for cid in result.comment_ids:
            comment = comments_by_id.get(cid)
            if not comment:
                continue

            body = _build_reply_body(result.status, comment.author, state.commit_sha, result.error)

            # Reply
            try:
                await github_service.reply_to_comment(
                    state.pr_number, comment.id, body,
                    in_reply_to_id=comment.in_reply_to_id,
                )
            except Exception as e:
                logger.error("Reply failed", comment_id=cid, error=str(e))

            # Resolve (conditionally)
            should_resolve = (
                result.status == GroupFixStatus.FIXED
                or (result.status == GroupFixStatus.NO_CHANGES and state.autofix_config.resolve_no_changes)
            )
            if should_resolve and comment.thread_id:
                try:
                    await github_service.resolve_thread(comment.thread_id)
                except Exception as e:
                    logger.error("Resolve failed", comment_id=cid, error=str(e))
            elif should_resolve and not comment.thread_id:
                logger.warning("No thread_id for comment, skipping resolve", comment_id=cid)

    return {"status": "completed", "resolution_results": resolution_results}
```

### Graph Wiring Update
```python
# Source: amelia/pipelines/pr_auto_fix/graph.py
from amelia.pipelines.pr_auto_fix.nodes import (
    classify_node,
    commit_push_node,
    develop_node,
    reply_resolve_node,  # NEW
)

def create_pr_auto_fix_graph(checkpointer=None):
    workflow = StateGraph(PRAutoFixState)

    workflow.add_node("classify_node", classify_node)
    workflow.add_node("develop_node", develop_node)
    workflow.add_node("commit_push_node", commit_push_node)
    workflow.add_node("reply_resolve_node", reply_resolve_node)  # NEW

    workflow.set_entry_point("classify_node")
    workflow.add_edge("classify_node", "develop_node")
    workflow.add_edge("develop_node", "commit_push_node")
    workflow.add_edge("commit_push_node", "reply_resolve_node")  # CHANGED
    workflow.add_edge("reply_resolve_node", END)  # NEW

    return workflow.compile(checkpointer=checkpointer)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| commit_push -> END | commit_push -> reply_resolve -> END | This phase | Completes the feedback loop |
| No reply tracking | ResolutionResult per comment | This phase | Enables dashboard/metrics in later phases |

**No deprecated patterns to worry about** -- this is additive work on top of Phase 4's established pipeline.

## Open Questions

1. **thread_id vs node_id for resolve**
   - What we know: `PRReviewComment` has both `thread_id` (review thread ID from GraphQL) and `node_id` (comment's GraphQL node ID). `resolve_thread()` calls the `resolveReviewThread` mutation which needs a thread ID.
   - What's clear: The `fetch_review_comments` method stores `thread["id"]` (the thread's GraphQL node ID) in `thread_id`. This IS what `resolve_thread()` needs.
   - Recommendation: Use `comment.thread_id` for resolve. The naming is correct.

2. **Config field name for no_changes resolve**
   - What we know: Need a boolean flag on PRAutoFixConfig, default True
   - Recommendation: `resolve_no_changes: bool = True` -- clear, follows existing naming pattern (`auto_resolve`)

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (auto mode) |
| Config file | `pyproject.toml` |
| Quick run command | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PIPE-06 | Reply to fixed comments and resolve thread | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode::test_fixed_comment_gets_reply_and_resolve -x` | Wave 0 |
| PIPE-06 | Reply includes commit SHA | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode::test_fixed_reply_includes_commit_sha -x` | Wave 0 |
| PIPE-06 | Reply @mentions author | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode::test_reply_mentions_author -x` | Wave 0 |
| PIPE-07 | Unfixable comment gets reply with reason, thread left open | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode::test_failed_comment_reply_no_resolve -x` | Wave 0 |
| PIPE-07 | No_changes comment gets reply, resolve gated by config | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode::test_no_changes_resolve_config_gated -x` | Wave 0 |
| PIPE-06 | Missing thread_id logs warning, skips resolve | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode::test_missing_thread_id_skips_resolve -x` | Wave 0 |
| PIPE-06 | Resolve failure is non-fatal | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode::test_resolve_failure_nonfatal -x` | Wave 0 |
| PIPE-06 | Graph wiring: commit_push -> reply_resolve -> END | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode::test_graph_includes_reply_resolve -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/pipelines/pr_auto_fix/ -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/pipelines/pr_auto_fix/test_nodes.py::TestReplyResolveNode` -- new test class covering PIPE-06, PIPE-07
- No framework install needed -- pytest-asyncio already configured
- No new fixtures needed -- existing `_make_comment`, `_make_state`, `_make_config`, `_make_profile` helpers cover the needs. May need to extend `_make_state` to accept `commit_sha` and `group_results` defaults.

## Sources

### Primary (HIGH confidence)
- `amelia/pipelines/pr_auto_fix/nodes.py` -- existing node patterns (classify_node, develop_node, commit_push_node)
- `amelia/pipelines/pr_auto_fix/state.py` -- PRAutoFixState, GroupFixResult, GroupFixStatus
- `amelia/pipelines/pr_auto_fix/graph.py` -- current graph wiring
- `amelia/services/github_pr.py` -- reply_to_comment(), resolve_thread(), AMELIA_FOOTER
- `amelia/core/types.py` -- PRReviewComment fields (author, node_id, thread_id, in_reply_to_id), PRAutoFixConfig
- `amelia/pipelines/utils.py` -- extract_config_params pattern
- `tests/unit/pipelines/pr_auto_fix/test_nodes.py` -- existing test patterns and fixtures

### Secondary (MEDIUM confidence)
- `.planning/phases/05-thread-resolution-composition/05-CONTEXT.md` -- all locked decisions and code context

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, fully established patterns
- Architecture: HIGH -- single new node following exact existing pattern, code reviewed directly
- Pitfalls: HIGH -- identified from direct code reading of reply_to_comment() and resolve_thread() implementations

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable -- internal codebase patterns, no external API changes)
