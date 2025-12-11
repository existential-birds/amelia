# 12-Factor Agents Compliance Analysis

> Analyzing Amelia's alignment with the [12-Factor Agents](https://github.com/humanlayer/12-factor-agents) methodology.

## Executive Summary

| Factor | Status | Notes |
|--------|--------|-------|
| 1. Natural Language → Tool Calls | **Strong** | Schema-validated outputs, structured task execution |
| 2. Own Your Prompts | **Partial** | Prompts embedded in code, not templated or versioned |
| 3. Own Your Context Window | **Partial** | Message history exists, but not custom-formatted |
| 4. Tools Are Structured Outputs | **Strong** | Pydantic schemas enforce structure |
| 5. Unify Execution State | **Partial** | State split between LangGraph and SQLite |
| 6. Launch/Pause/Resume | **Strong** | REST API, WebSocket events, session handoffs (Phases 2,3,8,9,15) |
| 7. Contact Humans with Tools | **Partial** | Approval gates in place, structured questions coming (Phases 9,12) |
| 8. Own Your Control Flow | **Strong** | LangGraph provides full control over flow |
| 9. Compact Errors | **Partial** | Error tracking improving with verification framework (Phases 4,6,7) |
| 10. Small, Focused Agents | **Strong** | Architect/Developer/Reviewer separation |
| 11. Trigger from Anywhere | **Strong** | CLI, REST, WebSocket, chat integration (Phases 2,5,9,15) |
| 12. Stateless Reducer | **Partial** | State machine exists, but state is mutable |
| 13. Pre-fetch Context | **Partial** | Document RAG in place, code pre-fetching planned (Phases 11,13) |

**Overall (Post-Phase 15)**: 5 Strong, 8 Partial, 0 Weak

---

## Detailed Analysis

### Factor 1: Natural Language to Tool Calls

> **Principle**: Convert natural language inputs into structured, deterministic tool calls.

#### Current Implementation: Strong

Amelia excels here:

```python
# Architect produces TaskDAG from natural language issue
class TaskListResponse(BaseModel):
    tasks: list[Task]

class Task(BaseModel):
    name: str
    description: str
    steps: list[Step]          # Structured sub-tasks
    dependencies: list[str]     # DAG edges
    files_modified: list[str]
```

**What we do well:**
- Issues are converted to structured `TaskDAG` objects
- Schema validation via Pydantic ensures LLM outputs conform
- CLI driver uses `--json-schema` for structured generation
- Tasks contain explicit steps (TDD structure: test → implement → commit)

**Evidence:**
- `amelia/agents/architect.py:62-68` - Schema-validated task generation
- `amelia/core/state.py:45-89` - Task/TaskDAG models with validators

#### Gap: None significant

#### Roadmap Alignment

**Addressed in Phase 1 (Complete)**:
- TaskDAG generation with Pydantic validation
- Schema-enforced structured outputs

---

### Factor 2: Own Your Prompts

> **Principle**: Treat prompts as first-class code you control and iterate on.

#### Current Implementation: Partial

**What we do well:**
- Explicit system prompts define each agent's role
- Role-specific instructions (architect vs developer vs reviewer)
- Schema definitions enforce output structure

**What we're missing:**
- Prompts are **hardcoded strings** in agent files, not templates
- No prompt versioning or A/B testing infrastructure
- No centralized prompt registry for iteration
- Can't iterate on prompts without code changes

**Current pattern (embedded):**
```python
# amelia/agents/architect.py - prompt is inline
SYSTEM_PROMPT = """You are an expert software architect..."""
```

**Recommended pattern (templated):**
```python
# prompts/architect/system.md
# prompts/architect/user.jinja2
prompt_manager.load("architect", context={"issue": issue})
```

#### Gap: Not fully addressed in roadmap

**Recommendation**: Add prompt templating system (Jinja2 + versioning) in future phase.

#### Roadmap Alignment

