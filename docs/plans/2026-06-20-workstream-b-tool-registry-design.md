# Workstream B — Unified Tool Registry Design

**Date:** 2026-06-20
**Status:** Design (no implementation)
**Folds in:** #233 (Tool Registry), #621 (Wiring gaps), #357 (Read-only restriction), #228 (Security Guardrails)
**Resurfaces:** #627 (github_pr_create), #560 (git_commit w/ message generation)

---

## 0. Why one registry

Amelia currently has **four divergent tool paths**, none of them a registry:

| Path | How tools arrive | Restriction support |
|------|------------------|---------------------|
| `ApiDriver.execute_agentic` (deepagents) | `FilesystemMiddleware` always injects `ls, read_file, write_file, edit_file, glob, grep` + sandbox `execute`; custom tools appended via `tools=` kwarg | **none** — `allowed_tools` raises `NotImplementedError` (deepagents.py:397) |
| `ClaudeCliDriver.execute_agentic` | SDK builtin tools | subtractive `allowed_tools` via `ClaudeAgentOptions.allowed_tools` (claude.py:367) |
| `CodexCliDriver.execute_agentic` | codex builtins | coarse sandbox-mode mapping of `allowed_tools` (codex.py:94) |
| Per-agent custom tools | Architect hand-builds `create_write_plan_tool` and passes `tools=[...]`; Reviewer/Oracle use `submit_tools` | n/a |

