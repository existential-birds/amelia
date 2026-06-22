# 00 — Mission & Current State

## The long-term goal

Make **Amelia** functionally equivalent to the **Hermes agent framework**
(Nous Research; reference checkout at `~/github/reference_agents/hermes-agent/`, architecture
docs at https://hermes-agent.nousresearch.com/docs/developer-guide/architecture).

### The two architectures (why this is a *core inversion*, not a feature backlog)

**Hermes** is a *general-purpose, dynamically-routed, loosely-coupled agent runtime*. One
`AIAgent` ReAct loop serves every surface (CLI, gateway, batch, ACP, MCP). Its power is
**registry/plugin-shaped**:
- Self-registering **tool registry** (70+ tools, ~28 composable toolsets, `check_fn` permission
  gates, safe parallel dispatch).
- Multi-provider runtime resolution (18+ providers, 3 API modes, credential pools + fallback).
- Pluggable **context engines** (lossy trajectory compression with session lineage) + memory providers.
- **Batch + subagent parallelism** (`batch_runner` fan-out, `delegate_task`) — this is what the
  "500+ local agents" goal maps onto.
- Skills as markdown; platform-agnostic core.

**Amelia** is today a *rigid SWE pipeline*: a LangGraph state machine with
Architect→Developer↔Reviewer **baked into the state type**, three hardcoded pipelines,
one-workflow-per-worktree serialization, a dashboard/tracker product around it. Excellent at
one workflow; structurally unable to be a general agent.

"Make Amelia ≈ Hermes" therefore means: **replace the fixed graph with a dynamic agent loop,
lift tools/providers/context into registries, and make the runtime massively concurrent.**
Every issue is judged on whether it moves toward that inversion.

## Key amelia subsystems (where things live)

| Subsystem | Path | Notes |
|---|---|---|
| Pipelines (LangGraph) | `amelia/pipelines/` | `implementation/{graph,state,nodes}.py`, `registry.py` |
| Orchestrator | `amelia/server/orchestrator/service.py` | god-class, ~3,123 LOC (#603 decomposes it) |
| Agents | `amelia/agents/` | architect, developer, reviewer, evaluator, oracle |
| Drivers | `amelia/drivers/` | `api/deepagents.py` (OpenRouter/deepagents), `cli/claude.py`, `cli/codex.py` |
| Tools | `amelia/tools/` | shell_executor, git_utils, file_bundler, knowledge, write_plan |
| Tool constants | `amelia/core/constants.py` | `READONLY_TOOLS` preset (defined, **unconsumed**), tool name constants |
| Sandbox | `amelia/sandbox/` | `provider.py`, `docker.py`, `daytona.py`, `worker.py`, `driver.py` |
| Knowledge | `amelia/knowledge/` | embeddings, ingestion, search (pgvector) |
| Server/DB | `amelia/server/` | FastAPI, Postgres, event bus, token/usage models |
| Skills | `amelia/skills/review/` | markdown review guidelines |

## What the prior session did

### Closed 14 issues as "abandoned" (off the hermes-equivalence path)
Pipeline/dashboard polish: **#64, #66, #183, #195, #234, #520, #541, #546, #558, #559, #560,
#610, #627, #533**. (Comment used: "Closing as abandoned — this no longer fits the project's
current direction." Hermes was never mentioned, per user instruction.)
- Note: capabilities like auto-open-PR (#627) and good commit messages (#560) were closed as
  *issues* but their *capability* re-emerges for free as **registered tools** in Workstream B
  (`github_pr_create`, `git_commit` with message generation). Nothing was lost.

### Shipped the concurrency cluster as 7 PRs (the "500+ parallel agents" enabler)
All TDD'd, all passing the full pre-push gate on push:

| PR | Issue | Removes from hot path |
|----|----|----|
| #649 | #642 | Per-call chat-model/HTTP-client rebuild (handshake every call) |
| #650 | #640 | Per-step worker cold-start + 1–3s LangChain import (real Docker integration test passed) |
| #651 | #645 | 5 serial git probes → 1; off-loop shell subprocess |
| #652 | #643 | Serial 2N `gh` subprocesses → semaphore-bounded concurrent |
| #653 | #644 | Blocking tracker calls freezing the event loop |
| #654 | #646 | Per-review-type skill-file re-reads on the loop |
| #655 | #641 | Per-command Daytona session create/delete + `rm` round-trips |

**The user merges these before your session.** After merge, issues #640–#646 auto-close.

### Produced design docs + a de-risking spike (see README for paths)
- Workstream A design (dynamic core) — **not your scope**, future.
- Workstream B design (tool registry) — **your scope**.
- Workstream B middleware-veto spike — **answered YES**, B is unblocked.

## Open issues after the 7 PRs merge (10 remain)

| Issue | Title | Workstream | Status |
|---|---|---|---|
| **#233** | Tool Registry | **B** (foundation) | ready — build first |
| **#621** | Wire tools / `allowed_tools` / orphaned `knowledge_search` | **B** | ready — after #233 |
| **#357** | Read-only tool restriction | **B** | ready (de-risked by spike) — after #233 |
| **#228** | Security Guardrails Layer | **B** | ready — after #233 |
| **#505** | Context window metadata + utilization tracking | **C** (foundation) | ready — build first |
| **#229** | Automated Context Window Management (compaction) | **C** | after #505 |
| #98 | Planner agent → dynamic routing | A | future (after B+C) |
| #230 | Evaluation CI/CD Integration | E (safety net) | not scheduled |
| #544 | Notes ingestion endpoint | E (knowledge) | not scheduled, low coupling |
| #603 | Epic: structural cleanup of 1k+ line files | E | partially done; not scheduled |

**Your job this session: B (#233 → #621/#357/#228) and C (#505 → #229).** They touch different
subsystems (tools vs drivers/tokens) so B and C run in parallel.

## Dependency graph for this session

```
Workstream B:  #233 (registry spine) ──┬──> #621 (wiring)
                                       ├──> #357 (readonly toolset)
                                       └──> #228 (guardrails/policy)
                       (the three fan out in parallel once #233 lands)

Workstream C:  #505 (window metadata) ──> #229 (compaction)

B and C are independent of each other → run concurrently.
```
