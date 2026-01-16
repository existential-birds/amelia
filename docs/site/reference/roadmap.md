# Amelia Roadmap

> **Vision:** Enterprise-grade agent orchestration for software development. Complete workflow control from issue to PR, with defense-in-depth security, comprehensive observability, and automated quality gates.
>
> **Architecture:** Aligned with the [12-Factor Agents](https://github.com/humanlayer/12-factor-agents) methodology.
>
> **Track Progress:** [GitHub Project Board](https://github.com/orgs/existential-birds/projects/1)

## Design Principles

Informed by [Anthropic's research on effective agent harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents):

1. **Model Improvement as Tailwind** - Prefer prompts over code, delegation over hardcoding
2. **Structured Handoffs** - Explicit state transfer for cross-session work
3. **One Feature at a Time** - Focused work with clear completion criteria
4. **Verify Before Declaring Done** - Agents test as humans would
5. **Incremental Accountability** - Every change is committed, logged, recoverable
6. **Environment as Truth** - Git history is the source of truth, not agent memory

## Research Foundation

| Research Finding | Impact |
|------------------|--------|
| Orchestrator-worker: 90.2% improvement (Anthropic) | Phase 1 architecture |
| Reflexion: 91% vs 80% on coding (Shinn et al.) | Self-reflection protocol |
| Multi-agent: ~15× token cost | Token budget enforcement |
| Sectioning vs Voting patterns | Parallelization strategies |

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

Specialized AI agents working in sequence with approval gates before code ships.

**Capabilities:**
- Agent orchestration via LangGraph state machine (Architect → Developer → Reviewer loop)
- Human approval gates before execution
- Multi-driver support (API via OpenRouter, CLI via Claude)
- GitHub and Jira issue tracker integrations (read-only)

**12-Factor Compliance:** F1 (NL→Tools), F4 (Structured Outputs), F8 (Own Control Flow), F10 (Small Agents), F12 (Stateless Reducer)

---

## Phase 2: Web Dashboard [Complete]

*Observable orchestration through a local web interface*

Browser-based dashboard for workflow visibility, approvals, and real-time updates.

**Capabilities:**
- FastAPI server with SQLite persistence (WAL mode)
- REST API for workflow lifecycle (create, approve, reject, cancel)
- React dashboard with XyFlow workflow visualization
- WebSocket real-time events with auto-reconnect and backfill
- Event bus with subscription filtering and trace-level logging

**12-Factor Compliance:** F5 (Unified State), F6 (Launch/Pause/Resume), F11 (Trigger from Anywhere)

---

## Phase 3: Session & Context Management [Planned]

*Token budgets and structured handoffs for long-running work*

Consolidates session continuity and context window management into a unified approach.

**Capabilities:**
- Machine-readable progress artifacts persisted to repository
- Session kickoff protocol (verify environment, review history, select next task)
- Token budget enforcement with configurable limits per agent
- Compaction strategies (last N turns, recursive summarization)
- Async background compaction to avoid blocking execution

**Architectural Goal:** Implement `Thread` class with typed `Event` objects for token-efficient context serialization.

**12-Factor Compliance:** F3 (Own Context Window), F5 (Unified State), F6 (Launch/Pause/Resume)

---

## Phase 4: Quality Gates & Verification [Planned]

*Automated verification before code reaches human reviewers*

Combines pre-review automation with browser-based end-to-end testing.

**Capabilities:**
- Pre-review gates: lint, typecheck, test, security scan
- Browser automation (Playwright) for E2E verification
- Self-reflection protocol: Developer self-reviews before Reviewer
- Specialized reviewers (Security, Performance, Accessibility) running in parallel
- Configurable coverage thresholds with regression tracking
- Error self-healing: consecutive error tracking with automatic escalation

**12-Factor Compliance:** F9 (Compact Errors), F10 (Small Focused Agents)

---

## Phase 5: Bidirectional Tracker Sync [Planned]

*Full issue lifecycle management from CLI*

**Capabilities:**
- Create, update, transition, and close issues via CLI
- Label, milestone, and related-issue management
- Bidirectional sync with conflict resolution

**12-Factor Compliance:** F11 (Trigger from Anywhere)

---

## Phase 6: Pull Request Lifecycle [Planned]

*Complete PR management from creation through merge*

**Capabilities:**
- Generate PRs from task metadata with auto-assigned reviewers
- Fetch and address review comments with fixup commits
- Monitor CI status and auto-merge when approved
- Automatic branch cleanup post-merge

**12-Factor Compliance:** F6 (Launch/Pause/Resume), F9 (Compact Errors)

---

## Phase 7: Parallel Execution [Planned]

*Concurrent workflows with resource management*

**Capabilities:**
- Concurrent workflows on independent issues, each in isolated worktree
- DAG-aware task scheduling within workflows
- Resource management (LLM rate limiting, compute allocation)
- Fire-and-forget execution with notifications
- **Sectioning pattern**: Parallel independent subtasks
- **Voting pattern**: Run high-stakes tasks multiple times for consensus

**12-Factor Compliance:** F5 (Unified State), F6 (Launch/Pause/Resume), F12 (Stateless Reducer)

---

## Phase 8: Chat Integration [Planned]

*Async and mobile workflow management*

**Capabilities:**
- Slack/Discord interface with approval buttons
- Configurable notification verbosity and quiet hours
- Thread-per-workflow isolation
- `request_human_input` tool for agent-initiated questions with structured format

**12-Factor Compliance:** F6 (Launch/Pause/Resume), F7 (Contact Humans with Tools), F11 (Trigger from Anywhere)

---

## Phase 9: Continuous Improvement [Planned]

*Quality flywheel from metrics and feedback*

**Capabilities:**
- Success/failure tracking per agent, project, and task type
- Reviewer pattern detection for preemptive fixes
- Project-specific knowledge base (idioms, pitfalls, decisions)
- Prompt A/B testing with benchmark suite
- Pre-merge evaluation CI for agent quality
- LLM-as-Judge for nuanced quality assessment

**12-Factor Compliance:** F2 (Own Your Prompts), F9 (Compact Errors)

---

## Phase 10: Knowledge & Context Enrichment [Planned]

*Document RAG and automatic code pre-fetching*

Consolidates Spec Builder and Knowledge Library into unified context enrichment.

**Capabilities:**
- Document ingestion (PDF, DOCX, Markdown, HTML)
- Semantic search with source citations
- Framework documentation indexing and chat Q&A
- Automatic code pre-fetching before Architect planning:
  - Existing tests related to modified files
  - Similar features via semantic search
  - Recent commits touching related code
  - CI pipeline status

**12-Factor Compliance:** F3 (Own Context Window), F13 (Pre-fetch Context)

See [Spec Builder Design](https://github.com/existential-birds/amelia/issues/204) and [Knowledge Library Design](https://github.com/existential-birds/amelia/issues/203).

---

## Phase 11: Debate Mode [Planned]

*Multi-agent deliberation for design decisions*

**Capabilities:**
- Moderator assigns perspectives to debater agents
- Parallel debate rounds with convergence detection
- Human checkpoints for guidance injection
- Synthesis documents with recommendations and confidence levels

**12-Factor Compliance:** F7 (Contact Humans with Tools), F10 (Small Focused Agents)

See [Debate Mode Design](https://github.com/existential-birds/amelia/issues/202).

---

## Phase 12: Capitalization Tracking [Planned]

*Engineering work attribution for financial reporting*

**Capabilities:**
- Initiative resolution from JIRA Epics or GitHub Projects
- Hours estimation from workflow timestamps
- OPEX vs CAPEX classification
- CLI and dashboard reporting with audit trails

**12-Factor Compliance:** F5 (Unified State)

---

## Phase 13: Cloud Deployment [Planned]

*Parallel execution without local resource limits*

**Capabilities:**
- Multiple workflows running in parallel on AWS
- Thin CLI client for submitting and monitoring
- OAuth-based authentication with GitHub

**12-Factor Compliance:** F6 (Launch/Pause/Resume), F11 (Trigger from Anywhere), F12 (Stateless Reducer)

---

## Phase 14: Security & Authorization [Planned]

*Defense-in-depth security with per-agent permissions*

Consolidates security guardrails with agent identity management.

**Capabilities:**
- Deterministic guardrails blocking high-risk operations
- Per-agent tool allowlists (Architect: read-only, Developer: write, Reviewer: read+comment)
- Reasoning-based defenses with optional guard model
- Audit logging of all tool calls with agent identity
- MCP security: explicit allowlists, collision detection, taint tracking

**12-Factor Compliance:** F7 (Contact Humans with Tools), F9 (Compact Errors), F10 (Small Focused Agents)

See [Security Guardrails Layer](https://github.com/existential-birds/amelia/issues/228) and [Agent Identity & Authorization](https://github.com/existential-birds/amelia/issues/231).

---

## 12-Factor Compliance Summary

| Factor | Status | Primary Phases |
|--------|--------|----------------|
| F1: Natural Language → Tool Calls | ✅ Complete | Phase 1 |
| F2: Own Your Prompts | ✅ Complete | Phase 9 |
| F3: Own Your Context Window | 🔄 Planned | Phase 3, 10 |
| F4: Tools = Structured Outputs | ✅ Complete | Phase 1 |
| F5: Unified State | ✅ Complete | Phase 2 |
| F6: Launch/Pause/Resume | ✅ Complete | Phase 2 |
| F7: Contact Humans with Tools | 🔄 Planned | Phase 8, 11, 14 |
| F8: Own Your Control Flow | ✅ Complete | Phase 1 |
| F9: Compact Errors | 🔄 Planned | Phase 4 |
| F10: Small Focused Agents | ✅ Complete | Phase 1 |
| F11: Trigger from Anywhere | ✅ Complete | Phase 2 |
| F12: Stateless Reducer | ✅ Complete | Phase 1 |
| F13: Pre-fetch Context | 🔄 Planned | Phase 10 |

**Current:** 9 Complete, 4 Planned

---

## References

- [Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) - Anthropic
- [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) - Anthropic