Symptoms this causes, all of which are open issues:
- `knowledge_search` (`amelia/tools/knowledge.py::create_knowledge_tool`) is **orphaned** — `grep` finds zero references in any agent or pipeline (#621).
- `READONLY_TOOLS` (constants.py:80) is **defined-but-unconsumed** except as a *subset check* inside the codex driver; the comment literally says "Not yet consumed" (#621, #357).
- Read-only enforcement for Architect/Oracle lives **in prompts**, not at the tool layer (#357).
- There is **no risk metadata, no check_fn gating, no audit log** anywhere (#228).
- `github_pr_create` / `git_commit` capabilities live as private helpers inside `pr_auto_fix` and `git_utils.GitOperations`, not as agent-callable tools (#627, #560).

The fix is **one `ToolSpec` schema that every tool registers against**, plus thin adapters that render that schema into each driver's native format. Modeled on Hermes' `tools/registry.py` + `toolsets.py` + `model_tools.py` triad, adapted to Amelia's Pydantic/async/multi-driver world.

---

## 1. The `ToolSpec` schema and `register()`

New package: **`amelia/tools/registry/`**

```
amelia/tools/registry/
  __init__.py          # exports: registry, register, ToolSpec, RiskLevel, Permission
  spec.py              # ToolSpec, RiskLevel, Permission enums
  registry.py          # ToolRegistry singleton + discover_builtin_tools()
  adapters.py          # spec -> LangChain StructuredTool / SDK MCP tool
  policy.py            # check_fn gating + pre/post hooks + audit (#228)
```

### 1.1 `ToolSpec` (spec.py)

A frozen Pydantic model — not a dataclass, to stay consistent with the project convention "Pydantic models for all data structures." `handler` and `check_fn` are `Callable` fields (arbitrary-types allowed).

```python
class RiskLevel(IntEnum):
    READ_ONLY = 0      # cannot mutate disk, repo, or network state
    WRITE = 1          # mutates the working tree (write_file, edit_file, write_plan)
    EXECUTE = 2        # runs arbitrary local code (run_shell_command)
    DESTRUCTIVE = 3    # irreversible / remote side effects (git push, github_pr_create, file delete)

class Permission(StrEnum):
    FS_READ = "fs.read"
    FS_WRITE = "fs.write"
    SHELL_EXEC = "shell.exec"
    GIT_LOCAL = "git.local"      # commit, diff, log (local repo mutation/read)
    GIT_REMOTE = "git.remote"    # push, fetch
    GITHUB = "github"            # PR/issue API
    NET_READ = "net.read"        # web_fetch, web_search, knowledge_search

class ToolSpec(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str                              # canonical name — MUST be a ToolName value
    description: str
    input_schema: type[BaseModel]          # Pydantic model => json schema (single source)
    handler: Callable[..., Awaitable[Any]] # async handler(**validated_kwargs) -> result
    risk_level: RiskLevel = RiskLevel.READ_ONLY
    required_permissions: frozenset[Permission] = frozenset()
    toolsets: frozenset[str] = frozenset()   # membership: {"readonly","filesystem","git","vcs",...}
    check_fn: Callable[[], bool] | None = None   # availability probe (e.g. gh CLI present)
    factory: Callable[[ToolContext], Awaitable[Any]] | None = None
        # optional: tools needing runtime deps (knowledge_search needs an
        # EmbeddingClient + KnowledgeRepository) declare a factory that the
        # registry calls with a ToolContext at resolution time instead of a
        # static module-level handler. See §3.3.
```

`name` is validated in a `field_validator` against `ToolName` so the registry and `constants.ToolName` cannot drift — every registered tool has a canonical name, killing the ad-hoc `TOOL_NAME_ALIASES` round-trips at the boundary.

### 1.2 `register()` and the singleton (registry.py)

```python
class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec, *, override: bool = False) -> None:
        if spec.name in self._specs and not override:
            raise ValueError(f"Tool {spec.name!r} already registered ...")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None: ...
    def names_for_toolset(self, toolset: str) -> frozenset[str]: ...
    def resolve(self, names: Iterable[str]) -> list[ToolSpec]: ...

registry = ToolRegistry()

def register(spec: ToolSpec, *, override: bool = False) -> None:
    registry.register(spec, override=override)
```

Hermes uses a free `register()` raising on collision (registry.py:258) and a module-level singleton — we mirror that. We **drop** Hermes' MCP-overwrite / generation-counter / TTL-cache machinery: Amelia has no live MCP refresh, so a plain dict guarded by import-order is enough. (Open question Q3 revisits thread-safety.)

### 1.3 Import-time self-registration

Each tool module ends with a module-level `register(ToolSpec(...))` call. Discovery mirrors Hermes' AST scan (registry.py:29-74) so we import **only** modules that actually self-register, avoiding side-effect imports:

```python
def discover_builtin_tools() -> list[str]:
    """Import every amelia/tools/*.py that contains a top-level register(ToolSpec(...))."""
```

Called **once** from a new `amelia/tools/__init__.py` import guard (and explicitly at server/CLI startup) so the registry is populated before any driver builds a tool list. The AST guard (`_module_registers_tools`) means `git_utils.py` helper functions that don't self-register are skipped.

### 1.4 Built-in registrations (the migration target)

| Module | name | risk | permissions | toolsets |
|--------|------|------|-------------|----------|
| `read_file_tool.py`* | `read_file` | READ_ONLY | `fs.read` | `readonly`, `filesystem` |
| `write_file` / `edit_file`* | … | WRITE | `fs.write` | `filesystem` |
| `glob` / `grep`* | … | READ_ONLY | `fs.read` | `readonly`, `filesystem` |
| `shell_executor.py` | `run_shell_command` | EXECUTE | `shell.exec` | `execute` |
| `write_plan.py` | `write_plan` | WRITE | `fs.write` | `planning` |
| `file_bundler.py` | `bundle_files` (FileBundler-as-tool, #621) | READ_ONLY | `fs.read` | `readonly` |
| `knowledge.py` | `knowledge_search` | READ_ONLY | `net.read` | `readonly`, `knowledge` |
| `git_tools.py` (new) | `git_diff`, `git_log` (#621) | READ_ONLY | `git.local` | `readonly`, `vcs` |
| `git_tools.py` | `git_commit` (#560) | WRITE | `git.local` | `vcs` |
| `git_tools.py` | `git_push` | DESTRUCTIVE | `git.remote` | `vcs` |
| `github_tools.py` (new) | `github_pr_create` (#627) | DESTRUCTIVE | `github` | `vcs` |
| `quality_tools.py` (new) | `run_tests`, `run_linter` (#621) | EXECUTE | `shell.exec` | `quality` |

\* The deepagents `FilesystemMiddleware` tools (`ls/read_file/write_file/edit_file/glob/grep`) are **provided by the library**, not by us. We register **spec stubs** for them (name + risk + toolset, `handler=None`/`factory=None`) so the policy and toolset layers can reason about them uniformly. The stubs are the *catalog*; the actual implementation stays in deepagents/the SDK. See §3.

---

## 2. Toolset resolution — READONLY as a filter, per-agent profiles

### 2.1 Toolsets replace the bespoke middleware subclass (#357)

Today read-only is a *prompt instruction*. The plan in #357 was a `ReadOnlyFilesystemMiddleware` subclass that strips `write_file`/`edit_file`. **We delete that idea.** Read-only becomes `toolset="readonly"` membership computed off `risk_level <= READ_ONLY`, resolved the same way for every driver.

`registry.resolve_toolset("readonly")` returns exactly the specs whose `risk_level == READ_ONLY` (or that declare `"readonly"` in `toolsets`). This is the single definition `READONLY_TOOLS` should have been. `constants.READONLY_TOOLS` is **kept as a hand-maintained tuple but re-expressed as a registry query** in a unit test that asserts `set(READONLY_TOOLS) == registry.names_for_toolset("readonly")`, so the two can never drift (resolves the "defined-but-unconsumed" half of #621).

### 2.2 Per-agent toolset profiles

New module **`amelia/agents/tool_profiles.py`** — one declarative table, the single source of truth for "what can each agent touch":

```python
@dataclass(frozen=True)
class AgentToolProfile:
    toolsets: frozenset[str]          # which toolsets the agent may use
    extra_tools: frozenset[str] = frozenset()   # one-off additions (e.g. write_plan)
    max_risk: RiskLevel = RiskLevel.EXECUTE     # hard ceiling, policy-enforced

AGENT_TOOL_PROFILES: dict[str, AgentToolProfile] = {
    "developer":   AgentToolProfile({"filesystem","execute","vcs","knowledge","quality"}),
    "architect":   AgentToolProfile({"readonly","planning","knowledge"},
                                    max_risk=RiskLevel.WRITE),   # read + write_plan only
    "oracle":      AgentToolProfile({"readonly","knowledge"},
                                    max_risk=RiskLevel.READ_ONLY),
    "brainstormer":AgentToolProfile({"readonly","knowledge"},
                                    max_risk=RiskLevel.READ_ONLY),
    "reviewer":    AgentToolProfile({"readonly","knowledge"},
                                    max_risk=RiskLevel.READ_ONLY),
    "evaluator":   AgentToolProfile({"readonly"},
                                    max_risk=RiskLevel.READ_ONLY),
}
```

`resolve_agent_tools(agent_name) -> list[ToolSpec]` unions the toolsets, adds `extra_tools`, filters out `check_fn()==False`, and drops anything over `max_risk`. Each agent's `execute_agentic` call passes the resolved canonical names as `allowed_tools` (now actually implemented — §3) instead of relying on prompt text.

---

## 3. Implementing `allowed_tools` on ApiDriver (#621)

### 3.1 The constraint

`deepagents/graph.py` **always** appends `FilesystemMiddleware(backend=backend)` (lines 174, 252). Its 6 filesystem tools plus the sandbox `execute` tool are injected unconditionally; `create_deep_agent(tools=...)` is purely **additive**. There is no subtractive allowlist knob. So `allowed_tools` cannot be honored by "passing fewer tools" — the dangerous ones are already in.

### 3.2 Two-layer enforcement (additive shaping + policy gate)

We stop raising `NotImplementedError` and implement `allowed_tools` as **filter + wrap**, not "don't inject":

1. **Additive layer (custom tools).** Build the custom-tool list from `registry.resolve(allowed_tools)` filtered to specs that have a real `handler`/`factory` (knowledge_search, write_plan, bundle_files, git_*, github_pr_create, run_tests…). These become LangChain `StructuredTool`s via `adapters.to_langchain(spec)`. Only the allow-listed custom tools are passed to `create_deep_agent(tools=...)`.

2. **Subtractive layer (library tools we can't un-inject).** The always-present FilesystemMiddleware + sandbox tools are constrained by a **`ToolPolicyMiddleware`** (an `AgentMiddleware` subclass, §4) inserted ahead of FilesystemMiddleware in the `middleware=` list. Its `before_tool` hook rejects any call whose canonical name is **not in the resolved allow-set**, returning a tool error message ("Tool `write_file` is not permitted for this agent (read-only)") instead of executing. This is how Architect/Oracle get filesystem read-only **enforced at the tool level**: `write_file`/`edit_file`/`execute` calls are short-circuited by the middleware even though the library injected them.

So on the deepagents path, `allowed_tools` = (a) which custom registry tools get added **and** (b) the allow-set the `ToolPolicyMiddleware` enforces over the library tools. `NotImplementedError` is removed; the method gains a `_resolve_allowed(allowed_tools)` helper that returns `(custom_tools, allow_set)`.

### 3.3 The factory problem (knowledge_search)

`knowledge_search` needs an `EmbeddingClient` + `KnowledgeRepository` (constructed in `server/main.py:213`). A module-level handler can't hold those. So `ToolSpec.factory` is called with a **`ToolContext`** assembled by the driver/agent layer:

```python
@dataclass
class ToolContext:
    cwd: str
    embedding_client: EmbeddingClient | None
    knowledge_repo: KnowledgeRepository | None
    event_bus: EventBus | None   # for audit emission
```

`resolve_agent_tools` skips factory tools whose required context is absent (e.g. no knowledge repo configured ⇒ `knowledge_search` silently omitted) — same graceful-degradation shape as Hermes' `check_fn`.

### 3.4 CLI drivers (claude / codex)

The CLI drivers already accept `allowed_tools`. They keep doing so, but the **values now come from `resolve_agent_tools`** (canonical names), and `adapters.to_sdk_mcp(spec)` renders custom registry tools (knowledge_search, write_plan, github_pr_create) as in-process SDK MCP tools — reusing the existing `create_sdk_mcp_server` path in claude.py:615. Codex keeps its coarse sandbox-mode mapping but the mapping table moves to `registry`-derived risk levels (`max(risk_level for resolved tools)` → mode) instead of the hardcoded `READONLY_TOOLS` subset check. **One allow-set, three render targets.**

---

## 4. check_fn + risk + audit as policy over the registry (#228)

`amelia/tools/registry/policy.py` is the security layer. It does **not** own a second list of tools — it reads `ToolSpec` metadata off the same registry.

### 4.1 `ToolPolicyMiddleware` (deepagents) / `policy_guard` (CLI)

```python
class ToolPolicyMiddleware(AgentMiddleware):
    def __init__(self, allow_set, profile, ctx): ...

    async def before_tool(self, call):   # pre-exec validation hook
        name = normalize_tool_name(call.name)
        spec = registry.get(name)
        if name not in self._allow_set:        return _deny("not permitted")
        if spec and spec.risk_level > self._profile.max_risk:
                                                return _deny("exceeds risk ceiling")
        if spec and spec.check_fn and not spec.check_fn():
                                                return _deny("unavailable")
        self._audit("call", name, call.args)    # audit BEFORE
        if spec and spec.risk_level >= RiskLevel.DESTRUCTIVE:
            return self._gate_high_risk(spec, call)   # §4.2
        return None  # allow

    async def after_tool(self, call, result):  # post-exec validation hook
        self._audit("result", call.name, summarize(result))
        return None
```

The same logic runs in the CLI path via a `policy_guard(name, args)` callable invoked from the driver's tool-call loop (claude.py / codex.py already iterate SDK tool-call messages), since CLI drivers have no middleware concept.

### 4.2 Gating high-risk tools

`risk_level >= DESTRUCTIVE` (git push, github_pr_create, file delete, and `EXECUTE` shell when the profile flags it) routes through `_gate_high_risk`, which consults a **`PermissionPolicy`** resolved from config:

- `auto` — allowed (current default for autonomous pipelines; bypass is already how agentic mode runs, claude.py `bypass_permissions=True`).
- `deny` — short-circuit with a tool error (this is what enforces Architect/Oracle/Reviewer/Evaluator read-only: their `max_risk` ceiling denies `WRITE`+).
- `confirm` — emit an `EventType.TOOL_PERMISSION_REQUIRED` event and await resolution (future interactive path; for now treated as `deny` in headless pipelines).

`required_permissions` cross-checks the agent profile's granted permission set as a second, orthogonal gate (a tool may be low-risk but still require `github`).

### 4.3 Audit log

Every gate decision and every call/result emits a structured record. Reuse the existing event bus: a new `EventType.TOOL_AUDIT` `WorkflowEvent` carrying `{tool_name, risk_level, decision, args_digest, agent, workflow_id}`. Persisted alongside other workflow events (no new table needed — `WorkflowEvent` already streams to the dashboard and DB). Loguru structured line as a secondary sink (`logger.info("tool_audit", tool=…, decision=…)`). This satisfies #228's "audit log of tool calls" with **one source of truth** (the event stream), not a parallel log.

---

## 5. Resurfacing closed-issue capabilities as registered tools

These shipped as buried helpers; they become first-class registry entries reusing the existing implementations.

### 5.1 `github_pr_create` (#627)

New `amelia/tools/github_tools.py`. Handler shells `gh pr create` (matching `pr_auto_fix/nodes.py` patterns) via `run_shell_command`, or calls the GitHub API. `check_fn = lambda: shutil.which("gh") is not None`. `risk=DESTRUCTIVE`, `permissions={github}`, `toolsets={vcs}`. Self-registers; available to `developer` only (its profile includes `vcs`).

### 5.2 `git_commit` with message generation (#560)

New `amelia/tools/git_tools.py`, wrapping the **existing** `GitOperations.stage_and_commit` (git_utils.py:450) so the safety guards (protected-branch refusal, `:!.claude/` exclusion) are not reimplemented. Message generation: if the caller omits `message`, the handler builds a `git diff --stat` summary and calls `driver.generate()` with a commit-message prompt (the message-gen logic from #560), then commits. `risk=WRITE`, `permissions={git.local}`, `toolset=vcs`. Sibling `git_push` wraps `GitOperations.safe_push` at `risk=DESTRUCTIVE`.

---

## 6. Wiring fixes (#621)

1. **Wire `knowledge_search`.** Register it via `factory` (§3.3). Add `"knowledge"` toolset to the `developer`, `architect`, `oracle`, `brainstormer` profiles in §2.2. The `ToolContext` is populated wherever agents are constructed (drivers init / `server/main.py` already builds the `EmbeddingClient`+`KnowledgeRepository`). Verification test: an agent run with a seeded knowledge repo must produce a `TOOL_CALL` event for `knowledge_search` (observe the side effect, not just "tool was available").
2. **Consume `READONLY_TOOLS` for Reviewer/Evaluator.** Their profiles set `max_risk=READ_ONLY` and `toolsets={readonly}`. The drift-guard test (§2.1) asserts `READONLY_TOOLS` equals the `readonly` toolset, so the preset is now load-bearing instead of dead.
3. **Candidate new tools** (`git_diff`/`git_log`, `run_tests`/`run_linter`, `bundle_files`) register per the §1.4 table and join the `developer` profile.

---

## 7. File-level change list

**New**
- `amelia/tools/registry/__init__.py`, `spec.py`, `registry.py`, `adapters.py`, `policy.py`
- `amelia/agents/tool_profiles.py` — `AGENT_TOOL_PROFILES`, `resolve_agent_tools`
- `amelia/tools/git_tools.py` — `git_diff`, `git_log`, `git_commit`, `git_push` specs (wrap `GitOperations`)
- `amelia/tools/github_tools.py` — `github_pr_create`
- `amelia/tools/quality_tools.py` — `run_tests`, `run_linter`
- `tests/unit/tools/test_registry.py`, `test_policy.py`, `test_tool_profiles.py`, `test_readonly_drift.py`
- `tests/integration/test_agent_tool_restriction.py` — production entrypoint, real driver, asserts a denied `write_file` for Architect

**Modified**
- `amelia/tools/__init__.py` — call `discover_builtin_tools()`
- `amelia/tools/knowledge.py`, `shell_executor.py`, `write_plan.py`, `file_bundler.py` — append `register(ToolSpec(...))`
- `amelia/core/constants.py` — add new `ToolName`s (`git_diff`, `git_log`, `git_commit`, `git_push`, `github_pr_create`, `run_tests`, `run_linter`, `bundle_files`); keep `READONLY_TOOLS`, add drift test
- `amelia/drivers/api/deepagents.py` — remove `NotImplementedError` (line 397-401); add `_resolve_allowed`, insert `ToolPolicyMiddleware`, render custom tools from registry
- `amelia/drivers/cli/claude.py`, `codex.py` — source `allowed_tools` from registry, render custom tools via MCP adapter, codex risk-based mode mapping
- `amelia/drivers/base.py` — update `execute_agentic` docstring (ApiDriver now supports `allowed_tools`); add `ToolContext` to cross-driver kwargs contract
- `amelia/agents/architect.py`, `oracle.py`, `reviewer.py`, `evaluator.py`, `developer.py` + brainstormer site — pass `allowed_tools=resolve_agent_tools(name)`; delete prompt-level read-only instructions
- `amelia/server/models/events.py` — add `EventType.TOOL_AUDIT`, `TOOL_PERMISSION_REQUIRED`
- `amelia/server/main.py` — assemble `ToolContext` (it already builds the knowledge deps)

---

## 8. Open questions

1. **(biggest) Subtractive enforcement on deepagents.** The whole `allowed_tools` story for ApiDriver rests on `ToolPolicyMiddleware.before_tool` being able to **veto** a tool call from FilesystemMiddleware. Does the installed `deepagents`/`langchain` middleware API actually expose a `before_tool` short-circuit (return a `ToolMessage` without executing), or only an observe-after hook? If it's observe-only, read-only enforcement for Architect/Oracle on the API driver is **impossible without patching deepagents** or wrapping the backend (`LocalSandbox`) to refuse writes by risk. This must be spiked before committing to §3.2/§4.1. (Fallback: a write-denying `LocalSandbox` subclass keyed on the allow-set — moves the gate from middleware to backend.)
2. **`confirm` permission mode in headless pipelines.** Pipelines run autonomously with no human in the loop. Is `confirm` ⇒ `deny` acceptable for v1, or do destructive tools (push, PR create) need an out-of-band approval queue (dashboard) before they can be enabled for `developer`?
3. **Registry mutation safety.** Hermes guards its registry with an `RLock` for live MCP refresh. Amelia registers only at import time and never mutates after — is a plain dict safe forever, or will the planned MCP/skills integration reintroduce runtime mutation and force the lock back in?
4. **Canonical-name authority.** Should `ToolName` be generated *from* the registry (registry as source of truth) or should the registry validate *against* `ToolName` (constants as source of truth)? §1.1 assumes the latter; inverting it removes the dual list but is a bigger refactor of `TOOL_NAME_ALIASES`.
