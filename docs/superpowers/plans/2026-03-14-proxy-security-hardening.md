# Proxy Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 7 security issues in the sandbox proxy identified in issue #537.

**Architecture:** The sandbox proxy (`amelia/sandbox/proxy.py`) forwards container LLM requests to upstream providers, injecting API keys. Changes span the proxy router, Docker provider, worker, network rules, and server wiring. Each fix is independent and committed separately.

**Tech Stack:** Python 3.12+, FastAPI, httpx, Pydantic, pytest-asyncio, Docker

---

## Chunk 1: Proxy Hardening (Fixes 4, 5, 7)

These three fixes are localized to `amelia/sandbox/proxy.py` and its test file. No cross-file dependencies.

### Task 1: Redact profile name from 404 error (Fix 4)

**Files:**
- Modify: `amelia/sandbox/proxy.py:80-102` — `_resolve_provider_or_raise()`
- Modify: `tests/unit/sandbox/test_proxy.py:66-73` — `TestProxyProfileResolution`

- [ ] **Step 1: Write failing test — generic 404 detail**

In `tests/unit/sandbox/test_proxy.py`, update the existing test and add a new one:

```python
# Replace the existing test_unknown_profile_returns_404 (line 66-73)
def test_unknown_profile_returns_404(self, client: TestClient) -> None:
    response = client.post(
        "/proxy/v1/chat/completions",
        json={"model": "test", "messages": []},
        headers={"X-Amelia-Profile": "nonexistent"},
    )
    assert response.status_code == 404
    # Must NOT leak the profile name
    assert "nonexistent" not in response.json()["detail"]
    assert "unconfigured" in response.json()["detail"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/sandbox/test_proxy.py::TestProxyProfileResolution::test_unknown_profile_returns_404 -v`
Expected: FAIL — current detail contains "nonexistent"

- [ ] **Step 3: Update `_resolve_provider_or_raise()` to use generic message**

In `amelia/sandbox/proxy.py`, replace the detail string and add a debug log:

```python
async def _resolve_provider_or_raise(
    profile: str,
    resolve_provider: ProviderResolver,
) -> ProviderConfig:
    config = await resolve_provider(profile)
    if config is None:
        logger.debug("Unknown profile requested", profile=profile)
        raise HTTPException(
            status_code=404,
            detail="Unknown or unconfigured profile",
        )
    return config
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/sandbox/test_proxy.py::TestProxyProfileResolution -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add amelia/sandbox/proxy.py tests/unit/sandbox/test_proxy.py
git commit -m "fix(proxy): redact profile name from 404 error (#537)"
```

---

### Task 2: Sanitize upstream error messages (Fix 5)

**Files:**
- Modify: `amelia/sandbox/proxy.py:186-201` — exception handlers in `forward_request()`
- Test: `tests/unit/sandbox/test_proxy.py` — new `TestProxyErrorSanitization` class

- [ ] **Step 1: Write failing tests — error messages must be generic**

Add to `tests/unit/sandbox/test_proxy.py`:

```python
class TestProxyErrorSanitization:
    """Upstream errors must not leak internal details to the caller."""

    def test_connect_error_is_generic(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        async def mock_send(self: Any, request: httpx.Request, *, stream: bool = False, **kwargs: Any) -> httpx.Response:
            raise httpx.ConnectError("Connection refused: 10.0.0.5:443")

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={"X-Amelia-Profile": "work"},
        )
        assert response.status_code == 502
        detail = response.json()["detail"]
        assert "10.0.0.5" not in detail
        assert "Connection refused" not in detail

    def test_timeout_error_is_generic(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        async def mock_send(self: Any, request: httpx.Request, *, stream: bool = False, **kwargs: Any) -> httpx.Response:
            raise httpx.ReadTimeout("Read timed out on host api.openrouter.ai:443")

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={"X-Amelia-Profile": "work"},
        )
        assert response.status_code == 504
        detail = response.json()["detail"]
        assert "openrouter" not in detail

    def test_http_error_is_generic(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        async def mock_send(self: Any, request: httpx.Request, *, stream: bool = False, **kwargs: Any) -> httpx.Response:
            raise httpx.DecodingError("Invalid chunk encoding from 10.0.0.5")

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={"X-Amelia-Profile": "work"},
        )
        assert response.status_code == 502
        detail = response.json()["detail"]
        assert "10.0.0.5" not in detail
        assert "DecodingError" not in detail
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/sandbox/test_proxy.py::TestProxyErrorSanitization -v`
Expected: FAIL — current detail contains raw exception strings

