# Phase 4: Core Fix Pipeline - Research

**Researched:** 2026-03-13
**Domain:** LangGraph pipeline construction, Developer agent integration, Git commit/push operations
**Confidence:** HIGH

## Summary

Phase 4 builds a new LangGraph pipeline (`pr_auto_fix`) that orchestrates the full flow: classify PR review comments, invoke the Developer agent per file group, and commit/push fixes. All building blocks exist -- the classifier service (Phase 3), Developer agent, GitOperations, and the Pipeline protocol/registry are production-ready. The work is primarily integration and wiring.

The codebase has a clear, well-established pipeline pattern: a `Pipeline` class with `metadata`, `create_graph()`, `get_initial_state()`, `get_state_class()`; a separate `graph.py` with `StateGraph` construction; and node functions as async functions accepting `(state, config)`. The new pipeline follows this pattern exactly but with its own `PRAutoFixState` (not sharing `ImplementationState`).

**Primary recommendation:** Follow the ReviewPipeline structural pattern closely (it is the simpler of the two existing pipelines). Create a new `amelia/pipelines/pr_auto_fix/` package with state.py, nodes.py, graph.py, and pipeline.py. The Developer agent requires `ImplementationState` as input to `Developer.run()`, so the develop node must construct a temporary `ImplementationState` from `PRAutoFixState` fields for each file group invocation.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- New `PRAutoFixState` extending `BasePipelineState` -- clean separation from ImplementationState
- State fields: pr_number, head_branch, repo, classified_comments, file_groups, goal, tool_calls, tool_results, agentic_status, commit_sha, group_results
- Reuse existing `AgenticStatus` enum
- One `Developer.run()` call per file group with focused context
- Developer goal includes: comment body, file path, line number, diff hunk, PR metadata, classification reasoning, explicit constraints
- Dedicated `developer.pr_fix.system` prompt in PROMPT_DEFAULTS
- New `call_pr_fix_developer_node` function -- does NOT reuse `call_developer_node`
- Classification is a LangGraph node calling `classify_comments()` + writes to state
- Full graph flow: classify -> develop -> commit/push
- Develop node iterates over file groups internally (Python loop, not LangGraph conditional loop)
- On Developer failure for one group: mark failed, log error, continue with remaining groups
- Zero actionable comments: complete gracefully, empty group_results, no commit
- Single commit for all fixes via `GitOperations.stage_and_commit()`
- Commit message body lists each addressed comment
- Configurable message prefix from `PRAutoFixConfig.commit_prefix`
- No commit if no files changed after Developer runs
- Pipeline registers as `"pr_auto_fix": PRAutoFixPipeline` in PIPELINES dict

### Claude's Discretion
- Exact GroupFixResult model shape (status enum, error message, etc.)
- Internal helper decomposition within the develop node
- How to construct the Developer goal string (template vs f-string vs builder)
- Exact LangGraph graph construction patterns
- Whether classify node also handles pre-filtering or expects pre-filtered input

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PIPE-01 | New PR_AUTO_FIX LangGraph pipeline registered in pipeline registry | Pipeline Protocol pattern + registry dict pattern fully documented; follow ReviewPipeline structure |
| PIPE-02 | Pipeline nodes: classify -> develop -> commit/push (reply/resolve is Phase 5) | LangGraph StateGraph with linear edges; graph.py pattern from review pipeline |
| PIPE-03 | Developer agent receives PR review comments with file path, line number, diff hunk, and comment body as context | Developer.run() requires ImplementationState with goal field; build goal string with all comment context |
| PIPE-04 | Pipeline commits all fixes in single commit with configurable message prefix | GitOperations.stage_and_commit() + PRAutoFixConfig.commit_prefix already exist |
| PIPE-05 | Pipeline pushes commit to PR's head branch (never main) | GitOperations.safe_push() with PROTECTED_BRANCHES guard already implemented |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langgraph | >=1.0.8 | Pipeline state machine | Already used by implementation + review pipelines |
| pydantic | (project dep) | State models, frozen immutable state | Project convention for all data structures |
| langchain-core | (project dep) | RunnableConfig type | Used by all existing nodes for config passing |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| loguru | (project dep) | Structured logging | All node functions, error handling |
| amelia.tools.git_utils.GitOperations | existing | stage_and_commit, safe_push | Commit/push node |
| amelia.services.classifier | existing | classify_comments, group_comments_by_file | Classify node |
| amelia.agents.developer.Developer | existing | Agentic code execution | Develop node |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PRAutoFixState | ImplementationState | ImplementationState carries 15+ unused fields; clean separation is decided |
| Internal Python loop for groups | LangGraph conditional edges | Simpler graph topology, decided in CONTEXT.md |

