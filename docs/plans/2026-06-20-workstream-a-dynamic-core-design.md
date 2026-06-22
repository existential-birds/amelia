# Workstream A — Dynamic Agent Core: Design

**Status:** Design (no implementation)
**Issue:** #98 (reframed: not pipeline-routing, but a dynamic agent runtime)
**Author:** Workstream A
**Date:** 2026-06-20

---

## 0. Problem statement

Amelia's orchestration is a **fixed LangGraph**. `ImplementationPipeline.create_graph()`
(`amelia/pipelines/implementation/graph.py:71`) wires six hardcoded nodes —
`architect_node → plan_validator_node → human_approval_node → developer_node →
reviewer_node → next_task_node` — connected by deterministic conditional routers
(`route_after_start`, `_route_after_plan_validation`, `_route_after_review_or_task`
in `implementation/routing.py`). The role sequence is baked into graph topology. Every
new workflow shape (e.g. "investigate-then-maybe-implement", "fan out N parallel fixes")
requires a new `StateGraph`, a new `Pipeline` subclass, and registry plumbing
(`pipelines/registry.py:15`, `PIPELINES: dict[str, type[Pipeline[Any]]]`).

The roles themselves are **already** thin: each agent (`Architect.plan`,
`Developer.run`, `Reviewer.agentic_review`, `Evaluator.evaluate`, `Oracle.consult`)
differs from the others only by (a) system prompt, (b) an injected structured-output
"submit" tool, and (c) which tools it may touch. The ReAct loop *already lives inside the
driver* — `ApiDriver.execute_agentic` (`drivers/api/deepagents.py:353`) calls
`create_deep_agent(...)` which runs the agentic loop. The LangGraph layer above it is a
deterministic state machine that calls these single-shot agentic runs in a fixed order.

**Goal:** replace the fixed graph with a single **ReAct-style supervisor loop** that
chooses *which role to act as / delegate to* at each step, where Architect / Developer /
Reviewer / Evaluator / Oracle become **toolset + skill + prompt profiles** rather than
graph nodes.

### Key finding that shapes everything

`create_deep_agent` (the `deepagents` library we already depend on) **natively accepts a
`subagents: list[SubAgent | CompiledSubAgent]` parameter and a `skills` parameter** (see
verified signature below). Amelia's `ApiDriver.execute_agentic` calls `create_deep_agent`
but **never passes `subagents`**. The dynamic-delegation primitive we need is one
unused keyword argument away.

```python
create_deep_agent(
    model, tools, *, system_prompt, middleware=(),
    subagents: list[SubAgent | CompiledSubAgent] | None = None,   # <-- unused today
    skills: list[str] | None = None,                              # <-- unused today
    response_format=..., checkpointer=..., backend=..., ...
) -> CompiledStateGraph
```

---

## 1. Competing designs for the dynamic core

The branch point the team must resolve: **keep LangGraph as the per-agent executor under a
dynamic supervisor, or rip it out for a hand-rolled ReAct loop.**

### Design A — "Supervisor over LangGraph subagents" (deepagents-native)

The supervisor is itself a `create_deep_agent` instance. Each role
(architect/developer/reviewer/...) is registered as a **`SubAgent`** in the supervisor's
`subagents=[...]` list. The supervisor's loop (run by deepagents/LangGraph internally)
emits a `task`/delegation tool call naming a subagent; deepagents spawns that subagent as
a child `CompiledStateGraph`, runs it to completion, and feeds its result back into the
supervisor's message history. We write **no loop code** — we configure subagent profiles
and let deepagents drive.

```
 amelia DynamicSupervisor
  = create_deep_agent(
        model, system_prompt=SUPERVISOR_PROMPT,
        tools=[<shared read tools>],
        subagents=[
            SubAgent(name="architect", prompt=ARCHITECT_PROMPT, tools=architect_toolset),
            SubAgent(name="developer", prompt=DEVELOPER_PROMPT, tools=developer_toolset),
            SubAgent(name="reviewer",  prompt=REVIEWER_PROMPT,  tools=reviewer_toolset),
            SubAgent(name="evaluator", ...), SubAgent(name="oracle", ...),
        ],
        skills=[...],            # Workstream B skill profiles
    )
```