- [ ] **Step 3: Replace exception handlers with generic messages**

In `amelia/sandbox/proxy.py`, update the three exception handlers inside `forward_request()`:

```python
except httpx.ConnectError as e:
    logger.warning("Upstream connect failed", error=str(e))
    raise HTTPException(
        status_code=502,
        detail="Upstream provider unavailable",
    ) from e
except httpx.TimeoutException as e:
    logger.warning("Upstream request timed out", error=str(e))
    raise HTTPException(
        status_code=504,
        detail="Upstream provider request timed out",
    ) from e
except httpx.HTTPError as e:
    logger.warning("Upstream request failed", error=str(e))
    raise HTTPException(
        status_code=502,
        detail="Upstream provider request failed",
    ) from e
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/sandbox/test_proxy.py::TestProxyErrorSanitization -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add amelia/sandbox/proxy.py tests/unit/sandbox/test_proxy.py
git commit -m "fix(proxy): sanitize upstream error messages (#537)"
```

---

### Task 3: Add request body size limit (Fix 7)

**Files:**
- Modify: `amelia/sandbox/proxy.py` — add constant + size checks in `forward_request()`
- Test: `tests/unit/sandbox/test_proxy.py` — new `TestProxyBodySizeLimit` class

- [ ] **Step 1: Write failing tests — oversized requests rejected with 413**

First, update the import at the top of `tests/unit/sandbox/test_proxy.py`:

```python
from amelia.sandbox.proxy import PROXY_MAX_BODY_BYTES, ProviderConfig, create_proxy_router
```

Then add the test class:

```python
class TestProxyBodySizeLimit:
    """Proxy must reject oversized request bodies."""

    def test_content_length_exceeding_limit_returns_413(
        self, client: TestClient,
    ) -> None:
        """Request with Content-Length > limit is rejected before reading body."""
        response = client.post(
            "/proxy/v1/chat/completions",
            content=b"x",
            headers={
                "X-Amelia-Profile": "work",
                "Content-Length": str(PROXY_MAX_BODY_BYTES + 1),
            },
        )
        assert response.status_code == 413

    def test_normal_request_passes_size_check(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Normal-sized request passes through."""
        async def mock_send(self: Any, request: httpx.Request, *, stream: bool = False, **kwargs: Any) -> httpx.Response:
            return _streaming_response(200, b'{"choices": []}', request)

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "hi"}]},
            headers={"X-Amelia-Profile": "work"},
        )
        assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/sandbox/test_proxy.py::TestProxyBodySizeLimit -v`
Expected: FAIL — `ImportError` because `PROXY_MAX_BODY_BYTES` does not exist yet

- [ ] **Step 3: Add constant and size checks**

In `amelia/sandbox/proxy.py`, add the constant after the existing timeout constants:

```python
PROXY_MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB
```

In `forward_request()`, add size checks before `body = await request.body()`:

```python
async def forward_request(
    request: Request,
    provider: ProviderConfig,
    path: str,
) -> Response:
    # Check content-length header for early rejection
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > PROXY_MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Request body too large")

    body = await request.body()
    if len(body) > PROXY_MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Request body too large")

    # ... rest of forward_request unchanged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/sandbox/test_proxy.py::TestProxyBodySizeLimit -v`
Expected: PASS

- [ ] **Step 5: Run all proxy tests to check for regressions**

Run: `uv run pytest tests/unit/sandbox/test_proxy.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add amelia/sandbox/proxy.py tests/unit/sandbox/test_proxy.py
git commit -m "fix(proxy): add 10MB request body size limit (#537)"
```