## Architecture Patterns

### Recommended Project Structure
```
amelia/pipelines/pr_auto_fix/
  __init__.py          # Package exports
  state.py             # PRAutoFixState + GroupFixResult
  nodes.py             # classify_node, develop_node, commit_push_node
  graph.py             # create_pr_auto_fix_graph()
  pipeline.py          # PRAutoFixPipeline class
```

### Pattern 1: Pipeline Protocol Implementation
**What:** Each pipeline is a class implementing the `Pipeline` Protocol with `metadata`, `create_graph()`, `get_initial_state()`, `get_state_class()`.
**When to use:** Always -- this is how all pipelines work in this codebase.
**Example:**
```python
# Source: amelia/pipelines/review/pipeline.py
class PRAutoFixPipeline(Pipeline[PRAutoFixState]):
    @property
    def metadata(self) -> PipelineMetadata:
        return PipelineMetadata(
            name="pr_auto_fix",
            display_name="PR Auto-Fix",
            description="Fix PR review comments automatically",
        )

    def create_graph(self, checkpointer=None) -> CompiledStateGraph:
        return create_pr_auto_fix_graph(checkpointer=checkpointer)

    def get_initial_state(self, **kwargs) -> PRAutoFixState:
        return PRAutoFixState(
            workflow_id=uuid.UUID(str(kwargs["workflow_id"])),
            profile_id=str(kwargs["profile_id"]),
            pr_number=int(kwargs["pr_number"]),
            head_branch=str(kwargs["head_branch"]),
            repo=str(kwargs["repo"]),
            created_at=datetime.now(UTC),
            status="pending",
        )

    def get_state_class(self) -> type[PRAutoFixState]:
        return PRAutoFixState
```

### Pattern 2: Frozen State with model_copy
**What:** All pipeline states are frozen Pydantic models. Nodes return partial dicts; LangGraph merges them. For manual updates, use `state.model_copy(update={...})`.
**When to use:** Always -- project convention.
**Example:**
```python
# Nodes return partial state dicts, not full state objects
async def classify_node(state: PRAutoFixState, config: RunnableConfig | None = None) -> dict[str, Any]:
    # ... classification logic ...
    return {
        "classified_comments": list(classifications.values()),
        "file_groups": groups,
    }
```

### Pattern 3: Developer Agent Bridge (ImplementationState Adapter)
**What:** Developer.run() requires ImplementationState with a `goal` field. The develop node must construct a temporary ImplementationState for each file group.
**When to use:** Every Developer.run() call from the pr_auto_fix pipeline.
**Critical detail:** Developer.run() also requires `plan_markdown` (raises ValueError if None). The pr_fix developer node must either (a) set a minimal plan_markdown or (b) create a new Developer subclass/method. Option (a) is simpler and aligns with the decision to create a dedicated `call_pr_fix_developer_node`.

The Developer._build_prompt() checks `state.plan_markdown` and raises ValueError if None. The PR-fix developer node should either:
1. Set `plan_markdown` to a simple instruction string (e.g., the goal itself), OR
2. Pass the goal directly as `plan_markdown` since Developer._build_prompt wraps it with instructions anyway

**Example:**
```python
# Create a temporary ImplementationState for Developer.run()
temp_state = ImplementationState(
    workflow_id=state.workflow_id,
    profile_id=state.profile_id,
    created_at=state.created_at,
    status="running",
    goal=goal_text,
    plan_markdown=goal_text,  # Required by Developer._build_prompt
)
```

### Pattern 4: extract_config_params for Node Configuration
**What:** All nodes call `extract_config_params(config)` to get `(event_bus, workflow_id, profile)` from LangGraph's RunnableConfig.
**When to use:** Every node function.

