# Phase 5: Thread Resolution & Composition - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Complete the feedback loop after fixes are pushed: reply to each addressed comment explaining what changed, resolve fixed threads, and gracefully handle comments that couldn't be fixed. Add a new `reply_resolve_node` to the PR auto-fix LangGraph pipeline after `commit_push_node`. Review pipeline composition (PIPE-08) is deferred — no PR creation capability exists yet.

</domain>

<decisions>
## Implementation Decisions

### Reply content strategy
- Per-comment replies — each addressed comment gets its own reply, not grouped summaries
- Replies must `@mention` the comment author so they get a GitHub notification
- Fix replies include the commit SHA as a clickable reference (e.g., `@author Fixed: [what changed]. Commit: abc1234`)
- Unfixable replies include a specific reason why Amelia couldn't fix it (not a generic message)
- Reply format follows Phase 2 convention: concise & factual tone, footer signature `---\n_Amelia (automated fix)_`
- No_changes replies explain that Amelia reviewed the comment but no code changes were needed

### Node design
- Single `reply_resolve_node` added after `commit_push_node` in the LangGraph graph
- New graph flow: classify → develop → commit_push → reply_resolve → END
- Single pass over all comments, branching on GroupFixResult status:
  - `fixed` → fix reply with commit SHA + resolve thread
  - `failed` → unfixable reply with specific reason + leave thread open
  - `no_changes` → explanation reply + config-gated resolve
- Node always runs, even when commit_push had zero changes (all no_changes groups)

### Resolve behavior
- Always resolve threads on successful fix (ignore `auto_resolve` config flag — user decided: always resolve on fix)
- Unfixable comment threads are left open — signals human attention needed (matches PIPE-07)
- No_changes thread resolution controlled by a new config flag (default: true) — resolve since Amelia reviewed the comment
- Comments with no `node_id` (no thread ID): post reply but skip resolve, log a warning
- Resolve failures are non-fatal: log the error, continue with remaining threads. Fix is already pushed and reply posted.

### Partial fix handling
- Pipeline status is `completed` as long as it ran to the end — `GroupFixResult` per-group statuses tell the full story
- No new status enum values — consumers check `group_results` for mixed outcomes
- Reply_resolve node processes all comments regardless of mixed fix/fail/no_changes outcomes

### Review pipeline composition (PIPE-08)
- **Deferred entirely** — no PR creation capability exists yet, so the review pipeline cannot chain into PR_AUTO_FIX
- No preparatory interface work in this phase
- Future phase will add PR creation and wire composition

### Claude's Discretion
- Exact reply message templates (wording within the decided format)
- How to map comment_ids in GroupFixResult back to original PRReviewComment objects for reply context
- Error handling structure within reply_resolve_node
- Config field name and placement for no_changes resolve behavior
- Whether to use asyncio.gather for concurrent replies or sequential processing

</decisions>

<specifics>
## Specific Ideas

- Reply format for fixed: `@{author} Fixed: {what_changed}. Commit: {short_sha}\n\n---\n_Amelia (automated fix)_`
- Reply format for unfixable: `@{author} Could not auto-fix: {specific_reason}. Flagging for human review.\n\n---\n_Amelia (automated fix)_`
- Reply format for no_changes: `@{author} Reviewed this comment — no code changes needed.\n\n---\n_Amelia (automated fix)_`
- The `reply_to_comment()` method already appends the footer, so the node only needs to build the body text before the footer

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `GitHubPRService.reply_to_comment(pr_number, comment_id, body, in_reply_to_id)`: Posts reply with Amelia footer, handles parent ID for nested replies
- `GitHubPRService.resolve_thread(thread_node_id)`: Resolves thread via GraphQL mutation
- `GroupFixResult` model (`pipelines/pr_auto_fix/state.py`): Tracks file_path, status (fixed/failed/no_changes), error message, and comment_ids per group
- `PRAutoFixState`: Has `group_results`, `comments`, `commit_sha`, `pr_number` — all needed by reply_resolve_node
- `AMELIA_FOOTER` constant in `services/github_pr.py`: Footer signature already used by `reply_to_comment()`

### Established Patterns
- Pipeline nodes are async functions taking `(state, config)` and returning `dict[str, Any]`
- `extract_config_params(config)` to get event_bus, workflow_id, profile from RunnableConfig
- Per-item error isolation: catch exceptions per comment, log, continue (matches develop_node pattern)
- Frozen Pydantic state with `model_copy(update={...})` for immutable updates

### Integration Points
- `create_pr_auto_fix_graph()` in `graph.py`: Add reply_resolve_node, update edge from commit_push → reply_resolve → END
- `PRAutoFixState` may need new fields for reply/resolve tracking (e.g., `resolution_results`)
- `PRAutoFixConfig` needs new config flag for no_changes resolve behavior
- `PRReviewComment.author` field provides the @mention target
- `PRReviewComment.node_id` provides the thread ID for resolve_thread()

</code_context>

<deferred>
## Deferred Ideas

- **PIPE-08: Review pipeline composition** — deferred until PR creation capability is built. Review pipeline cannot chain into PR_AUTO_FIX without the ability to create PRs first. Capture as future phase work.
- **Concurrent reply posting** — could use asyncio.gather for parallel replies to reduce latency. Claude's discretion for v1; optimize later if needed.

</deferred>

---

*Phase: 05-thread-resolution-composition*
*Context gathered: 2026-03-14*