- **Pros:** Minimal new code. We *delete* `graph.py`, the routers, and the
  `Architect/Developer/Reviewer` orchestration classes' run-ordering, keeping only their
  prompts + submit-tool schemas as profile data. Streaming, checkpointing, tool dispatch,
  and the ReAct loop are all reused from the library we already ship. The frozen-Pydantic +
  `operator.add` reducer problem (below) **disappears** because deepagents' internal state
  is `MessagesState`-style append, not amelia's `ImplementationState`.
- **Cons:** We inherit deepagents' opinions about delegation: subagent results come back as
  a flattened string in the parent transcript, not as typed `ReviewResult`/`EvaluationResult`
  Pydantic objects. Parallel fan-out semantics are whatever deepagents' `task` tool offers
  (one child per call), not our own. We are coupled to deepagents' `SubAgent` shape and its
  release cadence. Harder to express "500 parallel agents" if the library serializes
  delegation.

### Design B — "Hand-rolled ReAct supervisor, drivers as single-shot executors"

We write our own supervisor loop (`DynamicSupervisor.run`) modeled on Hermes'
`conversation_loop` (`reference_agents/hermes-agent/agent/conversation_loop.py:563`): a
`while iteration_budget.remaining and not done:` loop that calls the model with a tool
catalog, dispatches tool calls — including a first-class `delegate_task` tool modeled on
Hermes `tools/delegate_tool.py:2065` — and feeds results back. Role agents stay as
**single-shot agentic calls** through `Driver.execute_agentic`, but the *order and
selection* is decided by the loop, not a graph.

```python
class DynamicSupervisor:
    async def run(self, ctx: SupervisorContext) -> SupervisorResult:
        budget = IterationBudget(max_iterations=ctx.profile.max_iterations)  # cf. Hermes
        messages = [system, goal]
        while budget.consume():
            resp = await self._driver.execute_agentic(messages, tools=self._catalog, ...)
            if not resp.tool_calls:        # model emitted final answer -> done
                return SupervisorResult(...)
            for call in resp.tool_calls:
                if call.name == "delegate_task":
                    results = await self._spawn(call.args.tasks)   # parallel children
                else:
                    results = await self._dispatch_tool(call)
                messages.extend(results)
```

- **Pros:** Full control of delegation: `delegate_task(tasks=[...])` spawns N children as
  `asyncio` tasks bounded by a semaphore (the path to 500+ parallel agents). Subagent
  results stay typed — a reviewer child can return `ReviewResult` and we keep our Pydantic
  contracts. Driver-agnostic: works the same whether the underlying executor is the API
  (deepagents) or CLI driver. No coupling to deepagents' delegation opinions.
- **Cons:** We own the loop forever — retry/fallback, budget accounting, message
  sanitization, prompt-cache seams, error classification. Hermes' `conversation_loop.py`
  is 253k of exactly this surface; we'd be reimplementing a slice of it. Higher initial
  cost and more places to introduce bugs. We must rebuild streaming/event emission that
  GraphRunner currently gives us for free.

### Design C — "Hybrid: hand-rolled supervisor, deepagents per role"  ← **RECOMMENDED**

