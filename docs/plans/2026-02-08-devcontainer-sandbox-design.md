# DevContainer Sandbox Design

**Goal:** Sandbox agent execution inside a Docker devcontainer so all LLM calls, tool execution, and file operations run in an isolated environment rather than directly on the host.

**Related:**
- [Trail of Bits claude-code-devcontainer](https://github.com/trailofbits/claude-code-devcontainer)
- [Daytona.io](https://www.daytona.io) (future cloud sandbox provider)

**Implementation Issues:**
- #408 — Parent issue
- #415 — ~~Prerequisite: Extract agent schemas into standalone modules~~ (Done: PR #418, merged)
- #409 — ~~PR 1: Foundation (SandboxProvider protocol, SandboxConfig, LLM/git proxy)~~ (Done: PR #419, merged)
- #410 — ~~PR 2: Container + Worker (Dockerfile, DockerSandboxProvider, worker, worktrees)~~ (Done: PR #424, merged)
- #411 — PR 3: Integration (ContainerDriver, factory wiring, network allowlist) — Not started

---

## Background

Amelia's agents execute shell commands and file operations directly on the host machine. The API driver uses `LocalSandbox` which runs `subprocess.run(shell=True)` with no isolation. The CLI driver spawns Claude Code with `bypass_permissions=True`. Both give agents full access to the host filesystem, processes, and network.

The Trail of Bits `claude-code-devcontainer` project demonstrates a Docker-based sandbox for running Claude Code with unrestricted permissions safely. This design adapts that approach for Amelia's API driver execution model, with an architecture that extends naturally to cloud sandbox providers like Daytona.io in the future.

---

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Target driver (MVP) | API driver only | Clean integration via `SandboxBackendProtocol`. CLI driver deferred. |
| Container lifecycle | Amelia-managed | `amelia dev`/`amelia start` starts container, `amelia stop` tears down. Best UX. |
| Configuration level | Profile-level `sandbox` field | Different profiles can have different sandbox modes. Fits existing pattern. |
| Worktree management | Automatic inside container | Orchestrator creates/cleans up git worktrees per workflow. User never thinks about it. |
| Base image | Fork ToB devcontainer | Already has Ubuntu 24.04, Python 3.13, Node 22, uv, iptables. Thin layer on top. |
| Network isolation | Allowlist infrastructure, disabled by default | Plumbing in place, users opt in via profile config. |
| Image distribution | Dockerfile in-repo, built locally | Simple, no registry dependency, users can customize. |
| Agent execution | Inside container (not just tool execution) | All LLM calls and file I/O run inside the container. No bind-mounts. Full isolation. |
| API key management | Host proxy — keys never enter the container | LLM and git credentials served by proxy on host. Works for local and future cloud. |
| Git authentication | Host proxy credential helper from day one | No shortcuts. Container's git credential helper talks to host proxy. |
| Usage tracking | Worker emits final `USAGE` message via JSON-line protocol | Worker has access to DeepAgents' accumulated `usage_metadata`. Emitting it as a final `AgenticMessage` keeps cost tracking working across all drivers with no special-casing. |
| Session cleanup | No-op (`return False`), same as `ClaudeCliDriver` | Session state lives in git worktrees, managed at workflow level by `worktree.py`. No in-memory checkpointer to clean up. |
| Amelia in container | Install package with `--no-deps`, then only sandbox deps | Worker imports `AgenticMessage`, schema classes, and `DriverUsage` directly. No type duplication. Heavy deps (LangGraph, FastAPI, asyncpg) excluded. Schema extraction completed in PR #418. |
| Schema round-trip | Worker serializes Pydantic model as JSON in `content`; driver reconstructs | `generate()` with `schema` must return a model instance, not a string. Worker calls `model.model_dump_json()`, `ContainerDriver` calls `schema.model_validate_json(content)`. |
| Proxy profile routing | Worker sends `X-Amelia-Profile` header; proxy resolves provider config | Different profiles use different LLM providers/keys/base URLs. Proxy looks up the profile's config to determine upstream and credentials. |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Host                                                     │
│                                                           │
│  Orchestrator (LangGraph)                                 │
│    │                                                      │
│    ▼                                                      │
│  ContainerDriver.execute_agentic()                        │
│    │                                                      │
│    ├─→ Write prompt to container (/tmp/prompt-{wf}.txt)   │
│    ├─→ docker exec ... python -m amelia.sandbox.worker    │
│    │       │                                              │
│    │       │  stdout (JSON lines)                         │
│    │       ← AgenticMessage per line ──────────────────   │
│    │                                                      │
│    ├─→ parse JSON → AgenticMessage                        │
│    ├─→ yield to Developer.run()                           │
│    ├─→ yield to call_developer_node()                     │
│    └─→ event_bus.emit(event)                              │
│        → WebSocket → Dashboard                            │
│                                                           │
│  LLM + Git Credential Proxy (:8430/proxy/v1/)            │
│    ├─→ /proxy/v1/chat/completions  (attaches LLM key)    │
│    ├─→ /proxy/v1/embeddings        (attaches LLM key)    │
│    └─→ /proxy/v1/git/credentials   (returns git token)   │
│                                                           │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │
│                                                           │
│  ┌────────────────────────────────────────────────────┐   │
│  │  DevContainer (amelia-sandbox-{profile})            │   │
│  │                                                     │   │
│  │  Worker process (python -m amelia.sandbox.worker)   │   │
│  │    │                                                │   │
│  │    ├─→ LLM calls → http://host.docker.internal:     │   │
│  │    │     8430/proxy/v1/  (proxy attaches keys)      │   │
│  │    │                                                │   │
│  │    ├─→ backend.read()    (inside container)         │   │
│  │    ├─→ backend.write()   (inside container)         │   │
│  │    ├─→ backend.execute() (inside container)         │   │
│  │    │                                                │   │
│  │    └─→ stdout: AgenticMessage JSON lines            │   │
│  │                                                     │   │
│  │  /workspace/                                        │   │
│  │    repo/              (bare clone)                  │   │
│  │    worktrees/                                       │   │
│  │      issue-123/       (git worktree for workflow 1) │   │
│  │      issue-456/       (git worktree for workflow 2) │   │
│  │                                                     │   │
│  │  iptables allowlist (disabled by default)           │   │
│  └────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

### Security Boundary

The container provides full isolation for agent execution:

| Threat | Protected | How |
|--------|-----------|-----|
| Agent deletes host files | Yes | No bind-mount, no host filesystem access |
| Agent installs malware on host | Yes | Process isolation |
| Agent reads ~/.ssh/, ~/.aws/ | Yes | Not mounted |
| Agent destroys project files | Contained | Only the container's clone is affected, git recovers |
| Agent exfiltrates data | When enabled | Network allowlist restricts outbound traffic |
| API key exposure | Yes | Keys never enter container, proxy pattern |

### Why Not Bind-Mounts

An earlier iteration of this design used bind-mounts (`-v project:/workspace`). This was rejected because bind-mounts give the container read/write/delete access to the mounted host directory. A rogue `rm -rf /workspace/` inside the container would destroy host files through the mount. The clone-inside-container approach means the agent only has access to its own copy.

### Streaming Events

The container boundary is transparent to the event streaming pipeline. The driver yields `AgenticMessage` objects (parsed from JSON lines on stdout), which flow through the existing path unchanged:

```
ContainerDriver.execute_agentic()  ← yields AgenticMessage (from JSON lines)
    → Developer.run()              ← converts to (state, WorkflowEvent)
    → call_developer_node()        ← event_bus.emit(event)
    → EventBus                     ← subscribers + ConnectionManager
    → WebSocket                    ← Dashboard
```

No changes to agents, orchestrator, event bus, connection manager, or dashboard.

---

> **PR 3 — Integration (#411)**
>
> Scope: `ContainerDriver`, driver factory wiring, network allowlist infrastructure.
> Files: `amelia/sandbox/driver.py`, `amelia/sandbox/network.py`, `amelia/sandbox/scripts/setup-network.sh`,
> `amelia/drivers/factory.py`
> Depends on: PR 1 (#409) and PR 2 (#410)

---

## ContainerDriver

Implements `DriverInterface`. Both `generate()` and `execute_agentic()` route through the sandbox worker.

### Protocol Conformance

`DriverInterface` does not include `workflow_id` in its method signatures. `ContainerDriver` receives it via `**kwargs` — agents pass it when calling the driver. This avoids breaking the protocol while giving the driver what it needs to namespace prompt files.

`ContainerDriver` is stateless with respect to `session_id`. It accepts the parameter (per the protocol) but does not maintain conversation history across invocations. This is safe because:
- The pipeline explicitly clears `driver_session_id` between tasks
- Agents don't share sessions across the Architect → Developer → Reviewer boundary
- Within a single agentic invocation, DeepAgents maintains its own internal conversation state

```python
class ContainerDriver:
    def __init__(self, model: str, provider: SandboxProvider):
        self.model = model
        self.provider = provider
        self._usage: DriverUsage | None = None

    async def execute_agentic(
        self,
        prompt: str,
        cwd: str,
        session_id: str | None = None,
        instructions: str | None = None,
        schema: type[BaseModel] | None = None,
        allowed_tools: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[AgenticMessage]:
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        workflow_id = kwargs.get("workflow_id", uuid4().hex[:8])
        self._usage = None
        await self.provider.ensure_running()
        prompt_file = f"/tmp/prompt-{workflow_id}.txt"
        await self._write_prompt_file(prompt, prompt_file)

        cmd = ["python", "-m", "amelia.sandbox.worker", "agentic",
               "--prompt-file", prompt_file,
               "--cwd", cwd, "--model", self.model]
        if instructions:
            cmd.extend(["--instructions", instructions])

        try:
            async for line in self.provider.exec_stream(cmd, cwd=cwd):
                try:
                    message = AgenticMessage.model_validate_json(line)
                except (json.JSONDecodeError, ValidationError) as e:
                    raise RuntimeError(
                        f"Invalid AgenticMessage from worker: {e}\n"
                        f"Line: {line[:200]}"
                    ) from e
                if message.type == AgenticMessageType.USAGE:
                    self._usage = message.usage
                else:
                    yield message
        finally:
            await self._cleanup_prompt_file(prompt_file)

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        schema: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> GenerateResult:
        """Collect JSON lines from worker and return result.

        Uses async for internally to collect lines (same pattern as
        ClaudeCliDriver.generate), but is NOT an async generator —
        returns a single GenerateResult tuple.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        workflow_id = kwargs.get("workflow_id", uuid4().hex[:8])
        self._usage = None
        await self.provider.ensure_running()
        prompt_file = f"/tmp/prompt-{workflow_id}.txt"
        await self._write_prompt_file(prompt, prompt_file)

        cmd = ["python", "-m", "amelia.sandbox.worker", "generate",
               "--prompt-file", prompt_file,
               "--model", self.model]
        if schema:
            module = schema.__module__
            cmd.extend(["--schema", f"{module}:{schema.__name__}"])

        try:
            async for line in self.provider.exec_stream(cmd):
                try:
                    message = AgenticMessage.model_validate_json(line)
                except (json.JSONDecodeError, ValidationError) as e:
                    raise RuntimeError(
                        f"Invalid AgenticMessage from worker: {e}\n"
                        f"Line: {line[:200]}"
                    ) from e
                if message.type == AgenticMessageType.USAGE:
                    self._usage = message.usage
                elif message.type == AgenticMessageType.RESULT:
                    if schema:
                        try:
                            output = schema.model_validate_json(message.content)
                        except ValidationError as e:
                            raise RuntimeError(
                                f"Worker output did not match schema "
                                f"{schema.__name__}: {e}"
                            ) from e
                    else:
                        output = message.content
                    return output, None
        except (ValueError, RuntimeError):
            raise
        except Exception as e:
            raise RuntimeError(f"Worker execution failed: {e}") from e
        finally:
            await self._cleanup_prompt_file(prompt_file)

        raise RuntimeError("Worker did not emit a RESULT message")

    def get_usage(self) -> DriverUsage | None:
        return self._usage

    def cleanup_session(self, session_id: str) -> bool:
        return False

    async def _cleanup_prompt_file(self, prompt_file: str) -> None:
        """Remove prompt file from container after execution."""
        try:
            async for _ in self.provider.exec_stream(["rm", "-f", prompt_file]):
                pass
        except Exception:
            logger.debug("Failed to clean prompt file", path=prompt_file)
```

### Design Notes

- **Schema round-trip:** `generate()` returns `GenerateResult = tuple[Any, str | None]`. The JSON-line boundary requires serialization: the worker calls `model.model_dump_json()` to serialize into `AgenticMessage.content`, and `ContainerDriver` calls `schema.model_validate_json(content)` to reconstruct the instance. Without this, callers like `Evaluator.evaluate()` (which accesses `response.evaluated_items`) would receive a string and fail.
- **Usage tracking:** The worker emits a final `USAGE` message with accumulated `DriverUsage`. `ContainerDriver` captures it during streaming and stores it for `get_usage()`. This keeps cost tracking working across all drivers.
- **Session semantics:** Returns `None` for session_id (stateless). Returns `False` from `cleanup_session()`, same as `ClaudeCliDriver`. Worktree lifecycle is managed by `worktree.py`, not through the driver interface.
- **Prompt file cleanup:** `try/finally` ensures prompt files are removed from the container after every invocation, preventing accumulation across workflows.

### Error Contract

The error handling follows the same pattern as `ApiDriver` and `ClaudeCliDriver`:

| Failure | Exception | Rationale |
|---------|-----------|-----------|
| Empty prompt | `ValueError` | Input validation, caller's fault |
| Malformed JSON on stdout | `RuntimeError` | Communication contract broken — worker is corrupt or misconfigured. Don't skip lines; raise immediately. |
| Valid JSON but not `AgenticMessage` | `RuntimeError` | Same — Pydantic `ValidationError` wrapped with context |
| Schema deserialization mismatch | `RuntimeError` | Worker sent valid JSON but doesn't match caller's schema |
| Worker exits non-zero | `RuntimeError` | Surfaced via `exec_stream` raising or empty output |
| Docker exec failure | `RuntimeError` | Container down, OOM-killed, etc. |
| LLM/git proxy unreachable | Worker exits non-zero | stderr has connection details for debugging |

Exceptions are fatal and propagate to the orchestrator. The Developer agent does not catch driver exceptions — they bubble up to the workflow retry logic. For LLM-detected task failures (as opposed to infrastructure failures), the worker emits `AgenticMessage(type=RESULT, is_error=True)` which the agent handles via the normal `message.is_error` path.

## Network Allowlist

Ships disabled by default. Infrastructure in place for users to enable via profile config.

### Configuration

```yaml
sandbox:
  mode: container
  network_allowlist_enabled: true
  network_allowed_hosts:
    - api.anthropic.com
    - openrouter.ai
    - api.openai.com
    - github.com
    - registry.npmjs.org
    - pypi.org
    - files.pythonhosted.org
```

### Implementation

On container start, if `network_allowlist_enabled: true`, the provider runs an iptables setup script:

```bash
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

# Host proxy is always allowed (LLM + git credentials)
iptables -A OUTPUT -d host.docker.internal -j ACCEPT

# Configured hosts
for host in allowed_hosts:
    iptables -A OUTPUT -d $(dig +short $host) -j ACCEPT
done

iptables -A OUTPUT -j DROP
```

## Driver Factory Wiring

Driver factory creates `ContainerDriver` when `sandbox.mode == "container"`, transparent to all callers:

```python
# amelia/drivers/factory.py
def get_driver(..., sandbox_config: SandboxConfig | None = None):
    if sandbox_config and sandbox_config.mode == "container":
        provider = DockerSandboxProvider(config=sandbox_config, ...)
        return ContainerDriver(model=model, provider=provider)
    elif driver_key == "api":
        return ApiDriver(model=model, ...)
    elif driver_key == "cli":
        return ClaudeCliDriver(model=model, ...)
```

> **PR 3 END**

---

## Module Layout

```
amelia/sandbox/
    __init__.py
    provider.py              ← SandboxProvider protocol          (PR 1)
    proxy.py                 ← LLM + git credential proxy        (PR 1)
    docker.py                ← DockerSandboxProvider              (PR 2)
    worker.py                ← Entrypoint that runs in container  (PR 2)
    worktree.py              ← Git worktree lifecycle             (PR 2)
    driver.py                ← ContainerDriver                    (PR 3)
    network.py               ← Iptables allowlist generation      (PR 3)
    Dockerfile                                                    (PR 2)
    devcontainer.json                                             (PR 2)
    scripts/
        credential-helper.sh                                      (PR 2)
        setup-network.sh                                          (PR 3)
```

### Remaining Integration Surface (PR 3)

| Existing module | Change |
|----------------|--------|
| `amelia/drivers/factory.py` | Add `ContainerDriver` branch when `sandbox.mode == "container"` |

---

## Remaining Implementation Phases (PR 3 — #411)

Phases 0–6 are complete (PR #418, #419, #424). Remaining work:

| Phase | What | Depends on | Parallelizable |
|-------|------|-----------|----------------|
| 7 | `ContainerDriver` (implements `DriverInterface`, schema deserialization) | Phase 4, 5, 6 | — |
| 8 | Driver factory integration + profile config wiring | Phase 7 | — |
| 9 | Network allowlist infrastructure (iptables, config) | Phase 4 | Independent |

### Testable Milestones

- **After Phase 7:** `ContainerDriver.generate(schema=EvaluationOutput)` returns a model instance (not string); `execute_agentic()` yields `AgenticMessage`
- **After Phase 8:** `amelia start ISSUE-123 --profile secure` runs sandboxed end-to-end

---

## Out of Scope (Deferred)

- CLI driver containerization (Claude Code process inside container)
- Cloud sandbox providers (Daytona, Fly.io)
- Pre-built images on GHCR
- Dashboard UI for sandbox management
- Container resource limits (CPU, memory)