### Pattern 5: Linear Graph with Edges
**What:** For the pr_auto_fix pipeline, the graph is linear: classify -> develop -> commit_push -> END. No conditional routing needed.
**Example:**
```python
# Source: pattern from amelia/pipelines/review/graph.py
def create_pr_auto_fix_graph(checkpointer=None):
    workflow = StateGraph(PRAutoFixState)
    workflow.add_node("classify_node", classify_node)
    workflow.add_node("develop_node", develop_node)
    workflow.add_node("commit_push_node", commit_push_node)
    workflow.set_entry_point("classify_node")
    workflow.add_edge("classify_node", "develop_node")
    workflow.add_edge("develop_node", "commit_push_node")
    workflow.add_edge("commit_push_node", END)
    return workflow.compile(checkpointer=checkpointer)
```

### Anti-Patterns to Avoid
- **Sharing ImplementationState:** Don't reuse it as the pipeline state. It has 15+ fields that are irrelevant and would cause confusion.
- **Reusing call_developer_node:** That function is tightly coupled to ImplementationState's task-based execution (current_task_index, total_tasks, base_commit tracking). The PR-fix node has different concerns.
- **LangGraph conditional loops for file groups:** Decided against in CONTEXT.md. Use a simple Python for-loop inside the develop node.
- **Force-pushing or pushing to protected branches:** GitOperations.safe_push() already guards against this, but the pipeline should also validate head_branch is not protected before starting.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Git commit + push | Custom subprocess calls | `GitOperations.stage_and_commit()` + `GitOperations.safe_push()` | Handles timeouts, protected branch guards, divergence detection |
| Comment classification | Custom LLM call | `classify_comments()` from services/classifier.py | Already handles batching, confidence thresholds, aggressiveness filtering |
| File grouping | Custom grouping logic | `group_comments_by_file()` from services/classifier.py | Handles None paths, actionability filtering |
| Pipeline registration | Custom discovery | Add entry to PIPELINES dict in registry.py | Established pattern, used by get_pipeline() |
| Token usage tracking | Custom tracking | `_save_token_usage()` from pipelines/nodes.py | Handles cost calculation, error resilience |

## Common Pitfalls

### Pitfall 1: Developer.run() Requires plan_markdown
**What goes wrong:** Developer._build_prompt() raises ValueError if state.plan_markdown is None.
**Why it happens:** Developer was designed for the implementation pipeline where the Architect always sets plan_markdown first.
**How to avoid:** Set plan_markdown to the goal text itself in the temporary ImplementationState. Developer._build_prompt wraps it with "IMPLEMENTATION PLAN:" header anyway.
**Warning signs:** ValueError("Developer requires plan_markdown. Architect must run first.")

### Pitfall 2: Frozen State Append-Only Fields
**What goes wrong:** Trying to set `tool_calls` or `tool_results` directly instead of using the `operator.add` reducer pattern.
**Why it happens:** These fields use `Annotated[list[...], operator.add]` which means LangGraph appends to them, not replaces.
**How to avoid:** In PRAutoFixState, if tool_calls/tool_results are not needed as append-only (since develop node handles groups internally), use regular lists without the operator.add annotation.
**Warning signs:** Tool calls from previous groups bleeding into current group's state.

### Pitfall 3: Classify Node Needs a Driver Instance
**What goes wrong:** classify_comments() requires a DriverInterface, but there's no agent for the classifier.
**Why it happens:** The classifier isn't a full agent -- it's a service that uses a driver directly.
**How to avoid:** Create a driver instance in the classify node using `get_driver()` with the profile's classifier/developer agent config. The existing classify_comments test mocks the driver.
**Warning signs:** Missing driver parameter.

### Pitfall 4: PRAutoFixConfig Not Passed to Classify Node
**What goes wrong:** classify_comments() needs PRAutoFixConfig for aggressiveness and confidence_threshold.
**Why it happens:** Config isn't part of pipeline state -- it needs to come from the profile or RunnableConfig.
**How to avoid:** Pass PRAutoFixConfig via RunnableConfig's configurable dict, or retrieve from the profile within the node using `profile.pr_autofix` (if that path exists) or pass as initial state field.
**Warning signs:** Classify node can't access aggressiveness settings.

### Pitfall 5: No Files Changed After Developer Runs
**What goes wrong:** Attempting to commit when Developer made no changes (e.g., all groups failed or comments were already addressed).
**Why it happens:** git commit fails with "nothing to commit" error.
**How to avoid:** Check `git status --porcelain` before committing. If empty, skip commit/push and mark all groups as 'no_changes'.
**Warning signs:** ValueError from GitOperations.stage_and_commit.

