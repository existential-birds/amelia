# Amelia Roadmap

> **Goal:** Agent orchestration for software development. Workflow control from issue to PR with security, observability, and automated quality gates.
>
> **Architecture:** [12-Factor Agents](https://github.com/humanlayer/12-factor-agents) methodology.
>
> **Track Progress:** [GitHub Project Board](https://github.com/orgs/existential-birds/projects/1)

## Design Principles

From [Anthropic's research on effective agent harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents):

1. **Model Improvement as Tailwind** - Prefer prompts over code, delegation over hardcoding
2. **Structured Handoffs** - Explicit state transfer for cross-session work
3. **One Feature at a Time** - Focused work with clear completion criteria
4. **Verify Before Declaring Done** - Agents test as humans would
5. **Incremental Accountability** - Every change is committed, logged, recoverable
6. **Environment as Truth** - Git history is the source of truth, not agent memory

---

## Completed

### Core Orchestration

LangGraph state machine coordinating specialized agents with human approval gates.

- Agent orchestration (Architect → Developer → Reviewer loop)
- Human approval gates before execution
- Multi-driver support (API via OpenRouter, CLI via Claude)
- GitHub and Jira issue tracker integrations (read-only)
- Phased execution for Developer agent with per-task context isolation ([#188](https://github.com/existential-birds/amelia/issues/188))
- Per-agent driver configuration ([#279](https://github.com/existential-birds/amelia/issues/279))
- Multiple workflow pipelines: implementation and review ([#260](https://github.com/existential-birds/amelia/issues/260))

### Web Dashboard

Local web interface for workflow visibility, approvals, and real-time updates.

- FastAPI server with PostgreSQL persistence ([#308](https://github.com/existential-birds/amelia/issues/308))
- REST API for workflow lifecycle (create, approve, reject, cancel, resume, replan)
- React dashboard with XyFlow workflow visualization
- WebSocket real-time events with auto-reconnect and backfill
- Event bus with subscription filtering and trace-level logging ([#227](https://github.com/existential-birds/amelia/issues/227))
- Quick Shot modal for launching workflows ([#248](https://github.com/existential-birds/amelia/issues/248))
- External plan import with file picker and async validation ([#346](https://github.com/existential-birds/amelia/issues/346), [#448](https://github.com/existential-birds/amelia/issues/448))
- Agent prompt configuration UI ([#182](https://github.com/existential-birds/amelia/issues/182))
- Token usage, cost, and duration tracking in dashboard ([#176](https://github.com/existential-birds/amelia/issues/176))
- Database-backed configuration replacing split YAML/ServerConfig ([#307](https://github.com/existential-birds/amelia/issues/307))

### Knowledge Library

RAG infrastructure for framework documentation, white papers, and specifications.

- Document ingestion (PDF, Markdown) ([#433](https://github.com/existential-birds/amelia/issues/433)–[#436](https://github.com/existential-birds/amelia/issues/436))
- Semantic search with source citations and tag filtering
- Dashboard UI with search, document management, and upload
- API endpoints for document CRUD and search

**Next:** DOCX/HTML ingestion, chat Q&A interface for document queries (see Phase 1 dependencies)

### Oracle Consulting System

Foundation for agents to query external knowledge sources with codebase context ([#280](https://github.com/existential-birds/amelia/issues/280)).

- Oracle agent with agentic consultation via `driver.execute_agentic()`
- FileBundler for gathering codebase files via glob patterns (git-aware, respects `.gitignore`)
- Token estimation with tiktoken (`cl100k_base`) for context management
- `OracleConsultation` state model with session metrics, cost tracking, and outcome recording
- `POST /api/oracle/consult` endpoint with path traversal prevention
- 6 WebSocket event types (`EventDomain.ORACLE`): started, thinking, tool call/result, completed, failed
- Pipeline state integration via `oracle_consultations` append-only reducer

### Spec Builder — Brainstorming

Document-assisted design tool for synthesizing specifications from research and requirements ([#204](https://github.com/existential-birds/amelia/issues/204)).

- Brainstorming chat interface with streaming (SpecBuilderPage dashboard + BrainstormService backend)
- Session management with persistence (create, list, delete, resume)
- Artifact generation from brainstorming sessions (design documents)
- Handoff from brainstorming to implementation pipeline via `Design` state
- Token usage and cost tracking per message
- Tool execution visualization (tool calls, results, reasoning blocks)

### Parallel Execution Foundation

Concurrent workflows with resource management.

- Concurrent workflows with configurable `max_concurrent` limit (default: 5)
- One-workflow-per-worktree constraint with path-based locking
- Batch workflow API (`POST /workflows/start-batch`) for starting multiple queued workflows
- Queue-and-execute pattern: `queue_workflow()` → `start_batch_workflows()`
- Background asyncio task execution with proper state tracking
- DevContainer sandbox for isolated agent execution ([#408](https://github.com/existential-birds/amelia/issues/408)–[#411](https://github.com/existential-birds/amelia/issues/411))

---

## Phase 1: Agent Integration & Context [In Progress]

Complete Oracle and Spec Builder integration into the agent workflow, plus context management improvements.

- Oracle dashboard UI for consultation requests and real-time event streaming
- Tool registration in driver abstraction for agent-initiated consultations
- Architect integration: Oracle consultation during `plan()` for library knowledge
- Reviewer integration: Oracle consultation during `agentic_review()` for pattern validation
- Automated context window management ([#229](https://github.com/existential-birds/amelia/issues/229))
- Automatic code pre-fetching before Architect planning:
  - Existing tests related to modified files
  - Similar features via semantic search
  - Recent commits touching related code
  - CI pipeline status

**Dependencies:** Knowledge Library + RLM processing for full capability

---

## Phase 2: RLM Document Processing [Planned]

Recursive Language Model (RLM) processing for documents exceeding context limits. Based on [Zhang, Khattab, Kraska (MIT CSAIL)](https://arxiv.org/abs/2503.09590).

- Hybrid mode: direct injection (<16K tokens) vs RLM processing (>16K or complex tasks)
- Structured tools: `search_pattern`, `get_section`, `chunk_by_size`, `chunk_by_structure`, `query_subset`, `summarize`
- `request_capability()` for signaling tool gaps → dashboard + analytics
- Session-scoped caching by `hash(tool + params)`
- Extended `OracleConsultation` model: `tools_used`, `recursive_calls`, `capability_requests`
- New events: `ORACLE_RLM_TOOL_CALL`, `ORACLE_CAPABILITY_REQUESTED`

**Dependencies:** Knowledge Library (provides documents)

---

## Phase 3: Quality Gates & Verification [Planned]

Automated verification before code reaches human reviewers.

**Foundation in place:**

- Configurable iteration limits (`max_retries`, `max_iterations`) with auto-halt
- Evaluator agent with decision matrix (IMPLEMENT, REJECT, DEFER, CLARIFY)
- Pre-push hook running lint, typecheck, test, and dashboard build
- Retry with exponential backoff for transient failures (`RetryConfig`, `_run_workflow_with_retry`)

- Error compaction/summarization before LLM re-invocation (review feedback currently fed verbatim)
- Pre-review gates integrated into agent workflow (not just git hooks)
- Evaluation CI/CD integration ([#230](https://github.com/existential-birds/amelia/issues/230))
- Specialized parallel reviewers (Security, Performance, Accessibility) ([#68](https://github.com/existential-birds/amelia/issues/68))
- Reviewer agent benchmark framework ([#8](https://github.com/existential-birds/amelia/issues/8))
- Self-reflection protocol: Developer self-reviews before Reviewer
- Security scan integration (SAST tools)
- Browser automation (Playwright) for E2E verification
- Configurable coverage thresholds with regression tracking

---

## Phase 4: Parallel Execution — Advanced Patterns [Planned]

Advanced concurrency patterns building on the parallel execution foundation.

- DAG-aware task scheduling within workflows
- Resource management (LLM rate limiting, compute allocation)
- **Sectioning pattern**: Parallel independent subtasks
- **Voting pattern**: Run high-stakes tasks multiple times for consensus
- Fire-and-forget completion notifications (currently WebSocket/dashboard only)

---

## Phase 5: Bidirectional Tracker Sync [Planned]

Full issue lifecycle management from CLI ([#64](https://github.com/existential-birds/amelia/issues/64)).

- Create, update, transition, and close issues via CLI
- Label, milestone, and related-issue management
- Bidirectional sync with conflict resolution

---

## Phase 6: Pull Request Lifecycle [Planned]

PR management from creation through merge ([#66](https://github.com/existential-birds/amelia/issues/66)).

- Generate PRs from task metadata with auto-assigned reviewers
- Fetch and address review comments with fixup commits
- Monitor CI status and auto-merge when approved
- Automatic branch cleanup post-merge

---

## Phase 7: Chat Integration & Notifications [Planned]

Slack/Discord interface for async workflow management ([#61](https://github.com/existential-birds/amelia/issues/61)).

- Approval buttons in chat
- Configurable notification verbosity and quiet hours
- Thread-per-workflow isolation
- `request_human_input` tool for agent-initiated questions (promotes F7 from partial to complete)
- Mobile pairing API for Volant iOS app ([#265](https://github.com/existential-birds/amelia/issues/265))

---

## Phase 8: Observability & Tooling [Planned]

Infrastructure for monitoring, debugging, and extending agent capabilities.

- Distributed tracing with OTel-compatible spans ([#232](https://github.com/existential-birds/amelia/issues/232))
- Observability metrics foundation (latency, throughput, error rates) ([#234](https://github.com/existential-birds/amelia/issues/234))
- Tool registry for dynamic tool discovery and registration ([#233](https://github.com/existential-birds/amelia/issues/233))
- Read-only DeepAgent mode via technical tool restriction ([#357](https://github.com/existential-birds/amelia/issues/357))

---

## Phase 9: Continuous Improvement [Planned]

Metrics and feedback for agent quality improvement ([#63](https://github.com/existential-birds/amelia/issues/63)).

**Foundation in place:**

- Success/failure tracking with `success_rate` in usage summaries
- Token usage and cost tracking per agent, model, and workflow (15+ models supported)
- Costs dashboard with trend charts, success rate badges, and model breakdown
- Reviewer structured output with severity classification (Critical/Major/Minor)

- Project-specific knowledge base (idioms, pitfalls, decisions)
- Prompt A/B testing with benchmark suite
- Pre-merge evaluation CI for agent quality
- LLM-as-Judge for nuanced quality assessment

---

## Phase 10: Debate Mode [Planned]

Multi-agent deliberation for design decisions ([#202](https://github.com/existential-birds/amelia/issues/202)).

- Moderator assigns perspectives to debater agents
- Parallel debate rounds with convergence detection
- Human checkpoints for guidance injection
- Synthesis documents with recommendations and confidence levels

---

## Phase 11: Security & Authorization [Planned]

Defense-in-depth security with per-agent permissions ([#228](https://github.com/existential-birds/amelia/issues/228), [#231](https://github.com/existential-birds/amelia/issues/231)).

**Foundation in place:**

- Path traversal prevention in worktree and file operations
- `allowed_tools` parameter on `execute_agentic()` for per-agent tool restriction ([#356](https://github.com/existential-birds/amelia/issues/356))

- Deterministic guardrails blocking high-risk operations
- Per-agent tool allowlists (Architect: read-only, Developer: write, Reviewer: read+comment)
- Configurable risk levels per profile (Prototype/Demo/Production) ([#219](https://github.com/existential-birds/amelia/issues/219))
- Reasoning-based defenses with optional guard model
- Tool-call-level audit logging with agent identity
- MCP security: explicit allowlists, collision detection, taint tracking

---

## Phase 12: Cloud Deployment [Planned]

Parallel execution on cloud infrastructure.

- Multiple workflows running in parallel on AWS
- Thin CLI client for submitting and monitoring
- OAuth-based authentication with GitHub

---

## Phase 13: Capitalization Tracking [Planned]

Engineering work attribution for financial reporting (OPEX vs CAPEX) ([#70](https://github.com/existential-birds/amelia/issues/70)).

- Initiative resolution from JIRA Epics or GitHub Projects
- Hours estimation from workflow timestamps
- OPEX vs CAPEX classification
- CLI and dashboard reporting with audit trails

---

## 12-Factor Compliance Summary

| Factor | Status | Primary Phases | Notes |
|--------|--------|----------------|-------|
| F1: Natural Language → Tool Calls | 🟡 Partial | Core Orchestration | Evaluator/Knowledge use Pydantic schemas; core agents (Architect/Developer/Reviewer) use free-form agentic mode |
| F2: Own Your Prompts | ✅ Complete | Core Orchestration | Full versioning system with DB persistence, `PromptResolver`, workflow audit linking |
| F3: Own Your Context Window | 🚧 In Progress | Phases 1, 2 | Task sectioning exists; no token counting or context budgeting |
| F4: Tools = Structured Outputs | 🟡 Partial | Core Orchestration, Phase 8 | Canonical `ToolName` registry; tool schemas owned by driver frameworks, not Amelia |
| F5: Unified State | ✅ Complete | Web Dashboard | Frozen `BasePipelineState` → `ImplementationState` hierarchy with LangGraph reducers |
| F6: Launch/Pause/Resume | ✅ Complete | Web Dashboard | 8 REST endpoints, LangGraph `interrupt_before`, PostgreSQL checkpointing |
| F7: Contact Humans with Tools | 🟡 Partial | Phases 7, 10, 11 | `human_approval_node` exists; agents cannot initiate contact mid-execution; no outbound notifications |
| F8: Own Your Control Flow | ✅ Complete | Core Orchestration | Custom routing functions with business logic, two pipeline graphs |
| F9: Compact Errors | 🟡 Partial | Phases 3, 8 | Exponential backoff retry exists; no error compaction for LLM context |
| F10: Small Focused Agents | ✅ Complete | Core Orchestration | 4 narrow agents, step limits, per-task fresh sessions |
| F11: Trigger from Anywhere | 🟡 Partial | Web Dashboard, Phase 7 | CLI + REST + Dashboard; no inbound webhooks or event-driven triggers |
| F12: Stateless Reducer | ✅ Complete | Core Orchestration | Frozen Pydantic state, `operator.add` reducers, pure node functions |
| F13: Pre-fetch Context | 🟡 Partial | Phase 1 | Issue/commit/design/prompts pre-fetched; codebase context via runtime exploration |

**Current:** 5 Complete, 1 In Progress, 7 Partial

---

## References

- [Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) - Anthropic
- [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) - Anthropic
- [Recursive Language Models](https://arxiv.org/abs/2503.09590) - Zhang, Khattab, Kraska (MIT CSAIL)
