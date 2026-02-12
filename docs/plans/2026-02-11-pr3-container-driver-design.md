# PR 3 — ContainerDriver, Factory Wiring, Network Allowlist

**Issue:** #411
**Depends on:** PR #419 (merged), PR #424 (merged)
**Branch:** `feat/sandbox-container-driver`

---

## Summary

This PR completes the DevContainer sandbox feature by adding `ContainerDriver` (implements `DriverInterface`), wiring it into the driver factory, adding network allowlist infrastructure, and integrating sandbox teardown into the server lifecycle.

**New files:**
- `amelia/sandbox/driver.py` — ContainerDriver
- `amelia/sandbox/network.py` — iptables allowlist generation
- `amelia/sandbox/scripts/setup-network.sh` — applies network rules inside container

**Modified files:**
- `amelia/core/types.py` — AgentConfig gains `sandbox` and `profile_name` fields; `get_agent_config()` injects them
- `amelia/drivers/factory.py` — fully typed signature, ContainerDriver branch
- `amelia/agents/*.py` — one-line change per agent to pass new config fields to `get_driver()`
- `amelia/server/main.py` — sandbox teardown in lifespan shutdown
- `amelia/sandbox/__init__.py` — export ContainerDriver

---

## 1. ContainerDriver

Implements `DriverInterface`. Delegates execution to a container worker via `SandboxProvider.exec_stream()`.

### `execute_agentic()`

1. Validates prompt is non-empty (raises `ValueError`).
2. Calls `provider.ensure_running()`.
3. Writes prompt to a temp file in the container via `provider.exec_stream()` with `stdin` parameter piped into `tee /tmp/prompt-{workflow_id}.txt`.
4. Runs `python -m amelia.sandbox.worker agentic --prompt-file ... --cwd ... --model ...`.
5. Parses each stdout line as `AgenticMessage` via `model_validate_json()`.
6. Yields all messages except `USAGE` (captured for `get_usage()`).
7. Cleans up prompt file in `try/finally` via `provider.exec_stream(["rm", "-f", path])`.

### `generate()`

Same pattern with `generate` subcommand. Collects lines until a `RESULT` message. If `schema` is provided, deserializes content via `schema.model_validate_json(content)` and returns the model instance. Returns `GenerateResult = tuple[Any, str | None]`.

### `cleanup_session()`

Returns `False`. Stateless — same as `ClaudeCliDriver`. Worktree lifecycle is managed by `worktree.py`.

### Error Contract

| Failure | Exception | Rationale |
|---------|-----------|-----------|
| Empty prompt | `ValueError` | Input validation, caller's fault |
| Malformed JSON on stdout | `RuntimeError` | Worker is corrupt or misconfigured. Raise immediately, no line-skipping. |
| Valid JSON but not `AgenticMessage` | `RuntimeError` | Pydantic `ValidationError` wrapped with context |
| Schema deserialization mismatch | `RuntimeError` | Worker sent valid JSON but doesn't match caller's schema |
| Worker exits without RESULT | `RuntimeError` | `"Worker did not emit a RESULT message"` |
| Docker exec failure | `RuntimeError` | Container down, OOM-killed, etc. Surfaced via `exec_stream` |

---

## 2. Config Threading

Sandbox config flows: `Profile.sandbox` → `AgentConfig` (injected) → `get_driver()` → `ContainerDriver`.

### AgentConfig Changes

Add two fields with defaults so existing stored configs are unaffected:

```python
class AgentConfig(BaseModel):
    driver: DriverType
    model: str
    options: dict[str, Any] = Field(default_factory=dict)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    profile_name: str = "default"
```

### Profile.get_agent_config() Injection

Inject profile-level `sandbox` and `name` at read time. No DB schema change — these fields are not stored per-agent:

```python
def get_agent_config(self, agent_name: str) -> AgentConfig:
    if agent_name not in self.agents:
        raise ValueError(f"Agent '{agent_name}' not configured in profile '{self.name}'")
    return self.agents[agent_name].model_copy(
        update={"sandbox": self.sandbox, "profile_name": self.name}
    )
```

### Agent Constructors

Unchanged signature, one-line body change:

```python
def __init__(self, config: AgentConfig):
    self.driver = get_driver(
        config.driver,
        model=config.model,
        sandbox_config=config.sandbox,
        profile_name=config.profile_name,
        options=config.options,
    )
```

---

## 3. Driver Factory

Fully typed signature — no `**kwargs` for core parameters:

```python
def get_driver(
    driver_key: str,
    *,
    model: str = "",
    cwd: str | None = None,
    sandbox_config: SandboxConfig | None = None,
    profile_name: str = "default",
    options: dict[str, Any] | None = None,
) -> DriverInterface:
    if sandbox_config and sandbox_config.mode == "container":
        if driver_key.startswith("cli"):
            raise ValueError(
                "Container sandbox requires API driver. "
                "CLI driver containerization is not yet supported."
            )
        provider = DockerSandboxProvider(
            profile_name=profile_name,
            image=sandbox_config.image,
        )
        return ContainerDriver(model=model, provider=provider)

    # ... existing api/cli logic using options dict for driver-specific params
```

### Provider Lifecycle

Each `get_driver()` call creates a new `DockerSandboxProvider` instance, but all instances for the same profile point to the same container (`amelia-sandbox-{profile}`). This is safe because:

