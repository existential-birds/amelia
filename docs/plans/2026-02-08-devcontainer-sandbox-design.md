# DevContainer Sandbox Design

**Goal:** Sandbox agent execution inside a Docker devcontainer so all LLM calls, tool execution, and file operations run in an isolated environment rather than directly on the host.

**Related:**
- [Trail of Bits claude-code-devcontainer](https://github.com/trailofbits/claude-code-devcontainer)
- [Daytona.io](https://www.daytona.io) (future cloud sandbox provider)

**Implementation Issues:**
- #408 — Parent issue
- #415 — ~~Prerequisite: Extract agent schemas into standalone modules~~ (Done: PR #418)
- #409 — PR 1: Foundation (SandboxProvider protocol, SandboxConfig, LLM/git proxy)
- #410 — PR 2: Container + Worker (Dockerfile, DockerSandboxProvider, worker, worktrees)
- #411 — PR 3: Integration (ContainerDriver, factory wiring, network allowlist)

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

---

> **PR 1 — Foundation (#409)**
>
> Scope: `SandboxProvider` protocol, `SandboxConfig` model, LLM + git credential proxy.
> Files: `amelia/sandbox/__init__.py`, `amelia/sandbox/provider.py`, `amelia/sandbox/proxy.py`,
> `amelia/core/types.py`, `amelia/server/app.py`

---

## SandboxProvider Protocol

Transport-agnostic interface for sandbox lifecycle and command execution. Enables future cloud providers (Daytona, Fly.io, etc.) without changing the driver layer.

```python
class SandboxProvider(Protocol):
    """Manages sandbox lifecycle and command execution."""

    async def ensure_running(self) -> None:
        """Ensure the sandbox is ready. Start if not running, no-op if up."""
        ...

    async def exec_stream(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> AsyncIterator[str]:
        """Execute command in sandbox, streaming stdout lines."""
        ...

    async def teardown(self) -> None:
        """Stop and clean up the sandbox."""
        ...

    async def health_check(self) -> bool:
        """Check if the sandbox is responsive."""
        ...
```

MVP implements only `DockerSandboxProvider`. The provider is a singleton per profile — one container shared across all workflows for that profile.

### Future Cloud Providers

The same protocol supports remote execution. The worker, JSON-line streaming, and orchestrator are identical — only the transport changes:

| Provider | Container → Proxy | exec_stream transport |
|----------|-------------------|----------------------|
| Local Docker | `host.docker.internal:8430` | `docker exec` stdout pipe |
| Daytona | Reverse tunnel / Tailscale | Daytona SDK `process.code_run` |
| Fly.io | Fly private network | `fly ssh console` |
| SSH remote | SSH port forward | SSH stdout pipe |

Profile config extends naturally:

```yaml
profiles:
  local:
    sandbox:
      mode: container       # DockerSandboxProvider
  cloud:
    sandbox:
      mode: daytona          # DaytonaSandboxProvider (future)
      daytona_api_key: ${DAYTONA_API_KEY}
```

## Profile Configuration (SandboxConfig)

New `SandboxConfig` nested in profile schema. Defaults preserve current behavior.

```python
class SandboxConfig(BaseModel):
    mode: Literal["none", "container"] = "none"
    image: str = "amelia-sandbox:latest"
    network_allowlist_enabled: bool = False
    network_allowed_hosts: list[str] = Field(default_factory=lambda: [
        "api.anthropic.com",
        "openrouter.ai",
        "api.openai.com",
        "github.com",
        "registry.npmjs.org",
        "pypi.org",
        "files.pythonhosted.org",
    ])
```

## LLM + Git Credential Proxy

A thin reverse proxy mounted on Amelia's existing FastAPI server. The container sends unauthenticated requests to the proxy; the proxy attaches credentials and forwards to the real API.

### Routes

```
/proxy/v1/chat/completions    ← forwards to LLM provider, attaches API key
/proxy/v1/embeddings          ← forwards to LLM provider, attaches API key
/proxy/v1/git/credentials     ← returns token from host's credential store
```

### Profile-Aware LLM Forwarding

The proxy resolves which LLM provider, base URL, and API key to use based on the profile. The worker includes its profile name as a header — it never sees the API key.

```
Container worker                          Host proxy (:8430)
─────────────────                         ──────────────────

POST /proxy/v1/chat/completions           Receives request
  Header: X-Amelia-Profile: work            │
  Body: {model, messages, ...}              ▼
  No auth header                          Looks up profile "work" in DB
          ─────────────────────→            → provider: openrouter
                                            → base_url: openrouter.ai/api/v1
                                            → api_key: sk-or-...
                                          Attaches Authorization: Bearer sk-or-...
                                          Forwards to openrouter.ai/api/v1/...
          ←─────────────────────          Streams response back
```

The `ContainerDriver` passes the profile name to the worker as an env var (`AMELIA_PROFILE`). The worker sets this as the `X-Amelia-Profile` header on all proxy requests. This keeps the proxy stateless — it does not need to track which container belongs to which profile.

### Worker LLM Routing

The worker uses DeepAgents (via `create_deep_agent`) which calls LangChain's `init_chat_model()` to create the LLM. How the worker routes LLM calls through the proxy depends on the provider:

- **Non-OpenRouter models** (e.g., `gpt-4`, `claude-sonnet`): LangChain respects `OPENAI_BASE_URL` and `OPENAI_API_KEY` env vars. The container sets `OPENAI_BASE_URL=http://host.docker.internal:8430/proxy/v1/` and a dummy API key. This works with no code changes.
- **OpenRouter models**: `_create_chat_model()` in `amelia/drivers/api/deepagents.py` hardcodes `base_url="https://openrouter.ai/api/v1"`, which overrides any env var. To support proxy routing, this function must accept an optional `base_url` parameter that defaults to the hardcoded value but can be overridden.

Required change in PR 1 (prerequisite for worker proxy routing):

```python
# amelia/drivers/api/deepagents.py
def _create_chat_model(
    model: str,
    provider: str | None = None,
    base_url: str | None = None,  # NEW — allows proxy override
) -> BaseChatModel:
    if provider == "openrouter":
        resolved_url = base_url or "https://openrouter.ai/api/v1"
        return init_chat_model(model, model_provider="openai", base_url=resolved_url, ...)
```

The worker sets `base_url` from the `LLM_PROXY_URL` env var. This keeps the proxy pattern working for all providers without special-casing per model type.

### Provider Registry

The proxy resolves `profile → agent_config.provider → (base_url, api_key)` using a hardcoded provider registry in `proxy.py`. This mirrors the existing env-var convention used by `_create_chat_model()` in the API driver.

```python
# amelia/sandbox/proxy.py — MVP constant, move to DB-stored config later
PROVIDER_REGISTRY: dict[str, ProviderConfig] = {
    "openrouter": ProviderConfig(
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
    ),
    "anthropic": ProviderConfig(
        base_url="https://api.anthropic.com/v1",
        api_key_env="ANTHROPIC_API_KEY",
    ),
}
```

MVP uses the constant. When users need custom providers via the dashboard, promote this to DB-stored configuration.

### Git Credential Helper

Inside the container, git is configured with a credential helper that calls the proxy:

```bash
#!/bin/bash
# /opt/amelia/scripts/credential-helper.sh
curl -s "http://host.docker.internal:8430/proxy/v1/git/credentials" \
    --data-binary @/dev/stdin
```

The proxy returns credentials from the host's existing store (macOS Keychain, `gh auth`, `git-credential-manager`).

> **PR 1 END**

---

> **PR 2 — Container + Worker (#410)**
>
> Scope: Dockerfile, `DockerSandboxProvider`, worker entrypoint, git worktree management.
> Files: `amelia/sandbox/Dockerfile`, `amelia/sandbox/devcontainer.json`, `amelia/sandbox/scripts/credential-helper.sh`,
> `amelia/sandbox/docker.py`, `amelia/sandbox/worker.py`, `amelia/sandbox/worktree.py`
> Depends on: PR 1 (#409)

---

## Dockerfile

Extends the ToB base with the Amelia package (code only, no heavy deps) plus the sandbox dependency group.

```dockerfile
FROM ghcr.io/trailofbits/claude-code-devcontainer:latest

# Install amelia package code (no transitive deps), then only sandbox-required deps.
# This gives the worker access to:
#   amelia.drivers.base (AgenticMessage, DriverUsage)
#   amelia.agents.schemas (EvaluationOutput, MarkdownPlanOutput, etc.)
# Heavy deps (langgraph, fastapi, asyncpg, langchain) are NOT installed.
COPY . /tmp/amelia/
RUN cd /tmp/amelia \
    && uv pip install --no-deps . \
    && uv pip install deepagents pydantic loguru httpx \
    && rm -rf /tmp/amelia

COPY amelia/sandbox/scripts/ /opt/amelia/scripts/
RUN chmod +x /opt/amelia/scripts/*.sh

RUN git config --system credential.helper \
    '/opt/amelia/scripts/credential-helper.sh'

USER vscode
WORKDIR /workspace
```

- **`--no-deps` + explicit sandbox deps** — installs the `amelia` package for imports, but only the lightweight dependencies the worker actually needs. Heavy deps (LangGraph, FastAPI, asyncpg, langchain) are excluded.
- **Schema extraction (#415) is complete** (PR #418). All schemas the worker imports (`MarkdownPlanOutput`, `EvaluationOutput`, `EvaluatedItem`, `Disposition`, `EvaluationResult`) live in `amelia/agents/schemas/` with pydantic-only import chains.
- **Built locally** on first use. Rebuild triggered when Dockerfile hash changes.

## Container Lifecycle Manager

`DockerSandboxProvider` manages a single long-lived container per profile.

```python
class DockerSandboxProvider(SandboxProvider):
    CONTAINER_NAME = "amelia-sandbox-{profile_name}"
    IMAGE_NAME = "amelia-sandbox:latest"

    async def ensure_running(self) -> None:
        if await self.health_check():
            return
        if not await self._image_exists():
            await self._build_image()
        await self._start_container()
        await self._wait_for_ready(timeout=30)

    async def _start_container(self) -> None:
        # docker run -d --name amelia-sandbox-{profile}
        #   --add-host=host.docker.internal:host-gateway
        #   --cap-add NET_ADMIN --cap-add NET_RAW
        #   -e LLM_PROXY_URL=http://host.docker.internal:8430/proxy/v1
        #   -e AMELIA_PROFILE={profile_name}
        #   amelia-sandbox:latest sleep infinity

    async def exec_stream(self, command, cwd=None, env=None, stdin=None):
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", "--user", "vscode",
            *(["--workdir", cwd] if cwd else []),
            self.container_name, *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        async for line in proc.stdout:
            yield line.decode().rstrip("\n")

    async def health_check(self) -> bool:
        # docker inspect --format '{{.State.Running}}'

    async def teardown(self) -> None:
        # docker rm -f {container_name}
```

Key details:
- **No bind-mounts.** Container has its own filesystem. Code enters via `git clone` inside the container.
- **No API keys.** Only `LLM_PROXY_URL` is passed as env var. Keys stay on the host.
- **`--add-host=host.docker.internal:host-gateway`** included unconditionally. Redundant on macOS/Windows (Docker Desktop provides it natively) but essential on Linux (Docker 20.10+). Always including it avoids platform detection.
- **`NET_ADMIN` + `NET_RAW` capabilities** for iptables network allowlist.
- **`sleep infinity`** keeps container alive as daemon. Work happens via `docker exec`.
- **One container per profile.** `amelia-sandbox-work` and `amelia-sandbox-personal` run independently.

## Worker Protocol

The worker is a thin Python entrypoint that runs inside the sandbox. It receives a prompt, runs a DeepAgents agent (or a single-turn LLM call), and streams `AgenticMessage` objects as JSON lines to stdout.

### Modes

```bash
# Agentic execution (tools + LLM)
python -m amelia.sandbox.worker agentic \
    --prompt-file /tmp/prompt-issue-123.txt \
    --cwd /workspace/worktrees/issue-123 \
    --model anthropic/claude-sonnet-4-5

# Single-turn generation (LLM only, no tools)
python -m amelia.sandbox.worker generate \
    --prompt-file /tmp/prompt-issue-123.txt \
    --schema amelia.agents.schemas.evaluator:EvaluationOutput \
    --model anthropic/claude-sonnet-4-5
```

The `--schema` argument takes a fully qualified `module:ClassName` path. The worker dynamically imports the class, uses it with `ToolStrategy(schema=schema)` for the LLM call, and serializes the resulting Pydantic model instance as JSON in the `AgenticMessage.content` field. Since the `amelia` package is installed in the container (via `--no-deps`), all schema classes in `amelia.agents.schemas.*` are importable.

### Communication Contract

- **stdin:** Not used. Prompt delivered via `--prompt-file` (written by host as `vscode` user).
- **stdout:** One `AgenticMessage` JSON object per line. Nothing else.
- **Final stdout line:** `AgenticMessage` with `type=USAGE` containing accumulated `DriverUsage` in the `usage` field. Emitted by the worker after execution completes, before exit. The `ContainerDriver` captures this and stores it for `get_usage()`.
- **stderr:** Worker's own loguru logs. Not parsed by host. Available for debugging.
- **Exit code:** 0 = success, non-zero = failure.
- **Prompt file cleanup:** `ContainerDriver` removes `/tmp/prompt-{workflow_id}.txt` in a `try/finally` block after each invocation. Cleanup failures are logged but not raised.

### Changes to AgenticMessage

The worker protocol requires two additions to existing types in `amelia/drivers/base.py`:

```python
class AgenticMessageType(StrEnum):
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    RESULT = "result"
    USAGE = "usage"          # NEW — final line with accumulated usage data

class AgenticMessage(BaseModel):
    # ... existing fields ...
    usage: DriverUsage | None = None  # Populated only for type=USAGE
```

The `USAGE` message is not yielded to callers — it is consumed internally by `ContainerDriver` to populate `get_usage()`. The `to_workflow_event()` mapping does not need a `USAGE` entry since it never reaches the event bus.

### Prompt Delivery

For large prompts, the host writes a prompt file inside the container before invoking the worker. Prompt files are namespaced per workflow to avoid collisions when multiple workflows share one container (`AMELIA_MAX_CONCURRENT > 1`). All `docker exec` calls run as the `vscode` user, so files are created with correct ownership:

```bash
docker exec --user vscode amelia-sandbox-work \
    tee /tmp/prompt-{workflow_id}.txt < prompt_content
```

## Git Worktree Management

Each workflow gets an isolated git worktree inside the container.

### Filesystem Layout

```
/workspace/
    repo/                    ← bare clone (shared across workflows)
        .git/
    worktrees/
        issue-123/           ← worktree for workflow 1
        issue-456/           ← worktree for workflow 2
```

### Lifecycle

```
1. First workflow for this repo:
   git clone --bare <repo-url> /workspace/repo

2. Subsequent workflows:
   git -C /workspace/repo fetch origin

3. Create worktree:
   git -C /workspace/repo worktree add \
       /workspace/worktrees/issue-123 -b issue-123 origin/main

4. Worker executes with cwd=/workspace/worktrees/issue-123

5. On success:
   git -C /workspace/worktrees/issue-123 push origin issue-123

6. On completion (success or failure):
   git -C /workspace/repo worktree remove /workspace/worktrees/issue-123
```

- **Bare clone** as shared base — no checkout, only worktrees have working files.
- **Fetch before worktree** — ensures branching from latest remote state.
- **Branch naming** matches Amelia's existing convention (issue identifier).

> **PR 2 END**

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

### Prerequisites

| Change | Issue | Status |
|--------|-------|--------|
| Extract agent schemas into `amelia/agents/schemas/` | #415 | Done (PR #418) |
| Add `base_url` parameter to `_create_chat_model()` | PR 1 | Pending |

#### Schema Extraction (#415) — Completed

PR #418 extracted all schema classes to `amelia/agents/schemas/` with pydantic-only import chains:

| Class | Location |
|-------|----------|
| `MarkdownPlanOutput` | `amelia/agents/schemas/architect.py` |
| `EvaluationOutput` | `amelia/agents/schemas/evaluator.py` |
| `EvaluatedItem` | `amelia/agents/schemas/evaluator.py` |
| `EvaluationResult` | `amelia/agents/schemas/evaluator.py` |
| `Disposition` | `amelia/agents/schemas/evaluator.py` |

All re-exported from `amelia/agents/schemas/__init__.py`. Import paths updated across agents, pipelines, and tests.

**Classes already safe (no extraction needed):**

| Class | File | Why safe |
|-------|------|----------|
| `AgenticMessage` | `amelia/drivers/base.py` | Only imports from stdlib + pydantic; `WorkflowEvent` import is behind `TYPE_CHECKING` |
| `AgenticMessageType` | `amelia/drivers/base.py` | stdlib `StrEnum` only |
| `DriverUsage` | `amelia/drivers/base.py` | `BaseModel` only |

### Integration Surface

| Existing module | Change | PR |
|----------------|--------|-----|
| `amelia/core/types.py` | Add `SandboxConfig` to profile schema | PR 1 |
| `amelia/server/app.py` | Mount proxy routes at `/proxy/v1/` (profile-aware: reads `X-Amelia-Profile` header to resolve provider config) | PR 1 |
| `amelia/drivers/api/deepagents.py` | Add optional `base_url` parameter to `_create_chat_model()` for proxy routing (currently hardcodes OpenRouter URL) | PR 1 |
| `pyproject.toml` | No `sandbox` dependency group needed — Dockerfile installs deps directly | PR 2 |
| `amelia/drivers/factory.py` | Add `ContainerDriver` branch when `sandbox.mode == "container"` | PR 3 |
| `amelia/drivers/base.py` | Add `USAGE` to `AgenticMessageType`, add `usage: DriverUsage \| None` field to `AgenticMessage` | PR 2 |
| `amelia/agents/` | No change (schemas already extracted per #415) | — |
| `amelia/server/events/` | No change | — |
| `dashboard/` | No change (MVP) | — |

---

## Implementation Phases

| Phase | What | Depends on | Parallelizable |
|-------|------|-----------|----------------|
| 0 | ~~Extract agent schemas into `amelia/agents/schemas/` (#415)~~ | — | Done (PR #418) |
| 1 | `SandboxProvider` protocol + `SandboxConfig` model | — | Yes (with 2) |
| 2 | LLM + git credential proxy on existing FastAPI server (profile-aware) | — | Yes (with 1) |
| 3 | Dockerfile + devcontainer.json + credential helper script | Phase 0, 2 | — |
| 4 | `DockerSandboxProvider` (lifecycle, exec_stream, health) | Phase 1, 3 | Yes (with 5, 6) |
| 5 | Worker entrypoint (agentic + generate modes, JSON-line streaming, schema round-trip) | Phase 3 | Yes (with 4, 6) |
| 6 | Git worktree management (clone, fetch, create, push, cleanup) | Phase 4 | Yes (with 5) |
| 7 | `ContainerDriver` (implements `DriverInterface`, schema deserialization) | Phase 4, 5, 6 | — |
| 8 | Driver factory integration + profile config wiring | Phase 7 | — |
| 9 | Network allowlist infrastructure (iptables, config) | Phase 4 | Independent |

### Testable Milestones

- ~~**After Phase 0:** `from amelia.agents.schemas.evaluator import EvaluationOutput` works with only pydantic installed~~ (Done)
- **After Phase 2:** Proxy forwards LLM calls with auth (profile-aware), returns git credentials
- **After Phase 5:** Worker runs inside container, streams JSON lines; `generate --schema` serializes Pydantic model as JSON
- **After Phase 7:** `ContainerDriver.generate(schema=EvaluationOutput)` returns a model instance (not string); `execute_agentic()` yields `AgenticMessage`
- **After Phase 8:** `amelia start ISSUE-123 --profile secure` runs sandboxed end-to-end

---

## Out of Scope (Deferred)

- CLI driver containerization (Claude Code process inside container)
- Cloud sandbox providers (Daytona, Fly.io)
- Pre-built images on GHCR
- Dashboard UI for sandbox management
- Container resource limits (CPU, memory)