Write a **thin** hand-rolled supervisor loop (Design B's loop), but keep each role as a
`create_deep_agent` agentic run under `Driver.execute_agentic` (Design A's executors).
The supervisor owns *selection and delegation*; the driver owns *the inner ReAct turn of a
single role*. We do **not** use deepagents' `subagents=` for cross-role orchestration —
we use it only optionally within a role. Delegation is amelia's own `delegate_task` tool,
backed by `asyncio.gather` + a semaphore.

This is the recommendation because it cleanly resolves the frozen-state problem and the
500-agent requirement *without* surrendering typed role contracts or coupling our
orchestration to a third-party delegation model:

- The supervisor's working state is a **message list**, not `ImplementationState`. The
  `operator.add` reducers and `ConfigDict(frozen=True)` merge model that make LangGraph
  state composition rigid (`base.py:75`, `state.py:52`) are simply **not used** on the hot
  path. We keep `ImplementationState` only as the typed *result envelope* a workflow
  produces, populated at the end, not threaded through every node.
- Role outputs remain typed: a delegated reviewer returns `ReviewResult` via its existing
  `submit_review` submit-tool; the supervisor receives it as structured data, not a string.
- Delegation is ours, so "500 parallel agents" is a semaphore width, not a library default.

**Tradeoff we are explicitly accepting:** we hand-roll the supervisor loop (real cost,
~Design B), but we keep the per-role executor we already trust (deepagents), so the
hand-rolled surface is *just selection + delegation + budget*, an order of magnitude
smaller than Hermes' full loop. Pragmatist's objection: "Design A is less code today."
Perfectionist's objection: "Design A leaks deepagents' string-flattened delegation into
our typed domain and can't express bounded 500-wide fan-out." We side with the
perfectionist because delegation fidelity and concurrency are the entire point of #98.

### Why not keep the fixed graph at all?

The `operator.add` reducer model is the concrete blocker. LangGraph composes node return
values into frozen state via `Annotated[list[...], operator.add]`
(`pipelines/implementation/state.py:52-53`,
`pipelines/base.py:75-77`: `oracle_consultations: Annotated[list[OracleConsultation],
operator.add]`). This is **append-only accumulation keyed to a static node graph**. A
dynamic supervisor that may run the reviewer 0 or 7 times, or fan out 40 developers, has no
fixed reducer schema — you cannot pre-declare the `Annotated` fields for a topology decided
at runtime. Forcing dynamic control flow through LangGraph's reducer model means encoding a
dispatcher node with a self-loop and stuffing heterogeneous results into `operator.add`
lists — all the rigidity of the graph with none of its clarity. The reducer model is the
reason "keep LangGraph as the *supervisor*" is rejected; it survives only as an optional
*per-role inner executor* (Design C), where its static single-role schema is fine.

---

## 2. Role → toolset/skill profile mapping (assumes Workstream B tool registry exists)

Today each agent hardcodes its prompt + submit-tool (verified):
`Architect.plan` injects `write_plan`; `Reviewer.agentic_review` injects `submit_review`
(`SubmitReviewInput`); `Evaluator.evaluate` injects `submit_evaluation`
(`EvaluationOutput`); `Developer.run` and `Oracle.consult` use the full default toolkit.
The *only* axes of difference are **prompt, toolset, submit-schema**. That is exactly a
profile.

Define `AgentProfile` (new, `amelia/core/agent_profile.py`):

```python
class AgentProfile(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str                       # "architect" | "developer" | "reviewer" | ...
    system_prompt: str
    toolset: tuple[str, ...]        # tool names resolved against Workstream B ToolRegistry
    skills: tuple[str, ...] = ()    # skill ids resolved against the skill registry
    submit_schema: type[BaseModel] | None = None   # write_plan / submit_review / ...
    max_iterations: int = 50
    delegable: bool = True          # may the supervisor delegate to this role
```

| Role | toolset | submit_schema | skills (Workstream B) |
|------|---------|---------------|------------------------|
| architect | read/search/`write_plan` | `WritePlanInput` | `planning`, `repo-survey` |
| developer | full edit/exec/test | none | `coding`, `test-authoring` |
| reviewer | read/diff/`submit_review` | `SubmitReviewInput` | `code-review` |
| evaluator | read/`submit_evaluation` | `EvaluationOutput` | `triage` |
| oracle | read/search | none (free-text advice) | `deep-reasoning` |

The supervisor is itself a profile (`supervisor`) whose toolset is the **delegation tool +
shared read tools**, and whose "tools" *to the model* are the delegable role profiles
exposed as `delegate_task(role=...)` targets. `toolset` and `skills` are resolved through
the Workstream B registry at supervisor-construction time, so adding a role is adding a
row of data, not a graph node + router + reducer.

`amelia/core/agent_profiles.py` ships the five built-in profiles as module constants
(`ARCHITECT_PROFILE`, ...), reusing the existing prompt constants
(`SYSTEM_PROMPT_PLAN`, etc.) and submit schemas. The existing agent classes
(`agents/architect.py` …) are **reduced to profile data + their submit-schema**; their
orchestration methods (`.plan`, `.run`, `.agentic_review`) are deleted because the
supervisor now drives the agentic call directly through `Driver.execute_agentic`.

---

## 3. Subagent-delegation primitive

New tool `delegate_task` (`amelia/runtime/delegation.py`), modeled on Hermes
`tools/delegate_tool.py` but typed and asyncio-native:

```python
class DelegatedTask(BaseModel):
    role: str                       # profile name to act as
    goal: str
    context: str | None = None      # file paths, constraints
    worktree: str | None = None     # None => share supervisor worktree (read-only roles)

class DelegateTaskInput(BaseModel):
    tasks: tuple[DelegatedTask, ...]   # N tasks -> N parallel children
    background: bool = False
```

Spawning (in `DynamicSupervisor._spawn`):

```python
sem = asyncio.Semaphore(self._max_child_concurrency)
async def _one(t: DelegatedTask) -> ChildResult:
    async with sem:
        profile = self._registry.profile(t.role)
        return await run_role(profile, t, driver=self._driver, sandbox=self._sandbox)
results = await asyncio.gather(*(_one(t) for t in tasks))
```

Each child is an independent agentic run with its own iteration budget (cf. Hermes'
per-agent `IterationBudget`, `agent/iteration_budget.py`), its own driver session, its own
typed submit-schema result. Children may themselves delegate (depth-bounded via
`max_spawn_depth`, default 2, mirroring Hermes) — `delegable=False` profiles are leaves.

**How 500+ parallel agents become feasible locally.** Two concurrency limits exist and
must be reconciled:

1. **Workflow-level** (existing): `OrchestratorService` enforces *one workflow per
   worktree* and a global `max_concurrent` via the `_active_tasks: dict[str, tuple[UUID,
   asyncio.Task]]` map checked in `_assert_can_acquire_worktree` (`service.py:557`). This
   is a heavyweight, worktree-bound limit — appropriate for full filesystem-mutating
   workflows.
2. **Subagent-level** (new): inside *one* workflow, `delegate_task` fans out via an
   `asyncio.Semaphore`, default width configurable per profile. Read-only roles
   (architect/reviewer/oracle/evaluator) **share the supervisor's worktree** (no new
   checkout), so 500 read-mostly children are 500 coroutines + 500 LLM sockets, not 500
   git worktrees. Only roles that *mutate* the filesystem need isolation, and they get it
   via the existing sandbox model (`SandboxMode.NONE|CONTAINER|DAYTONA`, `core/types.py`)
   — a mutating child requests a sandbox/worktree, a read child does not. 500 parallel is
   therefore I/O-bound coroutine fan-out under one workflow slot, bounded by the
   sub-semaphore and provider rate limits, *not* by `OrchestratorService.max_concurrent`.

The two limits compose: `max_concurrent` caps top-level workflows; the per-workflow
sub-semaphore caps children within each. Neither subsumes the other; both are enforced.

---

## 4. Migration path: `orchestration_mode: fixed | dynamic`

`orchestration_mode` does **not** exist yet (confirmed: 0 grep hits). Introduce it on
`Profile` (`core/types.py`) as `orchestration_mode: Literal["fixed", "dynamic"] = "fixed"`
so legacy behavior is the default and nothing changes until opted in.

Routing seam: `OrchestratorService.start_workflow` (`service.py:565`) currently always
hands off to `GraphRunner` (`server/orchestrator/runner.py`). Branch there:

```python
if profile.orchestration_mode == "dynamic":
    runner = self._dynamic_runner   # new DynamicRunner, mirrors GraphRunner's seams
else:
    runner = self._runner           # existing GraphRunner
```

`DynamicRunner` exposes the **same** public contract GraphRunner does (start, stream
events through `StreamEventEmitter`, register/finalize `WorkflowTrajectoryRecorder`, honor
approval gates) so the orchestrator, event bus, DB repository, and dashboard are unchanged.
Internally it constructs and runs `DynamicSupervisor` instead of compiling a `StateGraph`.

**What ships behind the flag first (smallest credible slice):**

1. `DynamicRunner` + `DynamicSupervisor` loop with **no delegation** — single supervisor
   that can act as developer-only on a one-task issue. Proves the loop, budget, event
   streaming, and trajectory recording end-to-end against the production entrypoint
   (`start_workflow` with `orchestration_mode="dynamic"`).
2. Add `delegate_task` with sequential (semaphore=1) execution; map the five role
   profiles. Now the supervisor reproduces the fixed pipeline's architect→developer→
   reviewer flow *by choice*, validating role parity against the legacy graph on the same
   issues.
3. Raise sub-concurrency; add parallel fan-out + sandbox-per-mutating-child. Soak the
   500-agent claim.

Legacy `fixed` graph stays fully wired and is the default throughout; cutover is per-profile
opt-in, then default-flip, then deletion (Section 5) once dynamic reaches parity on the
integration suite.

---

## 5. File-level change list

**Created**

- `amelia/core/agent_profile.py` — `AgentProfile` model.
- `amelia/core/agent_profiles.py` — five built-in role profiles (constants).
- `amelia/runtime/supervisor.py` — `DynamicSupervisor`, `SupervisorContext`,
  `SupervisorResult`, the ReAct loop.
- `amelia/runtime/delegation.py` — `delegate_task` tool, `DelegatedTask`,
  `DelegateTaskInput`, `_spawn`, semaphore/depth bounding.
- `amelia/runtime/iteration_budget.py` — `IterationBudget` (per-agent, thread-safe;
  port Hermes' `agent/iteration_budget.py`).
- `amelia/server/orchestrator/dynamic_runner.py` — `DynamicRunner` mirroring GraphRunner's
  public seams.
- `tests/integration/test_dynamic_supervisor.py` — production-entrypoint test:
  `start_workflow(orchestration_mode="dynamic")`, real driver boundary mocked only at the
  HTTP/LLM seam, asserts on the **written transcript / produced diff / ReviewResult**, with
  branched and fan-out shapes (N=0, N=1, N=many reviewer/developer children).

**Modified**

- `amelia/core/types.py` — add `orchestration_mode` to `Profile`.
- `amelia/server/orchestrator/service.py` — branch in `start_workflow` (and
  `start_pending_workflow`, `start_batch_workflows`) on `orchestration_mode`; construct
  `DynamicRunner`; reconcile sub-semaphore vs `max_concurrent` (Section 3).
- `amelia/drivers/api/deepagents.py` — optionally thread `subagents=`/`skills=` into
  `create_deep_agent` for *within-role* delegation (Design C's optional inner use); expose
  `execute_agentic` in a form the supervisor calls per-step.
- `amelia/agents/architect.py`, `developer.py`, `reviewer.py`, `evaluator.py`,
  `oracle.py` — strip orchestration methods (`.plan/.run/.agentic_review/.evaluate/
  .consult`) down to profile data + submit-schema; keep schemas, delete run-ordering.
- `amelia/server/config.py` — sub-concurrency + `max_spawn_depth` settings.

**Deleted (only after dynamic reaches parity; default-flip first)**

- `amelia/pipelines/implementation/graph.py`, `routing.py` — fixed topology + routers.
- `amelia/pipelines/implementation/nodes.py` — node wrappers (`call_architect_node`, …).
- `amelia/pipelines/{nodes.py,routing.py}` — shared fixed-graph plumbing.
- Eventually `pipelines/registry.py` + `base.py` once no fixed pipeline remains.
  `ImplementationState` is retained as a typed result envelope, **not** deleted; its
  `Annotated[..., operator.add]` reducer fields are dropped when it stops threading through
  a graph.

---

## 6. Open questions for the team lead

1. **Design A vs C — surrender delegation fidelity for less code?** The recommendation
   (C) costs us a hand-rolled loop. If we never actually need typed cross-role results or
   bounded 500-wide fan-out, Design A is materially cheaper. Is the 500-agent / typed-result
   requirement firm, or aspirational? This decides the workstream's size.
2. **CLI driver parity.** `ApiDriver` runs deepagents; the CLI driver path is different and
   `allowed_tools` raises `NotImplementedError` on `ApiDriver` today
   (`deepagents.py:397`). Does dynamic mode need to support the CLI driver at launch, or is
   API-driver-only acceptable for the first flagged release?
3. **Sandbox-per-mutating-child cost.** 500 read-only children share a worktree, but
   mutating children need isolation. Is `SandboxMode.DAYTONA` the intended substrate for
   wide *mutating* fan-out, and what is the cost/quota ceiling? This bounds the real-world
   parallel-write width.
4. **Approval gates under delegation.** The fixed graph has an explicit
   `human_approval_node`. In dynamic mode, does approval become a tool the supervisor calls
   (`request_approval`), and how does that interact with N backgrounded children awaiting
   approval simultaneously?
5. **Trajectory schema.** ATIF / `WorkflowTrajectoryRecorder` currently records a linear
   node sequence. A delegation tree is not linear — do we record children as nested spans,
   and does the dashboard need to render trees before we ship parallel fan-out?
6. **Budget accounting across the tree.** Hermes gives each agent an *independent* budget,
   so a tree can exceed the parent cap. Do we want a global token/iteration budget for the
   whole workflow tree, or per-agent budgets that can sum past the parent? This is a cost-
   control decision, not just a correctness one.