### Pitfall 6: Developer System Prompt Key Naming
**What goes wrong:** Using wrong key for custom prompt lookup.
**Why it happens:** Developer.__init__ checks `self._prompts.get("developer.system", ...)`. The PR-fix prompt needs a different key.
**How to avoid:** Register as `developer.pr_fix.system` in PROMPT_DEFAULTS and pass it via the prompts dict with key `"developer.system"` so Developer.system_prompt property picks it up. Or override the system_prompt property.
**Warning signs:** PR-fix Developer uses the generic implementation prompt instead of the PR-fix-specific one.

## Code Examples

### Creating PRAutoFixState
```python
# Source: pattern from amelia/pipelines/implementation/state.py
class GroupFixStatus(StrEnum):
    FIXED = "fixed"
    FAILED = "failed"
    NO_CHANGES = "no_changes"

class GroupFixResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    file_path: str | None
    status: GroupFixStatus
    error: str | None = None
    comment_ids: list[int] = Field(default_factory=list)

class PRAutoFixState(BasePipelineState):
    pipeline_type: Literal["pr_auto_fix"] = "pr_auto_fix"

    # PR identity
    pr_number: int
    head_branch: str
    repo: str

    # Classification results
    classified_comments: list[CommentClassification] = Field(default_factory=list)
    file_groups: dict[str, list[int]] = Field(default_factory=dict)  # file_path -> comment_ids

    # Developer tracking
    goal: str | None = None
    agentic_status: AgenticStatus = AgenticStatus.RUNNING

    # Results
    commit_sha: str | None = None
    group_results: list[GroupFixResult] = Field(default_factory=list)

    # Config (needed by classify node)
    autofix_config: PRAutoFixConfig = Field(default_factory=PRAutoFixConfig)

    # Raw comments (needed for building developer goals)
    comments: list[PRReviewComment] = Field(default_factory=list)
```

### Commit Message Construction
```python
# Source: CONTEXT.md specifics
def build_commit_message(
    prefix: str,
    group_results: list[GroupFixResult],
    comments: list[PRReviewComment],
) -> str:
    lines = [f"{prefix} address PR review comments", ""]
    lines.append("Addressed:")
    for result in group_results:
        if result.status == GroupFixStatus.FIXED:
            for cid in result.comment_ids:
                comment = next((c for c in comments if c.id == cid), None)
                if comment and comment.path and comment.line:
                    body_preview = comment.body[:60].replace("\n", " ")
                    lines.append(f"- {comment.path}:{comment.line} \"{body_preview}\"")
    return "\n".join(lines)
```