---

## Chunk 2: Network & Container Hardening (Fixes 2, 3, 6)

### Task 4: Default `network_allowlist_enabled` to `True` (Fix 2)

**Files:**
- Modify: `amelia/core/types.py:96` — change default
- Modify: `tests/unit/core/test_sandbox_config.py:26-28` — update assertion
- Modify: `tests/unit/core/test_sandbox_config.py:42-46,59-70` — add explicit `network_allowlist_enabled=False` to Daytona tests
- Modify: `tests/unit/sandbox/test_docker_provider.py:241-242` — update assertion
- Modify: `tests/unit/drivers/test_factory.py:180,187,355,365,373` — add explicit `network_allowlist_enabled=False` to Daytona tests
- Modify: `tests/integration/test_daytona_sandbox.py:210-213` — add explicit `network_allowlist_enabled=False`

**Context:** The `SandboxConfig._validate_daytona()` validator rejects `network_allowlist_enabled=True` for Daytona mode. Changing the default to `True` will break every Daytona `SandboxConfig` that doesn't explicitly set it to `False`. All such call sites must be updated.

- [ ] **Step 1: Update test to expect `True` as default**

In `tests/unit/core/test_sandbox_config.py`, update `test_network_allowlist_disabled_by_default`:

```python
def test_network_allowlist_enabled_by_default(self) -> None:
    config = SandboxConfig()
    assert config.network_allowlist_enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_sandbox_config.py::TestSandboxConfig::test_network_allowlist_enabled_by_default -v`
Expected: FAIL — current default is `False`

- [ ] **Step 3: Change default in `SandboxConfig`**

In `amelia/core/types.py`, change line 96:

```python
network_allowlist_enabled: bool = True
```

- [ ] **Step 4: Fix all Daytona test sites that now break**

Every `SandboxConfig(mode=SandboxMode.DAYTONA, ...)` that doesn't already pass `network_allowlist_enabled=False` must be updated. Add `network_allowlist_enabled=False` to each of these call sites:

**`tests/unit/core/test_sandbox_config.py`:**
- `test_daytona_mode` (line 42): add `network_allowlist_enabled=False`
- `test_sandbox_config_daytona_fields` (line 59): add `network_allowlist_enabled=False`

**`tests/unit/drivers/test_factory.py`** — all `SandboxConfig(mode=SandboxMode.DAYTONA, ...)` without explicit `network_allowlist_enabled=False`:
- `test_daytona_mode_returns_container_driver` (line 136): add `network_allowlist_enabled=False`
- `test_daytona_mode_missing_api_key_raises` (line 180): add `network_allowlist_enabled=False`
- `test_daytona_mode_rejects_cli_wrappers` (line 187): add `network_allowlist_enabled=False`
- `test_daytona_mode_passes_image` (line 205): add `network_allowlist_enabled=False`
- `test_daytona_mode_passes_github_token` (line 236): add `network_allowlist_enabled=False`
- `test_daytona_mode_missing_llm_api_key_raises` (line 249): add `network_allowlist_enabled=False`
- `test_daytona_mode_custom_provider_resolves` (line 261): add `network_allowlist_enabled=False`
- `test_daytona_mode_unsupported_provider_raises` (line 287): add `network_allowlist_enabled=False`
- `test_creates_provider_with_required_fields` (line 355): add `network_allowlist_enabled=False`
- `test_raises_without_api_key` (line 365): add `network_allowlist_enabled=False`
- `test_raises_without_repo_url` (line 373): add `network_allowlist_enabled=False`

**`tests/integration/test_daytona_sandbox.py`:**
- `test_factory_creates_daytona_stack` (line 210): add `network_allowlist_enabled=False`

- [ ] **Step 5: Fix Docker provider test assertion**

In `tests/unit/sandbox/test_docker_provider.py`, the test `test_allowlist_skipped_when_disabled` (line 237-247) creates a `DockerSandboxProvider` with default `network_allowlist_enabled` and asserts it's `False`. Update to explicitly pass `False`:

```python
async def test_allowlist_skipped_when_disabled(
    self, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When network_allowlist_enabled=False, no docker exec is invoked."""
    provider = DockerSandboxProvider(
        profile_name="test", network_allowlist_enabled=False,
    )
    assert provider.network_allowlist_enabled is False

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        await provider._apply_network_allowlist()

    mock_exec.assert_not_called()
```

- [ ] **Step 6: Run all affected test files**

Run: `uv run pytest tests/unit/core/test_sandbox_config.py tests/unit/sandbox/test_docker_provider.py tests/unit/drivers/test_factory.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add amelia/core/types.py tests/unit/core/test_sandbox_config.py tests/unit/sandbox/test_docker_provider.py tests/unit/drivers/test_factory.py tests/integration/test_daytona_sandbox.py
git commit -m "fix(sandbox): default network_allowlist_enabled to True (#537)"
```

---

### Task 5: Restrict DNS to Docker's internal resolver (Fix 3)

**Files:**
- Modify: `amelia/sandbox/network.py:10-72` — `generate_allowlist_rules()`
- Modify: `tests/unit/sandbox/test_network.py` — update/add DNS assertions

- [ ] **Step 1: Write failing test — DNS rules must target `127.0.0.11`**

In `tests/unit/sandbox/test_network.py`, add a new test and update the existing one:

```python
def test_dns_restricted_to_docker_resolver(self) -> None:
    """DNS rules must only allow Docker's internal resolver, not any destination."""
    from amelia.sandbox.network import generate_allowlist_rules

    rules = generate_allowlist_rules(allowed_hosts=[])

    # Must target Docker's internal DNS
    assert "-d 127.0.0.11" in rules
    # Must NOT have open DNS rules (no -d restriction)
    for line in rules.strip().split("\n"):
        if "--dport 53" in line and "iptables" in line:
            assert "-d " in line, f"DNS rule missing destination restriction: {line}"

def test_custom_dns_server(self) -> None:
    """Should use custom DNS server when specified."""
    from amelia.sandbox.network import generate_allowlist_rules

    rules = generate_allowlist_rules(allowed_hosts=[], dns_server="8.8.8.8")
    assert "-d 8.8.8.8" in rules
    assert "127.0.0.11" not in rules
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/sandbox/test_network.py::TestGenerateAllowlistRules::test_dns_restricted_to_docker_resolver -v`
Expected: FAIL — current rules don't have `-d` restriction on DNS

- [ ] **Step 3: Add `dns_server` parameter and restrict DNS rules**

In `amelia/sandbox/network.py`, update `generate_allowlist_rules()`:

```python
def generate_allowlist_rules(
    allowed_hosts: list[str],
    proxy_host: str = "host.docker.internal",
    dns_server: str = "127.0.0.11",
) -> str:
```

Replace the DNS rule lines:

```python
# Before:
"# Allow DNS (UDP + TCP)",
"iptables -A OUTPUT -p udp --dport 53 -j ACCEPT",
"iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT",

# After:
f"# Allow DNS via Docker resolver ({dns_server})",
f"iptables -A OUTPUT -d {dns_server} -p udp --dport 53 -j ACCEPT",
f"iptables -A OUTPUT -d {dns_server} -p tcp --dport 53 -j ACCEPT",
```

- [ ] **Step 4: Run all network tests**

Run: `uv run pytest tests/unit/sandbox/test_network.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add amelia/sandbox/network.py tests/unit/sandbox/test_network.py
git commit -m "fix(network): restrict DNS to Docker internal resolver (#537)"
```

---

### Task 6: Conditional `NET_ADMIN`/`NET_RAW` capabilities (Fix 6)

**Files:**
- Modify: `amelia/sandbox/docker.py:226-273` — `_start_container()`
- Modify: `tests/unit/sandbox/test_docker_provider.py` — new `TestContainerCapabilities` class

- [ ] **Step 1: Write failing tests — capabilities conditional on allowlist**

Add to `tests/unit/sandbox/test_docker_provider.py`:

```python
class TestContainerCapabilities:
    """NET_ADMIN/NET_RAW should only be added when allowlist is enabled."""

    async def test_capabilities_present_when_allowlist_enabled(self) -> None:
        provider = DockerSandboxProvider(
            profile_name="test", network_allowlist_enabled=True,
        )
        mock_restart = AsyncMock()
        mock_restart.returncode = 1  # No existing container to restart
        mock_restart.wait = AsyncMock()

        mock_run = AsyncMock()
        mock_run.communicate.return_value = (b"container-id", b"")
        mock_run.returncode = 0

        with patch("asyncio.create_subprocess_exec", side_effect=[mock_restart, mock_run]) as mock_exec:
            await provider._start_container()

        run_args = mock_exec.call_args_list[1][0]
        assert "--cap-add" in run_args
        assert "NET_ADMIN" in run_args
        assert "NET_RAW" in run_args

    async def test_no_capabilities_when_allowlist_disabled(self) -> None:
        provider = DockerSandboxProvider(
            profile_name="test", network_allowlist_enabled=False,
        )
        mock_restart = AsyncMock()
        mock_restart.returncode = 1
        mock_restart.wait = AsyncMock()

        mock_run = AsyncMock()
        mock_run.communicate.return_value = (b"container-id", b"")
        mock_run.returncode = 0

        with patch("asyncio.create_subprocess_exec", side_effect=[mock_restart, mock_run]) as mock_exec:
            await provider._start_container()

        run_args = mock_exec.call_args_list[1][0]
        assert "--cap-add" not in run_args
        assert "NET_ADMIN" not in run_args
        assert "NET_RAW" not in run_args
```

- [ ] **Step 2: Run tests to verify the "disabled" test fails**

Run: `uv run pytest tests/unit/sandbox/test_docker_provider.py::TestContainerCapabilities -v`
Expected: `test_no_capabilities_when_allowlist_disabled` FAILS — capabilities are always added

- [ ] **Step 3: Make capabilities conditional in `_start_container()`**

In `amelia/sandbox/docker.py`, refactor the `cmd` list in `_start_container()`. Remove the old comment about NET_ADMIN/NET_RAW being always required (lines 251-252) since capabilities are now conditional:

```python
cmd = [
    "docker", "run", "-d",
    "--name", self.container_name,
    "--add-host=host.docker.internal:host-gateway",
]
if self.network_allowlist_enabled:
    # NET_ADMIN + NET_RAW required for iptables-based network allowlist
    cmd.extend(["--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW"])
cmd.extend([
    "-e", f"LLM_PROXY_URL=http://host.docker.internal:{self.proxy_port}/proxy/v1",
    "-e", f"AMELIA_PROFILE={self.profile_name}",
    self.image,
    "sleep", "infinity",
])
```

- [ ] **Step 4: Run all docker provider tests**

Run: `uv run pytest tests/unit/sandbox/test_docker_provider.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add amelia/sandbox/docker.py tests/unit/sandbox/test_docker_provider.py
git commit -m "fix(docker): only add NET_ADMIN/NET_RAW when allowlist enabled (#537)"
```

---

## Chunk 3: Per-Container Proxy Authentication (Fix 1)

This is the largest fix. It touches 5 files and introduces a new auth mechanism.

### Task 7: Add `token_validator` to proxy router

**Files:**
- Modify: `amelia/sandbox/proxy.py` — add `token_validator` param, extract+validate token
- Modify: `tests/unit/sandbox/test_proxy.py` — token validation tests + update fixture

- [ ] **Step 1: Write failing tests — token validation**

Add to `tests/unit/sandbox/test_proxy.py`:

```python
class TestProxyTokenAuth:
    """Per-container proxy token authentication."""

    @pytest.fixture
    async def authed_app(self) -> AsyncIterator[FastAPI]:
        """App with token validation enabled."""
        app = FastAPI()

        async def _resolve_provider(profile_name: str) -> ProviderConfig | None:
            if profile_name == "work":
                return ProviderConfig(
                    base_url="https://openrouter.ai/api/v1",
                    api_key="sk-or-test-key",
                )
            return None

        async def _validate_token(token: str) -> bool:
            return token == "valid-secret-token"

        proxy = create_proxy_router(
            resolve_provider=_resolve_provider,
            token_validator=_validate_token,
        )
        app.include_router(proxy.router, prefix="/proxy/v1")
        yield app
        await proxy.cleanup()

    @pytest.fixture
    def authed_client(self, authed_app: FastAPI) -> TestClient:
        return TestClient(authed_app)

    def test_missing_token_returns_401(self, authed_client: TestClient) -> None:
        response = authed_client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={"X-Amelia-Profile": "work"},
        )
        assert response.status_code == 401

    def test_wrong_token_returns_401(self, authed_client: TestClient) -> None:
        response = authed_client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={
                "X-Amelia-Profile": "work",
                "X-Amelia-Proxy-Token": "wrong-token",
            },
        )
        assert response.status_code == 401

    def test_valid_token_passes_through(
        self, authed_client: TestClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def mock_send(self: Any, request: httpx.Request, *, stream: bool = False, **kwargs: Any) -> httpx.Response:
            return _streaming_response(200, b'{"choices": []}', request)

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

        response = authed_client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={
                "X-Amelia-Profile": "work",
                "X-Amelia-Proxy-Token": "valid-secret-token",
            },
        )
        assert response.status_code == 200

    def test_token_not_forwarded_upstream(
        self, authed_client: TestClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Proxy token must be stripped before forwarding."""
        captured_headers: dict[str, str] = {}

        async def mock_send(self: Any, request: httpx.Request, *, stream: bool = False, **kwargs: Any) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return _streaming_response(200, b'{"choices": []}', request)

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

        authed_client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={
                "X-Amelia-Profile": "work",
                "X-Amelia-Proxy-Token": "valid-secret-token",
            },
        )
        assert "x-amelia-proxy-token" not in captured_headers

    def test_no_validator_skips_token_check(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        """When no token_validator is set, requests pass without a token."""
        async def mock_send(self: Any, request: httpx.Request, *, stream: bool = False, **kwargs: Any) -> httpx.Response:
            return _streaming_response(200, b'{"choices": []}', request)

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={"X-Amelia-Profile": "work"},
        )
        assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/sandbox/test_proxy.py::TestProxyTokenAuth -v`
Expected: FAIL — `create_proxy_router` does not accept `token_validator`

- [ ] **Step 3: Implement token validation in proxy**

In `amelia/sandbox/proxy.py`:

1. Add a type alias after `ProviderResolver`:

```python
type TokenValidator = Callable[[str], Coroutine[Any, Any, bool]]
```

2. Update `create_proxy_router()` signature:

```python
def create_proxy_router(
    resolve_provider: ProviderResolver,
    token_validator: TokenValidator | None = None,
) -> ProxyRouter:
```

3. Add a helper function inside `create_proxy_router()`, before `forward_request()`:

```python
async def _validate_proxy_token(request: Request) -> None:
    """Validate the X-Amelia-Proxy-Token header if a validator is configured."""
    if token_validator is None:
        return
    token = request.headers.get("X-Amelia-Proxy-Token")
    if not token or not await token_validator(token):
        raise HTTPException(status_code=401, detail="Invalid or missing proxy token")
```

4. Call `_validate_proxy_token(request)` at the start of each endpoint handler (`proxy_chat_completions`, `proxy_embeddings`, `proxy_git_credentials`), before `_get_profile_header()`.

5. Add `"x-amelia-proxy-token"` to the hop-by-hop header strip list in `forward_request()`:

```python
for h in (
    "host",
    "x-amelia-profile",
    "x-amelia-proxy-token",
    "content-length",
    "connection",
    "keep-alive",
    "transfer-encoding",
):
    headers.pop(h, None)
```

- [ ] **Step 4: Run token auth tests**

Run: `uv run pytest tests/unit/sandbox/test_proxy.py::TestProxyTokenAuth -v`
Expected: PASS

- [ ] **Step 5: Run all proxy tests for regressions**