**Partially addressed in Phase 10 (Continuous Improvement)**:
- A/B testing infrastructure for prompts
- Prompt refinement via benchmarks

**Not addressed**: Prompt templating, externalization, version control

---

### Factor 3: Own Your Context Window

> **Principle**: Control how history, state, and tool results are formatted for the LLM.

#### Current Implementation: Partial

**What we do well:**
- `ExecutionState` tracks messages, plan, and review history
- Messages accumulate across agent transitions
- Reviewer sees full diff context

**What we're missing:**
- Standard message format (system/user/assistant), not custom XML/event format
- No structured event thread with typed events
- History not optimized for token efficiency
- No context compaction or summarization
- Errors not structured for LLM self-healing

**Current pattern:**
```python
# Messages are simple AgentMessage objects
class AgentMessage:
    role: str  # "system", "user", "assistant"
    content: str
```

**12-Factor pattern:**
```xml
<event type="tool_result" tool="create_task" status="success">
  {"task_id": "T-123", "name": "Add login"}
</event>
<event type="error" recoverable="true">
  {"message": "File not found", "suggestion": "Check path"}
</event>
```

#### Gap: Partially addressed in roadmap

**Recommendation**: Add structured event thread format for LLM context.

#### Roadmap Alignment

**Addressed in Phases 2 & 3**:
- Phase 2 adds [Context Compiler infrastructure](../analysis/context-engineering-gaps.md#gap-1-context-compiler) - fresh context projection per LLM call
- Phase 2 implements [Prompt Prefix Stability](../analysis/context-engineering-gaps.md#gap-3-prompt-prefix-stability-for-cache-optimization) - stable prefixes for cache optimization
- Phase 2 adds [Agent Scope Isolation](../analysis/context-engineering-gaps.md#gap-5-agent-scope-isolation) - minimal default context per agent
- Phase 3 implements [Schema-Driven Summarization](../analysis/context-engineering-gaps.md#gap-2-schema-driven-summarization) - compact context preserving semantics
- Phase 3 adds [Tiered Memory Architecture](../analysis/context-engineering-gaps.md#gap-4-tiered-memory-architecture) - Working Context/Sessions/Memory/Artifacts hierarchy
- Phase 3 implements [Session Memory Retrieval](../analysis/context-engineering-gaps.md#gap-6-session-memory-retrieval) - on-demand access to relevant history
- Phase 3 adds [Artifact Handle System](../analysis/context-engineering-gaps.md#gap-7-artifact-handle-system) - reference large objects by pointer

These Phase 2 & 3 improvements directly implement F3 principles from the 12-Factor Agents methodology.

---

### Factor 4: Tools Are Structured Outputs

> **Principle**: Tools are JSON outputs that trigger deterministic code, not magic function calls.

#### Current Implementation: Strong

**What we do well:**
- Tool calls produce structured responses (`DeveloperResponse`, `ReviewResponse`)
- Separation between LLM intent and execution handler
- Validation layer between LLM output and tool execution

**Evidence:**
```python
# amelia/agents/developer.py
class DeveloperResponse(BaseModel):
    status: Literal["completed", "failed", "needs_review"]
    output: str
    error: str | None
```

The handler interprets this structure and takes appropriate action.

#### Gap: None significant

#### Roadmap Alignment

**Addressed in Phase 1 (Complete)**:
- Pydantic-validated tool responses
- Clear separation between LLM output and execution

---

### Factor 5: Unify Execution State

> **Principle**: Merge execution state (current step, retry count) with business state (messages, results).

#### Current Implementation: Partial

**What we do well:**
- `ExecutionState` contains both business data (issue, plan) and execution metadata (workflow_status)
- State passed through LangGraph transitions
- Server persists full state as JSON blob

**What we're missing:**
- **Dual state systems**: LangGraph in-memory checkpoints + SQLite `state_json`
- Retry counts, error history not tracked in unified state
- No single serializable object that captures everything
- State reconstruction requires both LangGraph checkpoint AND database

**Current split:**
```
ExecutionState (LangGraph) ←→ ServerExecutionState (SQLite)
    ↓                              ↓
In-memory checkpoints         state_json blob
```

**12-Factor pattern:**
```python
# Single Thread object contains everything
thread = Thread(
    events=[...],           # Full history
    current_step=3,         # Execution pointer
    error_count=1,          # Retry tracking
    human_pending=True      # Waiting state
)
```

#### Gap: Partially addressed in roadmap

#### Roadmap Alignment

**Addressed in Phases 2 & 3**:
- Phase 2: SQLite persistence for unified state storage
- Phase 3: `amelia-progress.json` as single source of truth, Git-reconstructible
- Phase 3: [Tiered Memory Architecture](../analysis/context-engineering-gaps.md#gap-4-tiered-memory-architecture) unifies state across tiers

**Not fully addressed**: Elimination of dual state systems (LangGraph checkpoints vs SQLite)

---

### Factor 6: Launch/Pause/Resume

> **Principle**: Agents should support simple launch, query, pause, and resume via external triggers.

#### Current Implementation: Partial

**What we do well:**
- Launch: CLI (`amelia start ISSUE-123`) and REST API (`POST /workflows`)
- Human approval gate pauses between planning and execution
- WebSocket events enable async notification

**What we're missing:**
- **No pause between tool selection and invocation** (tool-level approval mode)
- No webhook-based resume from external systems (coming in Phase 9)
- State not fully serializable for resume after process restart (improving in Phases 2-3)
- No "fire-and-forget" background execution with callback (coming in Phase 8)

**Current flow:**
```
Plan → [PAUSE: Human Approval] → Execute All Tasks → Review
```

**12-Factor flow:**
```
Plan → [PAUSE] → Select Tool → [PAUSE: Approve?] → Execute Tool → Loop
```

The granular pause between selection and execution is missing.

#### Gap: Tool-level approval mode not in roadmap

**Recommendation**: Add tool-level approval mode for high-risk operations (pause between tool selection and execution).

#### Roadmap Alignment

**Addressed in Phases 2, 3, 8, 9, 15**:
- Phase 2: REST API for launch (`POST /workflows`), query (`GET /workflows/{id}`)
- Phase 2: WebSocket events for async state updates
- Phase 3: Session kickoff protocol and explicit pause points for handoffs
- Phase 3: Mergeable state guarantee - every session ends with passing tests
- Phase 8: Fire-and-forget execution with callback notifications
- Phase 8: Parallel workflows with resource management
- Phase 9: Webhook-based resume from Slack/Discord responses
- Phase 15: Cloud-scale launch/pause/resume with thin CLI client

**Not addressed**: Per-tool-call approval gates for high-risk operations

---

### Factor 7: Contact Humans with Tool Calls

> **Principle**: Use structured tool calls (intent, question, options) to contact humans.

#### Current Implementation: Weak

**What we do:**
- CLI: `typer.confirm()` / `typer.prompt()` - blocking synchronous prompts
- Server: REST endpoints for approval/rejection
- No structured human contact from within agent loop

**What we're missing:**
- **No `request_human_input` tool** - agents can't ask clarifying questions
- Human contact is hardcoded at graph nodes, not tool-based
- No support for different contact formats (yes/no, multiple choice, free text)
- No async human response handling (webhooks)

**Current pattern:**
```python
# Human interaction hardcoded in orchestrator
def human_approval_node(state):
    approved = typer.confirm("Approve?")  # Blocking!
```

**12-Factor pattern:**
```python
# Agent requests human input as a tool call
{
    "intent": "request_human_input",
    "question": "The API schema is ambiguous. Should I...",
    "options": ["Option A: REST", "Option B: GraphQL"],
    "urgency": "high"
}
# Loop breaks, webhook resumes when human responds
```

#### Gap: Partially addressed in roadmap

**Recommendation**: Add `request_human_input` tool type that breaks execution loop.

#### Roadmap Alignment

**Addressed in Phases 9 & 12**:
- Phase 9: Slack/Discord approval via action buttons (structured contact mechanism)
- Phase 9: Configurable notification verbosity
- Phase 12: Human checkpoints in Debate Mode for guidance injection

**Not addressed**: `request_human_input` as first-class tool type that agents can invoke mid-workflow

---

### Factor 8: Own Your Control Flow

> **Principle**: Build custom control structures tailored to your use case.

#### Current Implementation: Strong

**What we do well:**
- LangGraph provides full control over transitions
- Conditional edges based on task completion, review status
- Custom routing logic (developer loop, reviewer rejection loop)
- Execution modes (agentic vs structured)

**Evidence:**
```python
# amelia/core/orchestrator.py
graph.add_conditional_edges(
    "developer",
    lambda s: "developer" if s.plan.get_ready_tasks() else "reviewer"
)
graph.add_conditional_edges(
    "reviewer",
    route_after_review  # Custom logic
)
```

**What we could improve:**
- No context compaction mid-workflow (coming in Phase 3)
- No LLM-as-judge validation layer
- Rate limiting handled per-driver, not centrally

#### Gap: Mostly addressed

Control flow is a strength. Future work could add compaction and validation.

#### Roadmap Alignment

**Addressed in Phase 1 (Complete)**:
- LangGraph state machine with full control over transitions
- Conditional edges based on state
- Custom routing logic for developer/reviewer loops

---

### Factor 9: Compact Errors into Context Window

> **Principle**: Enable self-healing by capturing errors in context for LLM analysis.

#### Current Implementation: Weak

**What we do:**
- Errors logged via loguru
- `SafeShellExecutor` returns error details
- `DeveloperResponse` can contain `error` field

**What we're missing:**
- **No error event thread** - errors not accumulated in context
- **No retry threshold** - no consecutive error counter
- **No self-healing loop** - errors don't trigger adjusted tool calls
- Errors logged but not fed back to LLM for correction

**Current pattern:**
```python
# Error returned, but not added to context for retry
try:
    result = await executor.run(command)
except ShellExecutionError as e:
    logger.error(f"Command failed: {e}")
    return DeveloperResponse(status="failed", error=str(e))
```

**12-Factor pattern:**
```python
# Error added to thread, LLM retries with context
thread.append(Event(type="error", data=format_error(e)))
if consecutive_errors < 3:
    continue  # LLM sees error and adjusts
else:
    escalate_to_human()
```

#### Gap: Partially addressed in roadmap

**Recommendation**: Add error event tracking with retry thresholds, enhance with structured error context.

#### Roadmap Alignment

**Addressed in Phases 4, 6, 7**:
- Phase 4: Verification failures produce structured error context for retry attempts
- Phase 4: Test results and screenshots become part of agent context
- Phase 6: CI failures and review comments become structured context for fixes
- Phase 7: Gate failures produce actionable error context with retry logic

**Not fully addressed**: Error event thread accumulation, consecutive error counting, automatic escalation thresholds

---

### Factor 10: Small, Focused Agents

> **Principle**: Build specialized agents with limited scope (3-10 steps max).

#### Current Implementation: Strong

**What we do well:**
- **Architect**: Single responsibility - issue → plan
- **Developer**: Single responsibility - task → code
- **Reviewer**: Single responsibility - code → feedback
- Tasks scoped to ~3-5 steps each
- Competitive review spawns multiple focused reviewer personas

**Evidence:**
```
Issue → Architect (1 step)
     → Developer (N tasks, each 3-5 steps)
     → Reviewer (1 review per diff)
```

**What we could improve:**
- No explicit step limit enforcement
- Large tasks could still overwhelm context (addressed in Phase 3)

#### Gap: None significant

Strong compliance with this factor.

#### Roadmap Alignment

**Addressed in Phase 1 (Complete)**:
- Architect/Developer/Reviewer separation with single responsibilities
- Tasks scoped to 3-5 steps each

**Enhanced in Phases 7 & 12**:
- Phase 7: Specialized reviewers (Security, Performance, Accessibility) as focused sub-agents
- Phase 12: Debate Mode with focused agents per perspective

---

### Factor 11: Trigger from Anywhere

> **Principle**: Enable triggers from multiple channels (CLI, Slack, email, events).

#### Current Implementation: Partial

**What we do:**
- CLI: `amelia start`, `amelia plan-only`, `amelia review`
- REST API: Full CRUD for workflows
- WebSocket: Real-time event streaming

**What we're missing:**
- **No event-driven triggers** - no cron or external event support (beyond webhooks in Phase 9)

#### Gap: Fully addressed in roadmap

#### Roadmap Alignment

**Addressed in Phases 2, 5, 9, 15**:
- Phase 2: REST API with WebSocket events for real-time updates
- Phase 5: Bidirectional tracker sync - issues become first-class triggers regardless of source
- Phase 9: Slack DM interface with approval buttons
- Phase 9: Discord bot commands with role-based permissions
- Phase 9: Thread-per-workflow isolation
- Phase 15: Cloud deployment with thin CLI client and web dashboard connectivity

**Not addressed**: Event-driven triggers (cron, external events beyond chat/tracker)

---

### Factor 12: Stateless Reducer

> **Principle**: Treat agents as stateless reducers transforming input through deterministic steps.

#### Current Implementation: Partial

**What we do well:**
- LangGraph nodes are effectively reducers (state in → state out)
- `ExecutionState` is immutable (updates create new instances)
- Transitions are deterministic based on state

**What we're missing:**
- State mutations happen in-place within nodes
- No pure-function composition pattern
- Hidden state in driver sessions, subprocess handles
- `MemorySaver` is mutable shared state

**Evidence of mutation:**
```python
# State is updated in place, not returned as new object
state.plan.tasks[idx].status = "completed"
```

**12-Factor pattern:**
```python
# Pure reducer returns new state
def developer_node(state: State) -> State:
    new_tasks = [t.with_status("completed") if ... else t for t in state.tasks]
    return state.with_tasks(new_tasks)
```

#### Gap: Not directly addressed in roadmap

**Recommendation**: Consider immutable state updates for better debugging/replay.

#### Roadmap Alignment

**Partially addressed in Phases 8 & 15**:
- Phase 8: Parallel workflows require state isolation - no shared mutable state
- Phase 15: Cloud deployment requires fully serializable, stateless workflow execution

**Not addressed**: Pure reducer pattern with immutable state updates, elimination of in-place mutations

---

### Appendix 13: Pre-fetch Context

> **Principle**: Fetch likely-needed data upfront rather than mid-workflow.

#### Current Implementation: Weak

**What we do:**
- Issue context fetched once at start
- Design documents attached if provided
- Git diff fetched for reviewer

**What we're missing:**
- **No proactive context fetching** - don't pre-fetch codebase structure, existing tests, CI status
- **No RAG integration** - don't retrieve relevant code before planning
- **No pre-fetched documentation** - architect doesn't see existing patterns

**12-Factor pattern:**
```python
# Before architect runs, pre-fetch:
context = {
    "issue": issue,
    "existing_tests": find_related_tests(issue),
    "similar_features": search_codebase(issue.keywords),
    "ci_status": get_pipeline_status(),
    "recent_commits": get_commit_history(5)
}
```

#### Gap: Partially addressed in roadmap

**Still missing**: Automatic code/test pre-fetching for Architect.

#### Roadmap Alignment

**Addressed in Phases 11 & 13**:
- Phase 11: Spec Builder with document ingestion (PDF, DOCX, PPTX, Markdown, HTML)
- Phase 11: Semantic search with source citations
- Phase 11: Design documents pre-loaded before Architect planning
- Phase 13: Knowledge Library with framework documentation indexing
- Phase 13: Agent RAG integration for pertinent retrieval during tasks
- Phase 13: Relevant documentation pre-fetched based on task keywords

**Not addressed**: Automatic code/test pre-fetching, CI status, recent commits before Architect planning

---

## Context Engineering Integration

The roadmap explicitly integrates context engineering principles from [Context Engineering Gaps Analysis](context-engineering-gaps.md) into Phases 2 and 3:

### Phase 2: Context Compiler Infrastructure

Phase 2 addresses the following context engineering gaps:

- **[Gap 1: Context Compiler](context-engineering-gaps.md#gap-1-context-compiler)** - Every LLM call becomes a freshly computed projection against durable state, not dragging full message history
- **[Gap 3: Prompt Prefix Stability](context-engineering-gaps.md#gap-3-prompt-prefix-stability-for-cache-optimization)** - Stable prompt prefixes enable cache reuse, reducing latency and costs by 10x
- **[Gap 5: Agent Scope Isolation](context-engineering-gaps.md#gap-5-agent-scope-isolation)** - Each agent receives minimal default context, must actively request additional information

These directly implement **Factor 3 (Own Your Context Window)** principles.

### Phase 3: Session Continuity & Memory Architecture

Phase 3 addresses the following context engineering gaps:

- **[Gap 2: Schema-Driven Summarization](context-engineering-gaps.md#gap-2-schema-driven-summarization)** - Compact context preserving semantic structure, avoiding "glossy soup"
- **[Gap 4: Tiered Memory Architecture](context-engineering-gaps.md#gap-4-tiered-memory-architecture)** - Working Context, Sessions, Memory, Artifacts hierarchy mirroring Cache/RAM/Disk
- **[Gap 6: Session Memory Retrieval](context-engineering-gaps.md#gap-6-session-memory-retrieval)** - On-demand retrieval from searchable history instead of pinning everything
- **[Gap 7: Artifact Handle System](context-engineering-gaps.md#gap-7-artifact-handle-system)** - Reference large objects by pointer rather than embedding content

These further strengthen **Factor 3 (Own Your Context Window)** and enable **Factor 5 (Unified State)** through tiered architecture.

---

## Gap Summary by Roadmap Phase

### Addressed in Current Roadmap

| 12-Factor Gap | Roadmap Phase(s) | Context Engineering Gap |
|---------------|------------------|-------------------------|
| F3: Context window control | Phase 2: Context Compiler, Prefix Stability, Agent Scope | CE Gap 1, 3, 5 |
| F3 & F5: Unified state with context | Phase 3: Session continuity, Tiered Memory, Artifacts | CE Gap 2, 4, 6, 7 |
| F5: State persistence | Phase 2: SQLite, REST API | - |
| F6: Launch/Pause/Resume | Phases 2, 3, 8, 9, 15 | - |
| F7: Human contact | Phases 9, 12: Slack/Discord, Debate checkpoints | - |
| F9: Error context | Phases 4, 6, 7: Verification, CI, Gates | - |
| F11: Multi-channel triggers | Phases 2, 5, 9, 15: API, Tracker, Chat, Cloud | - |
| F13: Pre-fetch context | Phases 11, 13: Spec Builder, Knowledge Library | - |

### Not Addressed in Roadmap

| 12-Factor Gap | Recommendation | Priority | Phase 16? |
|---------------|----------------|----------|-----------|
| F2: Prompt templating | Add Jinja2 templates with versioning | Medium | Yes |
| F6: Tool-level approval | Pause between tool selection/execution | High | Yes |
| F7: `request_human_input` tool | Enable agents to ask clarifying questions | High | Yes |
| F9: Error self-healing loop | Add retry thresholds and error event thread | Medium | Yes |
| F12: Immutable state | Refactor to pure reducer pattern | Low | Yes |
| F13: Code pre-fetching | Auto-fetch tests, similar features, commits | Medium | Yes |

---

## Recommendations for Phase 16

Phase 16 (Closing the 12-Factor Loop) will address remaining gaps with these architectural refinements:

### High Priority

1. **Add `request_human_input` tool (F7)** - Enables agents to ask clarifying questions mid-workflow, breaking the loop for async response. Structured question format with urgency, options, and response type.

2. **Add tool-level approval mode (F6)** - For high-risk operations (deployments, data mutations), pause between tool selection and execution. Critical for compliance workflows.

3. **Implement error self-healing loop (F9)** - Track consecutive errors in event thread, feed back to LLM context, escalate after configurable threshold. Enable automatic retry with adjusted parameters.

### Medium Priority

4. **Externalize prompts (F2)** - Move to Jinja2 templates with version control and A/B testing capability. Enable prompt iteration without code changes.

5. **Pre-fetch code context (F13)** - Before Architect planning, auto-fetch existing tests, similar features, recent commits, and CI status. Complement document RAG from Phases 11 & 13.

6. **Structured event thread (F3)** - Replace simple message history with typed events (tool_call, tool_result, error, human_response). Enable better compaction and replay. (Note: Partially addressed by Phase 3 Schema-Driven Summarization)

### Lower Priority

7. **Immutable state updates (F12)** - Refactor to pure reducer pattern for better debugging and replay. Return new state objects instead of mutating in-place.

8. **True state unification (F5)** - Eliminate dual state systems (LangGraph checkpoints vs SQLite). Single serializable Thread object captures everything.

---

## Conclusion

Amelia's compliance with the 12-Factor Agents methodology has significantly improved through the updated roadmap:

### Current State (Phase 1)
- **Strong (4)**: Structured outputs (F1, F4), focused agents (F10), control flow ownership (F8)
- **Partial (6)**: State management (F5, F12), launch/pause (F6), context (F3), prompts (F2), triggers (F11), pre-fetching (F13)
- **Weak (3)**: Human contact as tools (F7), error recovery (F9)

### Post-Phase 15 Projection
- **Strong (5)**: F1, F4, F6, F8, F10, F11 - Adding launch/pause/resume and multi-channel triggers
- **Partial (8)**: F2, F3, F5, F7, F9, F12, F13 - Improvements across context, errors, and human contact
- **Weak (0)**: All factors addressed to at least partial compliance

### Key Improvements

**Phases 2 & 3** represent the most significant compliance leap through context engineering integration:
- **Factor 3 (Own Your Context Window)**: Context Compiler, Prompt Prefix Stability, Agent Scope Isolation, Schema-Driven Summarization, Tiered Memory, Session Retrieval, Artifact Handles
- **Factor 5 (Unified State)**: SQLite persistence, progress artifacts, tiered architecture
- **Factor 6 (Launch/Pause/Resume)**: REST API, WebSocket events, session handoffs

**Phases 4-15** continue strengthening compliance:
- **Factor 7 (Human Contact)**: Chat integration with approval buttons, debate checkpoints
- **Factor 9 (Error Recovery)**: Verification failures, CI context, gate failures as structured errors
- **Factor 11 (Trigger from Anywhere)**: Tracker sync, chat platforms, cloud deployment
- **Factor 13 (Pre-fetch Context)**: Document RAG, framework knowledge base

**Phase 16** closes remaining gaps with architectural refinements: prompt templating, tool-level approval, `request_human_input` tool, error self-healing loop, and code pre-fetching.

The strongest alignment remains with **Factor 10 (Small, Focused Agents)** - Amelia's Architect/Developer/Reviewer separation exemplifies this pattern. The most improved factor is **Factor 6 (Launch/Pause/Resume)**, moving from Partial to Strong through comprehensive session continuity and multi-channel control.
