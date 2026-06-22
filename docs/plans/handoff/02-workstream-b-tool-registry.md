# 02 — Workstream B: Unified Tool Registry

**Goal:** fold four issues into **one** coherent tool subsystem — so we don't ship four
overlapping registries. This is the foundation the eventual dynamic agent core (Workstream A)
sits on: in a Hermes-shaped runtime, "roles" are just toolset+skill selections over one loop,
so the registry must exist and be clean first.

**Full design (read it):** `docs/plans/2026-06-20-workstream-b-tool-registry-design.md`
**De-risking spike (read it):** `docs/plans/2026-06-20-workstream-b-middleware-veto-spike.md`

## The four issues this folds

| Issue | Role in B |
|---|---|
| **#233 Tool Registry** | The **spine**: `ToolSpec` schema, `register()`, import-time self-registration, tool metadata + risk levels. **Build first — the other three depend on it.** |
| **#621 Wiring/spike** | Fix the embarrassing gaps: `knowledge_search` is built+tested but wired to **zero** agents (`amelia/tools/knowledge.py` `create_knowledge_tool()`); `allowed_tools` raises `NotImplementedError` (`amelia/drivers/api/deepagents.py` ~line 397); `READONLY_TOOLS` preset (`amelia/core/constants.py` ~line 81) is defined but **unconsumed**. Plus candidate new tools (structured `git_diff`/`git_log`, `run_tests`/`run_linter`, `FileBundler`-as-tool). |
| **#357 Read-only restriction** | Architect/Oracle must be filesystem read-only **enforced at the tool level**, not via prompt. Becomes a *toolset filter* over the registry, not a bespoke subclass. |
| **#228 Security Guardrails** | `check_fn` permission gates + risk levels + pre/post-exec validation hooks + audit log. The *policy layer* over the same registry. |

## The spike result that unblocks #357 and #228 — read this

The prior session empirically verified: **`AgentMiddleware.awrap_tool_call`** (sync sibling
`wrap_tool_call`) in **langchain 1.3.9** (`langchain/agents/middleware/types.py:744`) is a true
**short-circuit veto** hook. The executor passes the real tool-execution callable into it
(`langgraph/prebuilt/tool_node.py:1196-1210`); a middleware can **skip calling it and return a
`ToolMessage`** so the tool never runs. Verified live: a denied `write_file` returned a substitute
error and its body never executed, while `read_file` ran normally.