Run: `uv run pytest tests/unit/sandbox/test_proxy.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add amelia/sandbox/proxy.py tests/unit/sandbox/test_proxy.py
git commit -m "feat(proxy): add per-container token authentication (#537)"
```

---

### Task 8: Generate token in Docker provider

**Files:**
- Modify: `amelia/sandbox/docker.py` — generate token, pass as env var, expose property
- Modify: `tests/unit/sandbox/test_docker_provider.py` — verify token generation

- [ ] **Step 1: Write failing tests — token generation**

Add to `tests/unit/sandbox/test_docker_provider.py`:

```python
class TestProxyTokenGeneration:
    """Docker provider generates a unique proxy token per container."""

    def test_proxy_token_generated_on_init(self) -> None:
        provider = DockerSandboxProvider(profile_name="test")
        assert provider.proxy_token is not None
        assert len(provider.proxy_token) > 20  # secrets.token_urlsafe(32) is 43 chars

    def test_proxy_token_unique_per_instance(self) -> None:
        p1 = DockerSandboxProvider(profile_name="test")
        p2 = DockerSandboxProvider(profile_name="test")
        assert p1.proxy_token != p2.proxy_token

    async def test_token_passed_as_env_var(self) -> None:
        provider = DockerSandboxProvider(
            profile_name="test", network_allowlist_enabled=False,
        )
        mock_restart = AsyncMock()
        mock_restart.returncode = 1
        mock_restart.wait = AsyncMock()

        mock_run = AsyncMock()
        mock_run.communicate.return_value = (b"container-id", b"")
        mock_run.returncode = 0

        with patch("asyncio.create_subprocess_exec", side_effect=[mock_restart, mock_run]) as mock_exec:
            await provider._start_container()

        run_args = mock_exec.call_args_list[1][0]
        # Find the AMELIA_PROXY_TOKEN env var
        env_pairs = list(zip(run_args, run_args[1:]))
        token_envs = [v for k, v in env_pairs if k == "-e" and v.startswith("AMELIA_PROXY_TOKEN=")]
        assert len(token_envs) == 1
        assert token_envs[0] == f"AMELIA_PROXY_TOKEN={provider.proxy_token}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/sandbox/test_docker_provider.py::TestProxyTokenGeneration -v`
Expected: FAIL — `proxy_token` attribute does not exist

- [ ] **Step 3: Generate token in `__init__` and pass in `_start_container()`**

In `amelia/sandbox/docker.py`:

1. Add import at top:

```python
import secrets
```

2. In `__init__()`, add after `self.container_name`:

```python
self.proxy_token = secrets.token_urlsafe(32)
```

3. In `_start_container()`, add `-e AMELIA_PROXY_TOKEN=...` to the `cmd` list, after the `AMELIA_PROFILE` env var:

```python
cmd.extend([
    "-e", f"LLM_PROXY_URL=http://host.docker.internal:{self.proxy_port}/proxy/v1",
    "-e", f"AMELIA_PROFILE={self.profile_name}",
    "-e", f"AMELIA_PROXY_TOKEN={self.proxy_token}",
    self.image,
    "sleep", "infinity",
])
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/sandbox/test_docker_provider.py::TestProxyTokenGeneration -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add amelia/sandbox/docker.py tests/unit/sandbox/test_docker_provider.py
git commit -m "feat(docker): generate per-container proxy auth token (#537)"
```

---

### Task 9: Send token from worker

**Files:**
- Modify: `amelia/sandbox/worker.py:196-234` — `_create_worker_chat_model()`
- Test: `tests/unit/sandbox/test_worker.py` — new test for token header injection

- [ ] **Step 1: Write failing test — worker sends proxy token**

Create or add to `tests/unit/sandbox/test_worker.py`:

