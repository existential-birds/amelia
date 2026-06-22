# 03 — Workstream C: Context Engine

**Goal:** give Amelia Hermes-style context management — first measure how full the window is
(#505), then compact long workflows so they don't silently grow until they hit the model limit
and fail (#229). In Hermes this is the **pluggable context engine** with lossy trajectory
compression + session lineage (reference: `~/github/reference_agents/hermes-agent/agent/context_compressor.py`
and `trajectory_compressor.py` — strategy: protect first + last-N turns, summarize the middle,
emit a new session referencing `parent_session_id`).

There is **no pre-written C design doc** — #505 is simple enough to go straight to
implementation; #229 warrants a short design pass first (see below). C touches drivers/tokens,
so it is **independent of Workstream B** and runs concurrently.

## The two issues

| Issue | Role |
|---|---|
| **#505** Context window metadata + utilization tracking | **Foundation** — you can't compact what you don't measure. Build first. |
| **#229** Automated Context Window Management (compaction) | Depends on #505. The actual compaction. |

Authoritative text: `gh issue view 505` · `gh issue view 229`.

## #505 — what to build (foundational, one agent, straight to implementation)

- **Model context-window sizes** alongside existing pricing in `amelia/server/models/tokens.py`
  (the file already has pricing for 15+ models — add a `context_window` per model, e.g. Claude
  Sonnet 200K, GPT-4o 128K, minimax/minimax-m2 per its spec).
- **Real-time utilization** — track cumulative token count against the window during agent
  execution in `amelia/drivers/api/deepagents.py` (`ApiDriver._sessions`).
- **Expose it on the driver interface** — `amelia/drivers/base.py` (`DriverInterface`), so callers
  can read utilization.
- **Dashboard gauge** — `dashboard/src/pages/CostsPage.tsx` (complements the existing cost/token
  charts): show context-window fill level per active workflow.
- **Threshold alerts** — configurable warning (e.g. 80%).
- **Out of scope for #505:** compaction/summarization/pruning — that's #229.

ACCEPTANCE (observable): for a known model + a session with known token usage, the driver reports
the correct utilization fraction; the dashboard renders a gauge; crossing the threshold emits the
alert event. Backend + a dashboard test (`pnpm test:run`). Remember the fresh-worktree
`pnpm install` for the dashboard build.

## #229 — what to build (depends on #505; do a short design pass first)

This is bigger and has a real trap, so **consider spawning one quick design-spike agent** (like
the prior session did for Workstream B) to settle the compaction strategy before implementing —
or scope it to Phase 2 only and defer Phase 3.

### The trap: append-only LangGraph reducers
`ImplementationState.tool_calls` / `tool_results` (`amelia/pipelines/implementation/state.py`)
are **append-only via `operator.add` reducers** — there is no pruning path. A "keep last N turns"
strategy needs a **custom reducer** (or an explicit compaction node that rewrites state), not just
slicing a list. Design this explicitly; it's the crux of #229 Phase 2.

### Phase 2 — simple compaction (recommended scope for this session)
- Configurable "keep last N turns" for `tool_calls`/`tool_results` (custom reducer or compaction node).
- **Token-aware** tool-output truncation (today's truncation in `ApiDriver` is 100KB **byte**-based
  and API-driver-only — make it token-aware).
- Automatic compaction trigger at a token threshold (uses #505's utilization).
- Token-budget config — per-profile / per-agent (e.g. `AMELIA_MAX_CONTEXT_TOKENS`).

### Phase 3 — smart compaction (recommend deferring to a follow-up PR)
- LLM-generated summaries of old segments (Hermes-style: protect first + last-N, summarize middle).
- Preserve key decisions; track provenance (summary vs original); async/background so it doesn't
  block agent execution.

### Integration points (from the issue)
| Component | File |
|---|---|
| ImplementationState (append-only reducers) | `amelia/pipelines/implementation/state.py` |
| Developer prompt assembly | `amelia/agents/developer.py` (`_build_prompt`) |
| ApiDriver sessions (full history, no truncation) | `amelia/drivers/api/deepagents.py` |
| DriverInterface | `amelia/drivers/base.py` (`execute_agentic`) |
| EventBus (emit "compacted" markers) | `amelia/server/events/bus.py` |
| Model pricing + window sizes | `amelia/server/models/tokens.py` (from #505) |

ACCEPTANCE (observable): a workflow that would exceed the window gets compacted and **continues
successfully** (not "compaction ran" — assert the workflow completes and the post-compaction
state preserves the protected turns + a summary marker); token-aware truncation cuts on token
count, verified against a known tokenizer; the trigger fires at the configured threshold.

## Sequencing (stacked, mirrors Workstream B)

```
#505  → branch feat/505-context-window-metadata, PR (foundation).
#229  → based on the #505 branch (it reads window sizes + utilization). Stacked PR.
        (Optionally: one design-spike agent for the compaction strategy before the build.)
```

Same stacking mechanic as B (see `02-workstream-b-tool-registry.md` → "Sequencing"): the #229
agent bases its branch on `origin/feat/505-...` and opens its PR with `--base` that branch, noting
"Depends on #505". Tell the user to merge #505 first.

## Parallelism note
Run **Workstream B (#233 first) and Workstream C (#505 first) concurrently** — different
subsystems, no file overlap. That's two foundational agents in the first wave (well under the
~3–4 concurrent-heavy-agent ceiling from the playbook), then each fans out its dependents.
