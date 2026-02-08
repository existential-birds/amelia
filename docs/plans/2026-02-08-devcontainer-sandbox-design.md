# DevContainer Sandbox Design

**Goal:** Sandbox agent execution inside a Docker devcontainer so all LLM calls, tool execution, and file operations run in an isolated environment rather than directly on the host.

**Related:**
- [Trail of Bits claude-code-devcontainer](https://github.com/trailofbits/claude-code-devcontainer)
- [Daytona.io](https://www.daytona.io) (future cloud sandbox provider)

**Implementation Issues:**
- #408 — Parent issue
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
│    ├─→ Write prompt to container (/tmp/prompt.txt)        │
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

### LLM Forwarding

```
Container worker                          Host proxy (:8430)
─────────────────                         ──────────────────

POST /proxy/v1/chat/completions           Receives request
  Body: {model, messages, ...}              │
  No auth header                            ▼
          ─────────────────────→          Attaches Authorization: Bearer sk-or-...
                                          Forwards to openrouter.ai/api/v1/...
          ←─────────────────────          Streams response back
```

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

Extends the ToB base with Amelia worker dependencies.

```dockerfile
FROM ghcr.io/trailofbits/claude-code-devcontainer:latest

COPY pyproject.toml uv.lock /tmp/amelia/
RUN cd /tmp/amelia && uv sync --frozen --no-dev --group sandbox \
    && rm -rf /tmp/amelia

COPY amelia/sandbox/worker.py /opt/amelia/worker.py
COPY amelia/sandbox/scripts/ /opt/amelia/scripts/
RUN chmod +x /opt/amelia/scripts/*.sh

RUN git config --system credential.helper \
    '/opt/amelia/scripts/credential-helper.sh'

USER vscode
WORKDIR /workspace
```

- **`--group sandbox`** — dedicated dependency group: `deepagents`, `pydantic`, `loguru`, `httpx`. Not the full Amelia package.
- **No Amelia source code** in image — only worker + scripts. Keeps image lean.
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
        #   --cap-add NET_ADMIN --cap-add NET_RAW
        #   -e LLM_PROXY_URL=http://host.docker.internal:8430/proxy/v1
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
- **`NET_ADMIN` + `NET_RAW` capabilities** for iptables network allowlist.
- **`sleep infinity`** keeps container alive as daemon. Work happens via `docker exec`.
- **One container per profile.** `amelia-sandbox-work` and `amelia-sandbox-personal` run independently.

## Worker Protocol

The worker is a thin Python entrypoint that runs inside the sandbox. It receives a prompt, runs a DeepAgents agent (or a single-turn LLM call), and streams `AgenticMessage` objects as JSON lines to stdout.

### Modes

```bash
# Agentic execution (tools + LLM)
python -m amelia.sandbox.worker agentic \
    --prompt-file /tmp/prompt.txt \
    --cwd /workspace/worktrees/issue-123 \
    --model anthropic/claude-sonnet-4-5

# Single-turn generation (LLM only, no tools)
python -m amelia.sandbox.worker generate \
    --prompt-file /tmp/prompt.txt \
    --schema EvaluationOutput \
    --model anthropic/claude-sonnet-4-5
```

### Communication Contract

- **stdin:** Not used. Prompt delivered via `--prompt-file` (written by host as `vscode` user).
- **stdout:** One `AgenticMessage` JSON object per line. Nothing else.
- **stderr:** Worker's own loguru logs. Not parsed by host. Available for debugging.
- **Exit code:** 0 = success, non-zero = failure.

### Prompt Delivery

For large prompts, the host writes a prompt file inside the container before invoking the worker. All `docker exec` calls run as the `vscode` user, so files are created with correct ownership:

```bash
docker exec --user vscode amelia-sandbox-work \
    tee /tmp/prompt.txt < prompt_content
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
> `amelia/drivers/factory.py`, `pyproject.toml`
> Depends on: PR 1 (#409) and PR 2 (#410)

---

## ContainerDriver

Implements `DriverInterface`. Both `generate()` and `execute_agentic()` route through the sandbox worker.

```python
class ContainerDriver:
    def __init__(self, model: str, provider: SandboxProvider):
        self.model = model
        self.provider = provider

    async def execute_agentic(self, prompt, cwd, ...):
        await self.provider.ensure_running()
        await self._write_prompt_file(prompt)

        cmd = ["python", "-m", "amelia.sandbox.worker", "agentic",
               "--prompt-file", "/tmp/prompt.txt",
               "--cwd", cwd, "--model", self.model]

        async for line in self.provider.exec_stream(cmd, cwd=cwd):
            yield AgenticMessage.model_validate_json(line)

    async def generate(self, prompt, schema=None, ...):
        await self.provider.ensure_running()
        await self._write_prompt_file(prompt)

        cmd = ["python", "-m", "amelia.sandbox.worker", "generate",
               "--prompt-file", "/tmp/prompt.txt",
               "--model", self.model]
        if schema:
            cmd.extend(["--schema", schema.__name__])

        async for line in self.provider.exec_stream(cmd):
            message = AgenticMessage.model_validate_json(line)
            if message.type == AgenticMessageType.RESULT:
                return message.content, message.session_id
```

Session continuity maps to git worktrees (persistent across calls), not in-memory checkpointers.

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

### Integration Surface

| Existing module | Change | PR |
|----------------|--------|-----|
| `amelia/core/types.py` | Add `SandboxConfig` to profile schema | PR 1 |
| `amelia/server/app.py` | Mount proxy routes at `/proxy/v1/` | PR 1 |
| `pyproject.toml` | Add `[dependency-groups] sandbox = [...]` | PR 2 |
| `amelia/drivers/factory.py` | Add `ContainerDriver` branch when `sandbox.mode == "container"` | PR 3 |
| `amelia/drivers/base.py` | No change | — |
| `amelia/agents/` | No change | — |
| `amelia/server/events/` | No change | — |
| `dashboard/` | No change (MVP) | — |

---

## Implementation Phases

| Phase | What | Depends on | Parallelizable |
|-------|------|-----------|----------------|
| 1 | `SandboxProvider` protocol + `SandboxConfig` model | — | Yes (with 2) |
| 2 | LLM + git credential proxy on existing FastAPI server | — | Yes (with 1) |
| 3 | Dockerfile + devcontainer.json + credential helper script | Phase 2 | — |
| 4 | `DockerSandboxProvider` (lifecycle, exec_stream, health) | Phase 1, 3 | Yes (with 5, 6) |
| 5 | Worker entrypoint (agentic + generate modes, JSON-line streaming) | Phase 3 | Yes (with 4, 6) |
| 6 | Git worktree management (clone, fetch, create, push, cleanup) | Phase 4 | Yes (with 5) |
| 7 | `ContainerDriver` (implements `DriverInterface`) | Phase 4, 5, 6 | — |
| 8 | Driver factory integration + profile config wiring | Phase 7 | — |
| 9 | Network allowlist infrastructure (iptables, config) | Phase 4 | Independent |

### Testable Milestones

- **After Phase 2:** Proxy forwards LLM calls with auth, returns git credentials
- **After Phase 5:** Worker runs inside container, streams JSON lines
- **After Phase 7:** `ContainerDriver.execute_agentic()` yields `AgenticMessage`
- **After Phase 8:** `amelia start ISSUE-123 --profile secure` runs sandboxed end-to-end

---

## Out of Scope (Deferred)

- CLI driver containerization (Claude Code process inside container)
- Cloud sandbox providers (Daytona, Fly.io)
- Pre-built images on GHCR
- Dashboard UI for sandbox management
- Container resource limits (CPU, memory)
