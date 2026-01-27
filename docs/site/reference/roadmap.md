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

## Phase 1: Core Orchestration [Complete]

LangGraph state machine coordinating specialized agents with human approval gates.

**Capabilities:**

- Agent orchestration (Architect → Developer → Reviewer loop)
- Human approval gates before execution
- Multi-driver support (API via OpenRouter, CLI via Claude)
- GitHub and Jira issue tracker integrations (read-only)

**12-Factor Compliance:** F1 (NL→Tools), F4 (Structured Outputs), F8 (Own Control Flow), F10 (Small Agents), F12 (Stateless Reducer)

---

## Phase 2: Web Dashboard [Complete]

Local web interface for workflow visibility, approvals, and real-time updates.

**Capabilities:**

- FastAPI server with SQLite persistence (WAL mode)
- REST API for workflow lifecycle (create, approve, reject, cancel)
- React dashboard with XyFlow workflow visualization
- WebSocket real-time events with auto-reconnect and backfill
- Event bus with subscription filtering and trace-level logging

**12-Factor Compliance:** F5 (Unified State), F6 (Launch/Pause/Resume), F11 (Trigger from Anywhere)

---

## Phase 3: Oracle Consulting System [In Progress]

Foundation for agents to query external knowledge sources with codebase context.

**Completed:**

- Oracle agent with agentic consultation via `driver.execute_agentic()`
- FileBundler for gathering codebase files via glob patterns (git-aware, respects `.gitignore`)
- Token estimation with tiktoken (`cl100k_base`) for context management
- `OracleConsultation` state model with session metrics, cost tracking, and outcome recording
- `POST /api/oracle/consult` endpoint with path traversal prevention
- 6 WebSocket event types (`EventDomain.ORACLE`): started, thinking, tool call/result, completed, failed
- Pipeline state integration via `oracle_consultations` append-only reducer
- Comprehensive test suite (226+ test cases)

**Remaining:**

- Dashboard UI for consultation requests and real-time event streaming
- Tool registration in driver abstraction for agent-initiated consultations
- Integration with Architect/Developer/Reviewer agents

**12-Factor Compliance:** F3 (Own Context Window)

---

## Phase 4: Knowledge Library [Planned]

RAG infrastructure for framework documentation, white papers, and specifications.

**Capabilities:**

- Document ingestion (PDF, DOCX, Markdown, HTML)
- Semantic search with source citations
- Framework documentation indexing
- Chat Q&A interface for document queries

**Dependencies:** Phase 3 (Oracle queries Knowledge Library for docs)

**12-Factor Compliance:** F3 (Own Context Window)

