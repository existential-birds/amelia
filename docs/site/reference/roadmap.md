# Amelia Roadmap

> **Vision:** Enterprise-grade agent orchestration for software development. Complete workflow control from issue to PR, with defense-in-depth security, comprehensive observability, and automated quality gates. Built for teams that need reliability, auditability, and compliance.
>
> **Architecture:** Aligned with the [12-Factor Agents](https://github.com/humanlayer/12-factor-agents) methodology for building reliable LLM-powered software.
>
> **Track Progress:** [GitHub Project Board](https://github.com/orgs/existential-birds/projects/1)

## Design Principles

These principles, informed by [Anthropic's research on effective agent harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), guide all roadmap decisions:

1. **Model Improvement as Tailwind** - Build features assuming LLMs will get smarter; prefer prompts over code, delegation over hardcoding
2. **Structured Handoffs** - Agents working across sessions need explicit state transfer mechanisms
3. **One Feature at a Time** - Context exhaustion is the enemy; focused work with clear completion criteria
4. **Verify Before Declaring Done** - Agents must test as humans would, not just claim completion
5. **Incremental Accountability** - Every change is committed, logged, and recoverable
6. **Environment as Truth** - Git history and artifacts are the source of truth, not agent memory

## Research Foundation

This roadmap is informed by industry research on agentic AI systems. Key findings incorporated:

| Research Finding | Impact on Roadmap |
|------------------|-------------------|
| Orchestrator-worker: 90.2% improvement (Anthropic) | Phase 1 agent architecture validated |
| Reflexion: 91% vs 80% on coding (Shinn et al.) | Phase 4 adds self-reflection protocol |
| Multi-agent: ~15× token cost | Phase 3 adds concrete token budgets |
| "LLMs can't plan alone" (Kambhampati 2024) | Dynamic orchestration adds plan verification |
| Sectioning vs Voting patterns | Phase 8 adds both parallelization strategies |
| "Evaluation lacks granularity" | Phase 10 adds per-agent, per-step metrics |

See [Knowledge Agents Research Analysis](/ideas/research/knowledge-agents) for full research synthesis.

## Enterprise Readiness

Amelia is designed for production deployment in enterprise environments. Key architectural decisions:

| Requirement | Implementation | Phase |
|-------------|---------------|-------|
| **Security** | Layered guardrails, agent authorization, MCP security | 16, 19 |
| **Observability** | Unified events, distributed tracing, metrics | 2, 20 |
| **Scalability** | Stateless execution, cloud deployment, context management | 15, 17 |
| **Quality Assurance** | Verification framework, evaluation CI/CD, quality gates | 4, 7, 18 |
| **Compliance** | Audit logging, capitalization tracking, human approval gates | 1, 14, 19 |
| **Recovery** | Checkpoint persistence, session continuity, idempotent execution | 3, 15 |

---

## Phase 1: Core Orchestration [Complete]

*Multi-agent coordination with human oversight*

The foundation: specialized AI agents working in sequence with explicit approval gates before any code changes ship.

**Key Capabilities:**
- Agent orchestration via state machine (Architect → Developer → Reviewer loop)
- Human approval gates before execution proceeds
- Multi-driver support for API and CLI-based LLM access
- Jira and GitHub issue tracker integrations

**12-Factor Compliance:**
- **F1 (Natural Language → Tool Calls)**: Issues converted to structured markdown plans with extracted goals and Pydantic validation
- **F4 (Tools = Structured Outputs)**: `DeveloperResponse`, `ReviewResponse` enforce schema compliance
- **F8 (Own Control Flow)**: LangGraph provides full control over transitions and routing
- **F10 (Small Focused Agents)**: Architect/Developer/Reviewer separation with ~3-5 steps per task

---

## Phase 2: Web Dashboard [In Progress]

*Observable orchestration through a local web interface*

A browser-based dashboard that provides visibility into workflow state, enables approvals, and streams real-time updates.

**Key Capabilities:**
- FastAPI server with SQLite persistence
- Workflow and task state tracking with event history
- REST API for workflow management (create, list, approve, reject, cancel)
- React dashboard with workflow visualization
- Real-time updates via WebSocket events

**12-Factor Compliance:**
- **F5 (Unified State)**: SQLite persistence begins state unification—workflow, task, and event history in one store
- **F6 (Launch/Pause/Resume)**: REST API enables external launch (`POST /workflows`) and query (`GET /workflows/{id}`)
- **F11 (Trigger from Anywhere)**: WebSocket events enable async notification to any connected client

---

## Phase 3: Session Continuity [Planned]

*Structured handoff mechanisms for long-running work*

Long-running agents fail across context windows because each session starts fresh. This phase adds explicit progress tracking so any agent can resume where another left off.

**Key Capabilities:**
- Machine-readable progress artifacts persisted to the repository
- Session kickoff protocol (verify environment, review history, select next feature)
- One-feature-per-session discipline to prevent context exhaustion
- Mergeable state guarantee—every session ends with passing tests and committed changes
- **Token budget enforcement**: 2,000 token limit per agent output (research-based)
- **Compaction triggers**: Auto-summarize when context exceeds 50,000 tokens

**12-Factor Compliance:**
- **F5 (Unified State)**: `amelia-progress.json` becomes single source of truth, Git-reconstructible
- **F6 (Launch/Pause/Resume)**: Explicit pause points and resume protocol for session handoffs
- **F3 (Own Context Window)**: Progress artifacts provide structured context for new sessions

---

## Phase 4: Verification Framework [Planned]

*Agents must verify before declaring done*

A major failure mode: agents mark features complete without proper verification. This phase adds browser-based end-to-end testing so agents test as humans would.

**Key Capabilities:**
- Browser automation integration (Puppeteer/Playwright) for agents
- Pre-completion verification: run happy paths, check for errors, capture evidence
- Feature tracking with explicit passing/failing status
- Health checks at session start—tests must pass before new work begins
- **Self-reflection protocol**: Developer self-reviews before Reviewer (Reflexion pattern: 91% vs 80% on HumanEval)
- **Two-stage verification**: Internal reflection → External review → Automated testing

**12-Factor Compliance:**
- **F9 (Compact Errors)**: Verification failures produce structured error context for retry attempts
- **F3 (Own Context Window)**: Test results and screenshots become part of agent context

---

## Phase 5: Bidirectional Tracker Sync [Planned]

*Eliminate tracker web UI entirely*

Full issue lifecycle management from the command line: create, update, transition, comment, and close issues without opening a browser.

**Key Capabilities:**
- Create and update issues via CLI
- Transition issue status (To Do → In Progress → Review → Done)
- Add comments and close with resolution summary
- Label, milestone, and related-issue management
- Bidirectional sync with conflict resolution

**12-Factor Compliance:**
- **F11 (Trigger from Anywhere)**: Issues become first-class triggers regardless of source system

---

## Phase 6: Pull Request Lifecycle [Planned]

*Eliminate GitHub web for code review*

Complete PR management from creation through merge, including handling reviewer feedback and automated merge when checks pass.

**Key Capabilities:**
- Generate PRs from task metadata with auto-assigned reviewers
- Fetch and address review comments with fixup commits
- Monitor CI status and auto-merge when approved
- Automatic branch cleanup post-merge

**12-Factor Compliance:**
- **F9 (Compact Errors)**: CI failures and review comments become structured context for fixes
- **F6 (Launch/Pause/Resume)**: Workflows pause awaiting approval, resume on merge

---

## Phase 7: Quality Gates [Planned]

*Objective verification before subjective review*

Automated gates that must pass before code reaches human reviewers: linting, type checking, tests, security scans, and architecture rules.

**Key Capabilities:**
- Pre-review automation (lint, typecheck, test, security scan)
- Configurable coverage thresholds with regression tracking
- Architecture rules (import restrictions, module boundaries, naming conventions)
- Specialized reviewers (Security, Performance, Accessibility) running in parallel

**12-Factor Compliance:**
- **F9 (Compact Errors)**: Gate failures produce actionable error context with retry logic
- **F10 (Small Focused Agents)**: Specialized reviewers (Security, Perf, A11y) as focused sub-agents

---

## Phase 8: Parallel Execution [Planned]

*Multiply throughput without proportional attention cost*

Run multiple independent workflows concurrently, each isolated in its own worktree, with a unified dashboard view.

**Key Capabilities:**
- Concurrent workflows on independent issues
- DAG-aware task scheduling within workflows
- Resource management (LLM rate limiting, compute allocation)
- Fire-and-forget execution with notifications on completion
- **Sectioning pattern**: Parallel execution of independent subtasks (research-validated)
- **Voting pattern**: Run high-stakes tasks multiple times, resolve conflicts for consensus

**12-Factor Compliance:**
- **F5 (Unified State)**: Each worktree maintains isolated, serializable state
- **F6 (Launch/Pause/Resume)**: Fire-and-forget launch with callback notifications
- **F12 (Stateless Reducer)**: Parallel workflows require state isolation—no shared mutable state

---

## Phase 9: Chat Integration [Planned]

*Async and mobile workflow management*

Manage workflows via Slack or Discord: receive status updates, approve plans, and monitor progress from your phone.

**Key Capabilities:**
- Slack DM interface with approval action buttons
- Discord bot commands and role-based permissions
- Configurable notification verbosity and quiet hours
- Thread-per-workflow isolation

**12-Factor Compliance:**
- **F7 (Contact Humans with Tools)**: Approval buttons as structured human contact mechanism
- **F11 (Trigger from Anywhere)**: Slack/Discord as additional trigger channels
- **F6 (Launch/Pause/Resume)**: Webhook-based resume from chat responses

---

## Phase 10: Continuous Improvement [Planned]

*Quality flywheel that compounds over time*

Track outcomes, learn from patterns, and automatically improve agent behavior based on historical performance.

**Key Capabilities:**
- Success/failure rate tracking per agent, project, and task type
- Reviewer pattern detection (preemptively address common feedback)
- Project-specific knowledge base (idioms, pitfalls, architectural decisions)
- Prompt refinement via A/B testing with benchmark suite
- **Per-agent metrics**: Track success rate, token usage, latency per agent type
- **Per-step metrics**: Identify bottleneck steps in workflows (research: "evaluation lacks granularity")

**12-Factor Compliance:**
- **F2 (Own Your Prompts)**: A/B testing infrastructure enables prompt iteration without code changes
- **F9 (Compact Errors)**: Historical error patterns inform retry strategies

---

## Phase 11: Spec Builder [Planned]

*Local NotebookLM for technical design documents*

A document-assisted design tool: upload reference materials, explore them through guided chat, and generate structured specs that feed directly into the Architect.

**Key Capabilities:**
- Document ingestion (PDF, DOCX, PPTX, Markdown, HTML)
- Semantic search with source citations
- Section-by-section spec generation from templates
- Dashboard integration with chat interface and spec preview

**12-Factor Compliance:**
- **F3 (Own Context Window)**: RAG retrieval enables custom context construction from documents
- **F13 (Pre-fetch Context)**: Design documents pre-loaded before Architect planning

See [Spec Builder Design](https://github.com/existential-birds/amelia/issues/204) for detailed specification.

---

## Phase 12: Debate Mode [Planned]

*Multi-agent deliberation for design decisions*

When facing complex decisions without clear answers, spawn multiple agents with assigned perspectives to argue different viewpoints, moderated by a Judge that synthesizes a recommendation.

**Key Capabilities:**
- Moderator analyzes prompts and assigns relevant perspectives
- Parallel debate rounds with convergence detection
- Human checkpoints for guidance injection
- Synthesis documents with recommendations, confidence levels, and caveats

**12-Factor Compliance:**
- **F10 (Small Focused Agents)**: Each debater is a focused agent with a single perspective
- **F7 (Contact Humans with Tools)**: Human checkpoints as structured intervention points

See [Debate Mode Design](https://github.com/existential-birds/amelia/issues/202) for detailed specification.

---

## Phase 13: Knowledge Library [Planned]

*Co-learning system where developers and agents share framework knowledge*

A shared knowledge base that helps developers learn frameworks while providing agents with documentation context for better code generation.

**Key Capabilities:**
- Framework documentation ingestion and indexing
- Chat-based Q&A grounded in official docs
- Contextual code explanations ("Explain" button on agent-generated code)
- Agent RAG integration for pertinent retrieval during tasks

**12-Factor Compliance:**
- **F3 (Own Context Window)**: Framework docs become structured context for code generation
- **F13 (Pre-fetch Context)**: Relevant documentation pre-fetched based on task keywords

See [Knowledge Library Design](https://github.com/existential-birds/amelia/issues/203) for detailed specification.

---

## Phase 14: Capitalization Tracking [Planned]

*Attribute engineering work to initiatives for financial reporting*

Map PRs and issues to capitalizable initiatives, estimate engineering hours from workflow execution, and produce auditable reports for finance.

**Key Capabilities:**
- Initiative resolution from JIRA Epics or GitHub Projects
- Hours estimation from workflow execution timestamps
- OPEX vs CAPEX classification per initiative
- CLI and dashboard reporting with full audit trails

**12-Factor Compliance:**
- **F5 (Unified State)**: Workflow timestamps and initiative mappings stored alongside execution state

---

## Phase 15: Cloud Deployment [Planned]

*Parallel workflow execution in the cloud*

Deploy Amelia to AWS to enable parallel workflow execution without local resource limitations, while preserving local-only mode as the default.

**Key Capabilities:**
- Multiple workflows running in parallel (not limited by local resources)
- Thin CLI client for submitting and monitoring workflows
- Web dashboard connectivity to cloud backend
- OAuth-based authentication with GitHub

**12-Factor Compliance:**
- **F6 (Launch/Pause/Resume)**: Cloud-scale parallel execution with simple launch APIs
- **F11 (Trigger from Anywhere)**: Web dashboard and CLI both connect to cloud backend
- **F12 (Stateless Reducer)**: Cloud deployment requires fully serializable, stateless workflow execution

---

## Phase 16: Security Guardrails [Planned]

*Defense-in-depth security for enterprise deployment*

Layered security controls that protect against prompt injection, tool misuse, and unauthorized actions.

**Key Capabilities:**
- Deterministic guardrails blocking high-risk operations without human confirmation
- Reasoning-based defenses with optional guard model before execution
- Tool parameter validation callbacks for inspection and modification
- MCP security: explicit allowlists, collision detection, taint tracking

**12-Factor Compliance:**
- **F7 (Contact Humans with Tools)**: High-risk operations pause for human approval
- **F9 (Compact Errors)**: Security violations produce structured audit events

See [Security Guardrails Layer](https://github.com/existential-birds/amelia/issues/228) for detailed specification.

---

## Phase 17: Context Window Management [Planned]

*Token budget enforcement and context compaction for long workflows*

Strategies for managing context limits during complex, multi-phase workflows.

**Key Capabilities:**
- Configurable compaction strategies (last N turns, token-based, recursive summarization)
- Async background compaction to avoid blocking execution
- Compaction tracking (know which events are summarized vs original)
- Token budget alerts and per-phase limits

**12-Factor Compliance:**
- **F3 (Own Context Window)**: Full control over what enters LLM context
- **F5 (Unified State)**: Compaction metadata stored with workflow state

See [Context Window Management](https://github.com/existential-birds/amelia/issues/229) for detailed specification.

---

## Phase 18: Evaluation CI/CD [Planned]

*Automated quality gates for agent releases*

Systematic evaluation framework ensuring agent quality before deployment.

**Key Capabilities:**
- Pre-merge CI evaluation suite for agent quality
- Golden dataset management (typical, edge, adversarial scenarios)
- LLM-as-Judge integration for nuanced quality assessment
- Production failure to regression test pipeline

**12-Factor Compliance:**
- **F9 (Compact Errors)**: Test failures become structured context for improvement
- **F2 (Own Your Prompts)**: Evaluation enables safe prompt iteration

See [Evaluation CI/CD Integration](https://github.com/existential-birds/amelia/issues/230) for detailed specification.

---

## Phase 19: Agent Identity & Authorization [Planned]

*Per-agent permissions and audit trails*

Least-privilege security model with comprehensive audit logging.

**Key Capabilities:**
- Per-agent tool allowlists (Architect: read-only, Developer: write, Reviewer: read+comment)
- Audit logging of all tool calls with agent identity
- Blast radius containment for compromised agents
- Runtime enforcement with clear error messages

**12-Factor Compliance:**
- **F10 (Small Focused Agents)**: Clear capability boundaries per agent type

See [Agent Identity & Authorization](https://github.com/existential-birds/amelia/issues/231) for detailed specification.

---

## Phase 20: Distributed Tracing [Planned]

*End-to-end observability across agents*

Full tracing infrastructure for debugging and performance analysis.

**Key Capabilities:**
- Trace ID propagation across all agents and tools
- Causal path visualization (parent-child relationships)
- Dashboard trace view with waterfall charts
- Performance profiling per agent and tool

**12-Factor Compliance:**
- **F5 (Unified State)**: Trace IDs become part of event schema

See [Distributed Tracing](https://github.com/existential-birds/amelia/issues/232) for detailed specification.

---

## Phase 21: Closing the 12-Factor Loop [Future]

*Architectural refinements for full methodology compliance*

After the core product features are complete, these technical refinements close remaining gaps with the [12-Factor Agents](https://github.com/humanlayer/12-factor-agents) methodology. These are architectural improvements, not user-facing features.

### Current Compliance After Phase 20

| Factor | Status | Primary Phases |
|--------|--------|----------------|
| F1: Natural Language → Tool Calls | ✅ Strong | Phase 1 |
| F2: Own Your Prompts | ✅ Strong | Phase 10, 18 |
| F3: Own Your Context Window | ✅ Strong | Phase 3, 11, 13, 17 |
| F4: Tools = Structured Outputs | ✅ Strong | Phase 1 |
| F5: Unified State | ✅ Strong | Phase 2, 3, 17, 20 |
| F6: Launch/Pause/Resume | ✅ Strong | Phase 2, 3, 8, 9, 15 |
| F7: Contact Humans with Tools | ✅ Strong | Phase 9, 12, 16 |
| F8: Own Your Control Flow | ✅ Strong | Phase 1 |
| F9: Compact Errors | ✅ Strong | Phase 4, 6, 7, 16, 18 |
| F10: Small Focused Agents | ✅ Strong | Phase 1, 7, 12, 19 |
| F11: Trigger from Anywhere | ✅ Strong | Phase 2, 5, 9, 15 |
| F12: Stateless Reducer | ⚠️ Partial | Phase 8, 15 |
| F13: Pre-fetch Context | ⚠️ Partial | Phase 11, 13 |

**Summary**: 11 Strong, 2 Partial

### Remaining Gaps

#### Gap 1: Prompt Templating System (F2)

**Current State**: Prompts are hardcoded strings in agent files (`SYSTEM_PROMPT = """..."""`).

**Gap**: No externalized prompt templates, versioning, or centralized registry. Phase 10 adds A/B testing but doesn't restructure where prompts live.

**Recommendation**:
- Externalize prompts to `prompts/{agent}/{role}.jinja2` files
- Add prompt registry with version tracking
- Enable runtime template selection without code changes

#### Gap 2: Structured Event Thread (F3)

**Current State**: Messages use simple `AgentMessage(role, content)` objects passed to LLM APIs.

**Gap**: Context is standard OpenAI message format, not optimized for token efficiency. No typed event threading, no context compaction for long-running workflows.

**Recommendation**:
- Implement `Thread` class with typed `Event` objects
- Custom XML/YAML serialization for token efficiency
- Add context compaction/summarization for workflows exceeding token limits

```python
# Target pattern
class Event:
    type: Literal["tool_call", "tool_result", "error", "human_response"]
    data: ToolCall | ToolResult | Error | HumanResponse

class Thread:
    events: list[Event]

def thread_to_context(thread: Thread) -> str:
    # Custom XML formatting for LLM consumption
```

#### Gap 3: True State Unification (F5)

**Current State**: State split between LangGraph in-memory checkpoints and SQLite `state_json` blob. Reconstruction requires both systems.

**Gap**: No single serializable object capturing everything—retry counts, error history, and execution metadata scattered across systems.

**Recommendation**:
- Unify into single `Thread` object (per Gap 2)
- Execution state (step, retries, waiting) inferred from event history
- Eliminate LangGraph `MemorySaver` in favor of explicit serialization

#### Gap 4: `request_human_input` Tool (F7)

**Current State**: Human contact hardcoded at graph nodes (`typer.confirm()` in CLI, REST endpoints in server). Agents cannot ask clarifying questions mid-workflow.

**Gap**: Phase 9 adds Slack/Discord channels but doesn't restructure human contact as tool calls. No structured mechanism for agents to request information.

**Recommendation**:
- Add `request_human_input` tool type that breaks execution loop
- Structured question format with urgency, options, and response type
- Webhook-based resume when human responds

```python
# Target pattern
class RequestHumanInput(BaseModel):
    intent: Literal["request_human_input"]
    question: str
    context: str
    urgency: Literal["low", "medium", "high"]
    format: Literal["yes_no", "multiple_choice", "free_text"]
    options: list[str] | None
    # Research-informed additions
    confidence: float  # Agent's confidence in proceeding without input
    stakes: Literal["low", "medium", "high"]  # Impact of wrong decision
    timeout_action: Literal["proceed", "wait", "fail"]  # What to do if no response
```

#### Gap 5: Error Self-Healing Loop (F9)

**Current State**: Errors logged via loguru and returned in `DeveloperResponse.error`, but not accumulated in context for retry.

**Gap**: No consecutive error counter, no retry thresholds, no automatic escalation after N failures. Errors don't feed back to LLM for self-correction.

**Recommendation**:
- Track errors in event thread (per Gap 2)
- Implement consecutive error counter with configurable threshold
- Escalate to human after threshold exceeded
- Consider hiding resolved errors from context

```python
# Target pattern
consecutive_errors = 0
while True:
    try:
        result = await handle_next_step(thread, next_step)
        consecutive_errors = 0
    except Exception as e:
        consecutive_errors += 1
        thread.events.append(Event(type="error", data=format_error(e)))
        if consecutive_errors >= 3:
            await escalate_to_human(thread)
            break
```

#### Gap 6: Immutable State Pattern (F12)

**Current State**: State mutations happen in-place within LangGraph nodes. Hidden state in driver sessions and subprocess handles.

**Gap**: Not a pure reducer pattern—state updates mutate existing objects rather than returning new instances. Complicates debugging and replay.

**Recommendation**:
- Refactor to immutable state updates (`state.with_tasks(new_tasks)`)
- Eliminate mutable shared state in `MemorySaver`
- Enable workflow replay from serialized event history

```python
# Target pattern (pure reducer)
def developer_node(state: State) -> State:
    new_tasks = [t.with_status("completed") if ... else t for t in state.tasks]
    return state.with_tasks(new_tasks)  # Returns new object
```

#### Gap 7: Automatic Code Pre-fetching (F13)

**Current State**: Issue context fetched once at start. No proactive fetching of codebase structure, existing tests, or CI status before Architect plans.

**Gap**: Phase 11 (Spec Builder) and Phase 13 (Knowledge Library) add document RAG, but don't pre-fetch code context. Architect doesn't see existing patterns, related tests, or recent commits.

**Recommendation**:
- Before Architect planning, automatically fetch:
  - Existing tests related to modified files
  - Similar features (semantic search on issue keywords)
  - Recent commits touching related code
  - CI pipeline status
- Include in Architect context for informed planning

---

## References

- [Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) - Anthropic's research on session continuity patterns
- [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) - Agent design principles