**Implication:** tool-level read-only (#357) and security gating (#228) on the ApiDriver/deepagents
path are achievable as a **drop-in middleware** — no deepagents patch, no write-denying sandbox
fallback. Amelia already forwards `middleware` into `create_deep_agent`, so the `allowed_tools`
`NotImplementedError` (#621) can simply be implemented as a `ToolPolicyMiddleware` that vetoes
disallowed tools. **This is the keystone for all of B.**

## The `ToolSpec` schema (from the design doc — the single thing everything registers against)

Frozen Pydantic model:
- `name` — validated against the `ToolName` enum/constants
- `description`
- `input_schema` — Pydantic type → JSON schema
- `handler` — async callable
- `risk_level` — `READ_ONLY | WRITE | EXECUTE | DESTRUCTIVE`
- `required_permissions` — `frozenset[Permission]`
- `toolsets` — `frozenset[str]` (membership; toolsets are composable)
- `check_fn` — availability/permission probe
- `factory` — for tools needing runtime deps (e.g. `knowledge_search` needs `EmbeddingClient` + repo)

Derived behaviors:
- **READONLY toolset (#357)** = a query `risk_level <= READ_ONLY`.
- **Guardrails (#228)** = a `ToolPolicyMiddleware` reading the same specs (pre/post hooks + audit).
- **`allowed_tools` (#621)** = additive custom tools **+** subtractive `ToolPolicyMiddleware`
  veto (via `awrap_tool_call`) over library tools.

## Biggest open question for you to resolve early
The design doc flags one: whether the policy layer should live as **one** `ToolPolicyMiddleware`
(does allowlist + readonly + guardrails) or as **composable** middlewares. Decide this before
fanning out #357/#228 so they don't both invent a policy mechanism. Recommendation: one
`ToolPolicyMiddleware` parameterized by a `ToolPolicy` (allowed set + risk ceiling + audit sink),
with #357 = a preset policy and #228 = the configurable policy surface.

## Sequencing (stacked PRs — one session, no forced mid-session merge)

```
Phase 1 (1 agent):   #233  → branch feat/233-tool-registry, PR. THE SPINE.
                      Migrate existing amelia/tools/* to register() against ToolSpec.
                      Implement ToolPolicyMiddleware skeleton using awrap_tool_call (so phase 2
                      has the veto hook to build on).

Phase 2 (3 agents, STACKED on the #233 branch, run concurrently):
   #621  wiring: knowledge_search → developer/architect/oracle/brainstormer; implement
         allowed_tools on ApiDriver via ToolPolicyMiddleware; consume READONLY_TOOLS.
   #357  readonly toolset preset + apply to Architect/Oracle.
   #228  configurable ToolPolicy: risk ceilings, pre/post hooks, audit log table.
```

**Why stacked:** #621/#357/#228 all import the registry + middleware from #233. Worktree agents
branch from `origin/main` by default, which won't have #233 yet. So in each Phase-2 prompt,
instruct the agent to base its branch on the #233 branch:

```
Start by basing your branch on the #233 registry branch (not main):
  git fetch origin && git checkout -b feat/«N»-«slug» origin/feat/233-tool-registry
Open your PR with --base feat/233-tool-registry and note "Depends on #233" in the body.
```

Tell the user at the end: **merge #233 first, then #621/#357/#228** (rebasing each onto main as
#233 lands). If the user would rather merge #233 before Phase 2, do Phase 1, ask them to merge it,
then fan out Phase 2 off a clean main (simpler bases, no stacking).

## Phase 1 agent prompt (#233) — adapt the template in 01-orchestration-playbook.md

Key slots:
- LOCATIONS: `amelia/tools/` (all tool modules), `amelia/core/constants.py` (`ToolName`,
  `READONLY_TOOLS` ~line 81), `amelia/drivers/api/deepagents.py` (`create_deep_agent` usage,
  `FilesystemMiddleware` ~line 387, `allowed_tools` `NotImplementedError` ~line 397),
  `amelia/drivers/base.py` (`DriverInterface.execute_agentic`), and the installed deepagents
  package (`uv run python -c "import deepagents,inspect;print(inspect.getfile(deepagents))"`).
- REQUIRED: define `ToolSpec` (frozen Pydantic, schema above) + a `ToolRegistry` with
  `register()` and import-time self-registration; migrate every existing tool in `amelia/tools/`
  to register against it; add a `ToolPolicyMiddleware` skeleton built on `awrap_tool_call` that
  takes a `ToolPolicy` (allowed set + risk ceiling + optional audit sink) and vetoes disallowed
  or over-risk tools by returning a substitute `ToolMessage`.
- ACCEPTANCE: registry enumerates all migrated tools with correct `risk_level`; a `ToolPolicy`
  that disallows `write_file` causes a denied `ToolMessage` and the write never executes (assert
  the file is NOT written — observable consequence, mirrors the spike); existing agent/driver
  tests stay green; `knowledge_search` is registerable via its `factory`.
- Reference `docs/plans/2026-06-20-workstream-b-tool-registry-design.md` for the full file-level
  change list, and `...-middleware-veto-spike.md` for the exact veto code shape.

## Phase 2 agent prompts — three, run concurrently, each based on the #233 branch
Use the template; LOCATIONS/REQUIRED/ACCEPTANCE per issue. Authoritative issue text:
`gh issue view 621` · `gh issue view 357` · `gh issue view 228`. Each must assert observable
consequences (e.g. #357: a read-only agent's `write_file` is vetoed and no file appears; #621:
`knowledge_search` actually returns results to the developer agent and `allowed_tools` filters
the exposed set; #228: a high-risk tool call is blocked by policy and an audit row is written).