See [Knowledge Library Design](https://github.com/existential-birds/amelia/issues/203).

---

## Phase 5: RLM Document Processing [Planned]

Recursive Language Model approach for processing documents exceeding context limits.

Based on [Recursive Language Models](https://arxiv.org/abs/2503.09590) (Zhang, Khattab, Kraska - MIT CSAIL): treats long documents as external objects manipulated through structured operations rather than direct prompt injection.

**Capabilities:**

- Hybrid mode: direct injection (<16K tokens) vs RLM processing (>16K or complex tasks)
- Structured tools: `search_pattern`, `get_section`, `chunk_by_size`, `chunk_by_structure`, `query_subset`, `summarize`
- `request_capability()` for signaling tool gaps → dashboard + analytics
- Session-scoped caching by `hash(tool + params)`
- Extended `OracleConsultation` model: `tools_used`, `recursive_calls`, `capability_requests`
- New events: `ORACLE_RLM_TOOL_CALL`, `ORACLE_CAPABILITY_REQUESTED`

**Dependencies:** Phase 4 (Knowledge Library provides documents)

**12-Factor Compliance:** F3 (Own Context Window)

See [RLM Integration Design](../plans/2026-01-17-rlm-integration-design.md).

---

## Phase 6: Spec Builder [In Progress]

Document-assisted design tool for synthesizing specifications from research and requirements.

**Completed:**

- Brainstorming chat interface with streaming (SpecBuilderPage dashboard + BrainstormService backend)
- Session management with persistence (create, list, delete, resume)
- Artifact generation from brainstorming sessions (design documents)
- Handoff from brainstorming to implementation pipeline via `Design` state
- Token usage and cost tracking per message
- Tool execution visualization (tool calls, results, reasoning blocks)

**Remaining:**

- Architect integration: Oracle consultation during `plan()` for library knowledge
- Reviewer integration: Oracle consultation during `agentic_review()` for pattern validation
- White paper and RFC synthesis into spec templates
- Automatic code pre-fetching before Architect planning:
  - Existing tests related to modified files
  - Similar features via semantic search
  - Recent commits touching related code
  - CI pipeline status

**Dependencies:** Phases 4, 5 (Knowledge Library + RLM processing) for full capability

**12-Factor Compliance:** F3 (Own Context Window), F13 (Pre-fetch Context)

See [Spec Builder Design](https://github.com/existential-birds/amelia/issues/204).

---

## Phase 7: Quality Gates & Verification [Planned]

Automated verification before code reaches human reviewers.

**Foundation in place:**

- Consecutive error tracking with automatic escalation (`consecutive_errors` in state)
- Configurable iteration limits (`max_retries`, `max_iterations`) with auto-halt
- Evaluator agent with decision matrix (IMPLEMENT, REJECT, DEFER, CLARIFY)
- Extension hooks for policy enforcement (`PolicyHook`, `AuditExporter`)
- Pre-push hook running lint, typecheck, test, and dashboard build

**Remaining:**

- Pre-review gates integrated into agent workflow (not just git hooks)
- Security scan integration (SAST tools)
- Browser automation (Playwright) for E2E verification
- Self-reflection protocol: Developer self-reviews before Reviewer
- Specialized reviewers (Security, Performance, Accessibility) in parallel
- Configurable coverage thresholds with regression tracking

**12-Factor Compliance:** F9 (Compact Errors), F10 (Small Focused Agents)

---

## Phase 8: Bidirectional Tracker Sync [Planned]

Full issue lifecycle management from CLI.

**Capabilities:**

- Create, update, transition, and close issues via CLI
- Label, milestone, and related-issue management
- Bidirectional sync with conflict resolution

**12-Factor Compliance:** F11 (Trigger from Anywhere)

---

## Phase 9: Pull Request Lifecycle [Planned]

PR management from creation through merge.

**Capabilities:**

- Generate PRs from task metadata with auto-assigned reviewers
- Fetch and address review comments with fixup commits
- Monitor CI status and auto-merge when approved
- Automatic branch cleanup post-merge

**12-Factor Compliance:** F6 (Launch/Pause/Resume), F9 (Compact Errors)

---

## Phase 10: Parallel Execution [In Progress]

Concurrent workflows with resource management.

**Completed:**

- Concurrent workflows with configurable `max_concurrent` limit (default: 5)
- One-workflow-per-worktree constraint with path-based locking
- Batch workflow API (`POST /workflows/start-batch`) for starting multiple queued workflows
- Queue-and-execute pattern: `queue_workflow()` → `start_batch_workflows()`
- Background asyncio task execution with proper state tracking

**Remaining:**

- DAG-aware task scheduling within workflows
- Resource management (LLM rate limiting, compute allocation)
- **Sectioning pattern**: Parallel independent subtasks
- **Voting pattern**: Run high-stakes tasks multiple times for consensus
- Fire-and-forget completion notifications (currently WebSocket/dashboard only)

**12-Factor Compliance:** F5 (Unified State), F6 (Launch/Pause/Resume), F12 (Stateless Reducer)

---

## Phase 11: Chat Integration [Planned]

Slack/Discord interface for async workflow management.

**Capabilities:**

- Approval buttons in chat
- Configurable notification verbosity and quiet hours
- Thread-per-workflow isolation
- `request_human_input` tool for agent-initiated questions

**12-Factor Compliance:** F6 (Launch/Pause/Resume), F7 (Contact Humans with Tools), F11 (Trigger from Anywhere)

---

## Phase 12: Continuous Improvement [Planned]

Metrics and feedback for agent quality improvement.

**Foundation in place:**

- Success/failure tracking with `success_rate` in usage summaries
- Token usage and cost tracking per agent, model, and workflow (15+ models supported)
- Costs dashboard with trend charts, success rate badges, and model breakdown
- Reviewer structured output with severity classification (Critical/Major/Minor)

**Remaining:**

- Project-specific knowledge base (idioms, pitfalls, decisions)
- Prompt A/B testing with benchmark suite
- Pre-merge evaluation CI for agent quality
- LLM-as-Judge for nuanced quality assessment

**12-Factor Compliance:** F2 (Own Your Prompts), F9 (Compact Errors)

---

## Phase 13: Debate Mode [Planned]

Multi-agent deliberation for design decisions.

**Capabilities:**

- Moderator assigns perspectives to debater agents
- Parallel debate rounds with convergence detection
- Human checkpoints for guidance injection
- Synthesis documents with recommendations and confidence levels

**12-Factor Compliance:** F7 (Contact Humans with Tools), F10 (Small Focused Agents)

See [Debate Mode Design](https://github.com/existential-birds/amelia/issues/202).

---

## Phase 14: Capitalization Tracking [Planned]

Engineering work attribution for financial reporting (OPEX vs CAPEX).

**Capabilities:**

- Initiative resolution from JIRA Epics or GitHub Projects
- Hours estimation from workflow timestamps
- OPEX vs CAPEX classification
- CLI and dashboard reporting with audit trails

**12-Factor Compliance:** F5 (Unified State)

---

## Phase 15: Cloud Deployment [Planned]

Parallel execution on cloud infrastructure.

**Capabilities:**

- Multiple workflows running in parallel on AWS
- Thin CLI client for submitting and monitoring
- OAuth-based authentication with GitHub

**12-Factor Compliance:** F6 (Launch/Pause/Resume), F11 (Trigger from Anywhere), F12 (Stateless Reducer)

---

## Phase 16: Security & Authorization [Planned]

Defense-in-depth security with per-agent permissions.

**Foundation in place:**

- Extension protocol system: `PolicyHook`, `AuthProvider`, `AuditExporter`, `AnalyticsSink`
- `ExtensionRegistry` for registering enterprise security hooks
- Policy enforcement at workflow start (`check_policy_workflow_start()`)
- Audit event broadcasting to all registered exporters
- Path traversal prevention in worktree and file operations
- No-op implementations for graceful degradation without extensions

**Remaining:**

- Deterministic guardrails blocking high-risk operations
- Per-agent tool allowlists (Architect: read-only, Developer: write, Reviewer: read+comment)
- Reasoning-based defenses with optional guard model
- Tool-call-level audit logging with agent identity
- MCP security: explicit allowlists, collision detection, taint tracking

**12-Factor Compliance:** F7 (Contact Humans with Tools), F9 (Compact Errors), F10 (Small Focused Agents)

See [Security Guardrails Layer](https://github.com/existential-birds/amelia/issues/228) and [Agent Identity & Authorization](https://github.com/existential-birds/amelia/issues/231).

---

## 12-Factor Compliance Summary

| Factor | Status | Primary Phases |
|--------|--------|----------------|
| F1: Natural Language → Tool Calls | ✅ Complete | Phase 1 |
| F2: Own Your Prompts | ✅ Complete | Phase 12 |
| F3: Own Your Context Window | 🚧 In Progress | Phases 3, 4, 5, 6 |
| F4: Tools = Structured Outputs | ✅ Complete | Phase 1 |
| F5: Unified State | ✅ Complete | Phase 2 |
| F6: Launch/Pause/Resume | ✅ Complete | Phase 2 |
| F7: Contact Humans with Tools | 🔄 Planned | Phases 11, 13, 16 |
| F8: Own Your Control Flow | ✅ Complete | Phase 1 |
| F9: Compact Errors | 🔄 Planned | Phase 7 |
| F10: Small Focused Agents | ✅ Complete | Phase 1 |
| F11: Trigger from Anywhere | ✅ Complete | Phase 2 |
| F12: Stateless Reducer | ✅ Complete | Phase 1 |
| F13: Pre-fetch Context | 🔄 Planned | Phase 6 |

**Current:** 9 Complete, 1 In Progress, 3 Planned

---

## References

- [Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) - Anthropic
- [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) - Anthropic
- [Recursive Language Models](https://arxiv.org/abs/2503.09590) - Zhang, Khattab, Kraska (MIT CSAIL)