```python
"""Tests for worker chat model creation."""

from unittest.mock import MagicMock, patch

import pytest


class TestCreateWorkerChatModel:
    """Tests for _create_worker_chat_model()."""

    def test_proxy_token_added_to_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When AMELIA_PROXY_TOKEN is set, it should be included in default_headers."""
        monkeypatch.setenv("AMELIA_PROXY_TOKEN", "test-secret-token")
        monkeypatch.setenv("AMELIA_PROFILE", "work")

        mock_init = MagicMock(return_value="mock-model")
        with patch("amelia.sandbox.worker.init_chat_model", mock_init, create=True):
            from amelia.sandbox.worker import _create_worker_chat_model
            _create_worker_chat_model(model="test-model", base_url="http://localhost:8430/proxy/v1")

        call_kwargs = mock_init.call_args[1]
        assert call_kwargs["default_headers"]["X-Amelia-Proxy-Token"] == "test-secret-token"

    def test_no_proxy_token_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When AMELIA_PROXY_TOKEN is not set, header should not be present."""
        monkeypatch.delenv("AMELIA_PROXY_TOKEN", raising=False)
        monkeypatch.setenv("AMELIA_PROFILE", "work")

        mock_init = MagicMock(return_value="mock-model")
        with patch("amelia.sandbox.worker.init_chat_model", mock_init, create=True):
            from amelia.sandbox.worker import _create_worker_chat_model
            _create_worker_chat_model(model="test-model", base_url="http://localhost:8430/proxy/v1")

        call_kwargs = mock_init.call_args[1]
        assert "X-Amelia-Proxy-Token" not in call_kwargs["default_headers"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/sandbox/test_worker.py::TestCreateWorkerChatModel::test_proxy_token_added_to_headers -v`
Expected: FAIL — worker does not read `AMELIA_PROXY_TOKEN`

- [ ] **Step 3: Update `_create_worker_chat_model()` to send token**

In `amelia/sandbox/worker.py`, add token reading after the profile header setup (after `headers["X-Amelia-Profile"] = profile`, around line 217):

```python
proxy_token = os.environ.get("AMELIA_PROXY_TOKEN", "")
if proxy_token:
    headers["X-Amelia-Proxy-Token"] = proxy_token
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/sandbox/test_worker.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add amelia/sandbox/worker.py tests/unit/sandbox/test_worker.py
git commit -m "feat(worker): send proxy auth token in requests (#537)"
```

---

### Task 10: Wire up token store in server

**Files:**
- Modify: `amelia/server/main.py` — add token registry, pass validator to `create_proxy_router()`

This task wires the Docker provider's `proxy_token` to the proxy's `token_validator`. The server maintains an in-memory dict mapping tokens to container names.

**Important:** The `token_validator` is optional (`None` = no auth). We wire it here so the infrastructure is in place, but the validator only rejects when tokens are registered. An empty registry means all tokens are rejected — which is correct because no containers have been provisioned yet. The sandbox provisioning code (which creates `DockerSandboxProvider` instances) must register each provider's `proxy_token` in this dict when starting a container. That registration wiring is out of scope for this PR since it depends on runtime profile loading; tokens will simply not be validated until that's done.

- [ ] **Step 1: Update `create_app()` to pass token validator**

In `amelia/server/main.py`, after the `_resolve_provider` closure and before the `proxy = create_proxy_router(...)` line:

```python
# Token registry: maps proxy tokens to container names.
# Populated when sandbox providers are created via DockerSandboxProvider.
# Registration of tokens happens during sandbox provisioning (not in this PR).
proxy_tokens: dict[str, str] = {}
application.state.proxy_tokens = proxy_tokens

async def _validate_proxy_token(token: str) -> bool:
    return token in proxy_tokens

proxy = create_proxy_router(
    resolve_provider=_resolve_provider,
    token_validator=_validate_proxy_token,
)
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add amelia/server/main.py
git commit -m "feat(server): wire proxy token validator with token registry (#537)"
```

---

## Chunk 4: Final Verification

### Task 11: Full test suite + lint + type check

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS

- [ ] **Step 2: Run linter**

Run: `uv run ruff check amelia tests`
Expected: No errors

- [ ] **Step 3: Run type checker**

Run: `uv run mypy amelia`
Expected: No errors

- [ ] **Step 4: Fix any issues found, commit**

If any issues are found, fix and commit with:
```bash
git commit -m "fix: address lint/type issues from security hardening (#537)"
```
