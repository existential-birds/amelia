# Phase 4: Core Fix Pipeline - Context

**Gathered:** 2026-03-13
**Status:** Ready for planning

<domain>
## Phase Boundary

A working LangGraph pipeline that takes raw PR review comments, classifies them, feeds actionable comments to the Developer agent per file group, and produces a single commit with fixes pushed to the PR's head branch. No thread resolution or replies (Phase 5), no concurrency control (Phase 6), no triggers (Phase 7).

</domain>

<decisions>
## Implementation Decisions

### Pipeline state design
- New `PRAutoFixState` extending `BasePipelineState` — clean separation from ImplementationState (which carries 15+ unused fields for architect/review/plan workflows)
- State fields beyond BasePipelineState:
  - **PR identity**: `pr_number: int`, `head_branch: str`, `repo: str`
  - **Classification results**: `classified_comments: list[CommentClassification]`, `file_groups: dict[str, list[...]]`
  - **Developer tracking**: `goal: str`, `tool_calls`, `tool_results`, `agentic_status` (reuse existing `AgenticStatus` enum), `commit_sha: str | None`
  - **Per-group results**: `group_results: list[GroupFixResult]` — tracks success/failure/no_changes per file group so commit node and Phase 5 know what happened
- Reuse existing `AgenticStatus` enum (RUNNING, COMPLETED, FAILED, MAX_TURNS) — no new status enum
- `PRAutoFixPipeline` implements `get_initial_state()` and `get_state_class()` directly — no mixin (only one pipeline uses this state)

### Developer context feeding
- One `Developer.run()` call per file group — focused context, per-group success/failure tracking
- Developer goal includes all context needed for highest-quality fixes:
  - Comment details: body, file path, line number, diff hunk
  - PR metadata: PR number, title, head branch
  - Classification reasoning: category and reason per comment (helps Developer understand intent)
  - Explicit constraints: only modify files in this group, make minimal changes, fix root causes not symptoms
- Explicit instruction in goal: fix the underlying bug/issue, not just the surface-level symptom. If a reviewer points out a test failure, fix the code that causes the failure, not just the test.
- Dedicated `developer.pr_fix.system` prompt registered in `PROMPT_DEFAULTS` — tailored for PR-fix behavior
- New `call_pr_fix_developer_node` function in the pr_auto_fix pipeline module — does not reuse `call_developer_node` from implementation pipeline

### Node flow & error handling
- Classification is a LangGraph node: classify node calls `classify_comments()` and writes results to state. Full graph flow: classify → develop → commit/push
- Develop node iterates over file groups internally (Python loop, not LangGraph conditional loop). Simpler graph topology.
- On Developer failure for one file group: mark that group as 'failed' in `group_results`, log the error, continue with remaining groups. Commit whatever was successfully fixed.
- Zero actionable comments: pipeline completes gracefully with status 'completed', empty group_results, no commit made

### Commit strategy
- Single commit for all fixes from one pipeline run (matches PIPE-04). `GitOperations.stage_and_commit()` called once after all Developer runs complete.
- Commit message body lists each addressed comment: `Addressed: [file:line] [truncated comment body]`
- Configurable message prefix (default `fix(review):`) from `PRAutoFixConfig.commit_prefix`
- No commit if no files changed on disk after all Developer runs — check git status, skip commit/push, mark group results as 'no_changes'

### Claude's Discretion
- Exact GroupFixResult model shape (status enum: fixed/failed/no_changes, error message, etc.)
- Internal helper decomposition within the develop node
- How to construct the Developer goal string (template vs f-string vs builder)
- Exact LangGraph graph construction (StateGraph, add_node, add_edge patterns)
- Whether classify node also handles pre-filtering (top-level only, iteration limits) or expects pre-filtered input

</decisions>

<specifics>
## Specific Ideas

- Pipeline registers as `"pr_auto_fix": PRAutoFixPipeline` in the `PIPELINES` dict in `registry.py`
- Follow `ReviewPipeline` pattern: class with `metadata` property and `create_graph()` method
- Developer.run() is already async generator yielding (state, event) — develop node uses same pattern as call_developer_node
- The PR-fix system prompt should emphasize: "You are fixing code based on reviewer feedback. Fix root causes, not symptoms. If a reviewer says a test fails, fix the code that causes the failure."
- Commit message example: `fix(review): address PR review comments\n\nAddressed:\n- src/utils.py:42 "This function doesn't handle None"\n- src/api/routes.py:15 "Missing auth check"`

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Pipeline` Protocol (`pipelines/base.py`): metadata, create_graph(), get_initial_state(), get_state_class() — PRAutoFixPipeline implements this
- `BasePipelineState` (`pipelines/base.py`): Common state with workflow_id, status, history, driver_session_id, agentic fields
- `Developer` agent (`agents/developer.py`): Agentic execution via `Developer.run()` async generator
- `GitOperations` (`tools/git_utils.py`): `stage_and_commit()`, `safe_push()` — ready to use
- `classify_comments()` (`services/classifier.py`): Takes raw comments + config, returns classifications
- `group_comments_by_file()` (`services/classifier.py`): Groups actionable comments by file path
- `PROMPT_DEFAULTS` (`agents/prompts/defaults.py`): Prompt registration system for new `developer.pr_fix.system` prompt
- `AgenticStatus` enum: RUNNING, COMPLETED, FAILED, MAX_TURNS — reuse for Developer tracking
- `CommentClassification`, `ClassificationOutput` (`agents/schemas/classifier.py`): Classification result models

### Established Patterns
- Pipeline Protocol + registry dict pattern for registration
- Frozen Pydantic state with `model_copy(update={...})` for immutable updates
- `extract_config_params(config)` for getting event_bus, workflow_id, profile from RunnableConfig
- Async throughout — all nodes are async functions
- `_save_token_usage()` after Developer runs for cost tracking

### Integration Points
- `PIPELINES` dict in `registry.py` needs `"pr_auto_fix": PRAutoFixPipeline` entry
- New `amelia/pipelines/pr_auto_fix/` package (pipeline.py, graph.py, nodes.py, state.py)
- `PRAutoFixConfig.commit_prefix` already exists in types.py
- `GitHubPRService.fetch_review_comments()` provides raw comment input
- Event bus for pipeline lifecycle events (Phase 9 adds specific event types)

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-core-fix-pipeline*
*Context gathered: 2026-03-13*