### Developer Goal Construction for File Group
```python
# Source: CONTEXT.md decisions
def build_developer_goal(
    file_path: str | None,
    comments: list[PRReviewComment],
    classifications: dict[int, CommentClassification],
    pr_number: int,
    head_branch: str,
) -> str:
    parts = [
        f"Fix code based on PR #{pr_number} review feedback (branch: {head_branch}).",
        "",
        "## Review Comments to Address",
        "",
    ]
    for comment in comments:
        cls = classifications.get(comment.id)
        parts.append(f"### {comment.path}:{comment.line}")
        parts.append(f"**Comment:** {comment.body}")
        if comment.diff_hunk:
            parts.append(f"**Diff context:**\n```\n{comment.diff_hunk}\n```")
        if cls:
            parts.append(f"**Category:** {cls.category} (reason: {cls.reason})")
        parts.append("")

    parts.extend([
        "## Constraints",
        f"- Only modify files related to: {file_path or 'general'}",
        "- Make minimal, targeted changes",
        "- Fix root causes, not symptoms",
        "- If a reviewer says a test fails, fix the code causing the failure, not the test",
    ])
    return "\n".join(parts)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Structured batch execution | Agentic tool-calling via Developer.run() | Pre-existing in codebase | Developer autonomously decides tools; no step-by-step orchestration |
| Shell-based git commands | create_subprocess_exec via GitOperations | Phase 2 (this project) | Shell-safe, proper error handling |

## Open Questions

1. **How does the classify node get a driver instance?**
   - What we know: classify_comments() requires a DriverInterface. The classifier isn't a registered agent.
   - What's unclear: Which agent config to use for the driver (there's no "classifier" agent in profiles).
   - Recommendation: Use the profile's developer agent config to create a driver for classification, or add a configurable "classifier" agent config. The simpler approach is passing the driver via RunnableConfig configurable dict.

2. **Should PRAutoFixState include raw comments or just IDs?**
   - What we know: The develop node needs full comment details (body, path, line, diff_hunk) to build Developer goals. The commit node needs comment details for the commit message.
   - What's unclear: Whether to store full PRReviewComment objects in state or pass them via config.
   - Recommendation: Store full comments in state (`comments: list[PRReviewComment]`). State is the canonical data flow mechanism in LangGraph, and these are small objects.

3. **How does the PR-fix system prompt get injected?**
   - What we know: Developer reads `self._prompts.get("developer.system", self.SYSTEM_PROMPT)`. The default SYSTEM_PROMPT comes from PROMPT_DEFAULTS["developer.system"].
   - What's unclear: Best way to override for PR-fix context without affecting the implementation Developer.
   - Recommendation: Register `developer.pr_fix.system` in PROMPT_DEFAULTS. In the develop node, pass `{"developer.system": PROMPT_DEFAULTS["developer.pr_fix.system"].content}` as the prompts dict to Developer constructor. This overrides the system prompt for this specific instance.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (asyncio_mode = "auto") |
| Config file | pyproject.toml |
| Quick run command | `uv run pytest tests/unit/pipelines/ -x -q` |
| Full suite command | `uv run pytest` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PIPE-01 | pr_auto_fix registered in PIPELINES | unit | `uv run pytest tests/unit/pipelines/test_registry.py -x` | Exists (needs new test) |
| PIPE-02 | Graph flows classify -> develop -> commit/push | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/ -x` | Wave 0 |
| PIPE-03 | Developer receives comment context | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py -x` | Wave 0 |
| PIPE-04 | Single commit with configurable prefix | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py -x` | Wave 0 |
| PIPE-05 | Push to head branch, never main | unit | `uv run pytest tests/unit/pipelines/pr_auto_fix/test_nodes.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/pipelines/ -x -q`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before /gsd:verify-work

### Wave 0 Gaps
- [ ] `tests/unit/pipelines/pr_auto_fix/__init__.py` -- package init
- [ ] `tests/unit/pipelines/pr_auto_fix/test_state.py` -- PRAutoFixState validation
- [ ] `tests/unit/pipelines/pr_auto_fix/test_nodes.py` -- classify, develop, commit_push nodes
- [ ] `tests/unit/pipelines/pr_auto_fix/test_graph.py` -- graph construction and edge validation
- [ ] `tests/unit/pipelines/pr_auto_fix/test_pipeline.py` -- PRAutoFixPipeline protocol conformance
- [ ] Update `tests/unit/pipelines/test_registry.py` -- add pr_auto_fix assertions

## Sources

### Primary (HIGH confidence)
- `amelia/pipelines/base.py` -- Pipeline Protocol, BasePipelineState, PipelineMetadata
- `amelia/pipelines/review/pipeline.py` -- ReviewPipeline pattern (closest analog)
- `amelia/pipelines/review/graph.py` -- StateGraph construction pattern
- `amelia/pipelines/nodes.py` -- call_developer_node reference implementation
- `amelia/agents/developer.py` -- Developer.run() signature, _build_prompt requirements
- `amelia/services/classifier.py` -- classify_comments, group_comments_by_file APIs
- `amelia/tools/git_utils.py` -- GitOperations.stage_and_commit, safe_push
- `amelia/pipelines/implementation/state.py` -- ImplementationState structure (what Developer expects)
- `amelia/core/agentic_state.py` -- AgenticStatus enum, ToolCall, ToolResult
- `amelia/agents/prompts/defaults.py` -- PROMPT_DEFAULTS registration pattern
- `amelia/pipelines/registry.py` -- PIPELINES dict and get_pipeline function
- `amelia/pipelines/utils.py` -- extract_config_params helper

### Secondary (MEDIUM confidence)
- `amelia/core/types.py` -- PRAutoFixConfig, PRReviewComment model shapes

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already in use, versions pinned in pyproject.toml
- Architecture: HIGH - following exact patterns from existing pipelines, all code inspected
- Pitfalls: HIGH - identified from direct code reading (Developer._build_prompt ValueError, frozen state semantics, driver requirements)

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable -- internal codebase patterns, no external API changes)