- `ensure_running()` is idempotent — checks health first, only starts if needed.
- The container is long-lived (`sleep infinity`).
- Concurrent calls from Architect, Developer, and Reviewer are safe.

No shared singleton or provider registry needed.

### CLI + Container Guard

`driver_key.startswith("cli")` + `sandbox.mode == "container"` raises `ValueError` immediately. Claude Code containerization is out of scope for this PR.

---

## 4. Network Allowlist

Ships disabled by default. Infrastructure in place for users to enable via `profile.sandbox.network_allowlist_enabled`.

### `amelia/sandbox/network.py`

Pure function — generates iptables rules from config:

```python
def generate_allowlist_rules(
    allowed_hosts: list[str],
    proxy_host: str = "host.docker.internal",
) -> str:
```

Returns a shell script string with rules in order:
1. Allow established/related connections
2. Allow loopback
3. Allow DNS (UDP + TCP port 53)
4. Allow proxy host (LLM + git credentials)
5. Resolve and allow each configured host
6. `DROP` everything else

No side effects — pure string generation.

### `amelia/sandbox/scripts/setup-network.sh`

Thin wrapper that receives generated rules and applies them with `iptables`. Runs inside the container with `NET_ADMIN` capability (already granted by `DockerSandboxProvider._start_container()`).

### Integration

`DockerSandboxProvider.ensure_running()` runs the setup script after container start, only when `network_allowlist_enabled: true`. This requires `DockerSandboxProvider` to accept `SandboxConfig` (or the relevant fields) in its constructor:

```python
provider = DockerSandboxProvider(
    profile_name=profile_name,
    image=sandbox_config.image,
    network_allowlist_enabled=sandbox_config.network_allowlist_enabled,
    network_allowed_hosts=sandbox_config.network_allowed_hosts,
)
```

---

## 5. Server Lifecycle & Teardown

### Teardown on Shutdown

Query Docker directly at shutdown — no provider registry needed. A utility function finds and stops all sandbox containers:

```python
async def teardown_all_sandbox_containers() -> None:
    """Stop all amelia-sandbox-* containers."""
```

Runs `docker ps -q --filter name=amelia-sandbox-` and `docker rm -f` on results. Also handles orphaned containers from previous crashes.

### Lifespan Integration

Register as an `exit_stack` callback early (like proxy cleanup), so it runs even if startup fails partway:

```python
exit_stack.push_async_callback(teardown_all_sandbox_containers)
```

Shutdown order:
1. `event_bus.cleanup()`
2. `connection_manager.close_all()`
3. `health_checker.stop()`
4. `lifecycle.shutdown()`
5. `teardown_all_sandbox_containers()` ← new
6. `exit_stack.aclose()` (proxy, checkpointer)
7. `database.close()`

---

## 6. Testing Strategy

Unit tests only — mock `SandboxProvider` protocol, no Docker required in CI.

### `tests/unit/sandbox/test_container_driver.py`

| Test | What it verifies |
|------|------------------|
| `execute_agentic` happy path | JSON lines parsed into AgenticMessage, USAGE captured not yielded, `get_usage()` returns DriverUsage |
| `generate` happy path | Returns `GenerateResult` tuple, USAGE captured |
| Schema round-trip | `generate(schema=Model)` returns Pydantic model instance via `model_validate_json` |
| Schema validation failure | Invalid JSON for schema raises `RuntimeError` |
| Empty prompt | Both methods raise `ValueError` |
| Malformed JSON | `RuntimeError` immediately, no line-skipping |
| Missing RESULT | `RuntimeError("Worker did not emit a RESULT message")` |
| Prompt file lifecycle | Write + cleanup called via provider; cleanup runs even on exception |
| `cleanup_session()` | Returns `False` |

### `tests/unit/sandbox/test_network.py`

| Test | What it verifies |
|------|------------------|
| Default hosts | Expected iptables rules generated |
| Custom hosts | Included in output |
| Proxy always allowed | `host.docker.internal` rule present regardless |
| Empty host list | Still allows DNS + loopback + proxy |

### `tests/unit/sandbox/test_factory_sandbox.py`

| Test | What it verifies |
|------|------------------|
| `mode=container` + `driver=api` | Returns `ContainerDriver` |
| `mode=container` + `driver=cli` | Raises `ValueError` |
| `mode=none` | Returns normal driver, existing behavior unchanged |

### Mock Pattern

`AsyncMock` implementing `SandboxProvider` with `exec_stream` returning `AsyncIterator[str]` of pre-built JSON lines. Same boundary-mocking philosophy as existing driver tests.

---

## Implementation Phases

| Phase | What | Files | Depends on |
|-------|------|-------|------------|
| 1 | Config threading: AgentConfig + get_agent_config + factory signature | `types.py`, `factory.py`, agents | — |
| 2 | ContainerDriver | `sandbox/driver.py` | Phase 1 |
| 3 | Network allowlist | `sandbox/network.py`, `scripts/setup-network.sh` | Independent |
| 4 | Server teardown | `server/main.py` | Independent |
| 5 | Tests | `tests/unit/sandbox/test_*.py` | Phase 1–4 |

Phases 1–2 are sequential. Phases 3 and 4 are independent of each other and can be done in parallel.
