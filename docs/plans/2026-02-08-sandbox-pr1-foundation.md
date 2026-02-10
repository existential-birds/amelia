# Sandbox PR1 — Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish the sandbox foundation: `SandboxProvider` protocol, `SandboxConfig` model on profiles, and the LLM + git credential proxy mounted on the existing FastAPI server.

**Architecture:** Three independent modules (`provider.py`, `proxy.py`, and config additions) that form the prerequisite layer for the container + worker (PR2) and driver integration (PR3). The proxy is a thin reverse proxy on the existing FastAPI server that attaches API keys based on profile. The provider protocol defines the sandbox lifecycle abstraction.

**Tech Stack:** Python 3.12+, Pydantic v2, FastAPI, httpx (async HTTP client for proxy forwarding)

**Design doc:** `docs/plans/2026-02-08-devcontainer-sandbox-design.md` — PR 1 section (lines 138–313)

---

### Task 1: Create `SandboxConfig` model and add it to `Profile`

**Files:**
- Modify: `amelia/core/types.py`
- Test: `tests/unit/core/test_sandbox_config.py`

**Step 1: Write the failing tests**

```python
# tests/unit/core/test_sandbox_config.py
"""Tests for SandboxConfig model and Profile integration."""

from amelia.core.types import Profile, SandboxConfig


class TestSandboxConfig:
    def test_default_mode_is_none(self):
        config = SandboxConfig()
        assert config.mode == "none"

    def test_container_mode(self):
        config = SandboxConfig(mode="container")
        assert config.mode == "container"

    def test_invalid_mode_rejected(self):
        import pytest

        with pytest.raises(Exception):
            SandboxConfig(mode="invalid")

    def test_default_image(self):
        config = SandboxConfig()
        assert config.image == "amelia-sandbox:latest"

    def test_network_allowlist_disabled_by_default(self):
        config = SandboxConfig()
        assert config.network_allowlist_enabled is False

    def test_default_allowed_hosts(self):
        config = SandboxConfig()
        assert "api.anthropic.com" in config.network_allowed_hosts
        assert "github.com" in config.network_allowed_hosts

    def test_custom_allowed_hosts(self):
        config = SandboxConfig(network_allowed_hosts=["example.com"])
        assert config.network_allowed_hosts == ["example.com"]


class TestProfileSandboxConfig:
    def test_profile_sandbox_defaults_to_none_mode(self):
        profile = Profile(name="test", working_dir="/tmp")
        assert profile.sandbox.mode == "none"

    def test_profile_with_container_sandbox(self):
        sandbox = SandboxConfig(mode="container")
        profile = Profile(name="test", working_dir="/tmp", sandbox=sandbox)
        assert profile.sandbox.mode == "container"

    def test_profile_sandbox_is_frozen(self):
        import pytest

        profile = Profile(name="test", working_dir="/tmp")
        with pytest.raises(Exception):
            profile.sandbox = SandboxConfig(mode="container")
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_sandbox_config.py -v`
Expected: FAIL — `SandboxConfig` does not exist yet

**Step 3: Implement `SandboxConfig` and add `sandbox` field to `Profile`**

Add to `amelia/core/types.py` (before the `Profile` class):

```python
class SandboxConfig(BaseModel):
    """Sandbox execution configuration for a profile.

    Attributes:
        mode: Sandbox mode ('none' = direct execution, 'container' = Docker sandbox).
        image: Docker image for sandbox container.
        network_allowlist_enabled: Whether to restrict outbound network.
        network_allowed_hosts: Hosts allowed when network allowlist is enabled.
    """

    model_config = ConfigDict(frozen=True)

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

Add `Literal` to the `typing` import at the top of the file. Add to `Profile`:

```python
sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/test_sandbox_config.py -v`
Expected: PASS

**Step 5: Run existing tests to verify nothing broke**

Run: `uv run pytest tests/unit/core/ -v`
Expected: PASS — `SandboxConfig` defaults to `mode="none"` so all existing profiles are unaffected

**Step 6: Lint and type check**

Run: `uv run ruff check amelia/core/types.py && uv run mypy amelia/core/types.py`
Expected: PASS

**Step 7: Commit**

```bash
git add amelia/core/types.py tests/unit/core/test_sandbox_config.py
git commit -m "feat(sandbox): add SandboxConfig model and Profile.sandbox field"
```

---

### Task 2: Create `SandboxProvider` protocol

**Files:**
- Create: `amelia/sandbox/__init__.py`
- Create: `amelia/sandbox/provider.py`
- Test: `tests/unit/sandbox/test_provider.py`

**Step 1: Write the failing tests**

```python
# tests/unit/sandbox/__init__.py
```

```python
# tests/unit/sandbox/test_provider.py
"""Tests for SandboxProvider protocol compliance."""

from collections.abc import AsyncIterator

from amelia.sandbox.provider import SandboxProvider


class FakeSandboxProvider:
    """Minimal implementation to verify protocol shape."""

    async def ensure_running(self) -> None:
        pass

    async def exec_stream(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> AsyncIterator[str]:
        yield "line1"

    async def teardown(self) -> None:
        pass

    async def health_check(self) -> bool:
        return True


def test_fake_provider_satisfies_protocol():
    provider = FakeSandboxProvider()
    assert isinstance(provider, SandboxProvider)


async def test_exec_stream_yields_lines():
    provider = FakeSandboxProvider()
    lines = []
    async for line in provider.exec_stream(["echo", "hi"]):
        lines.append(line)
    assert lines == ["line1"]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/sandbox/test_provider.py -v`
Expected: FAIL — `amelia.sandbox` does not exist

**Step 3: Create the sandbox package and provider protocol**

```python
# amelia/sandbox/__init__.py
"""Sandbox execution infrastructure for isolated agent environments."""

from amelia.sandbox.provider import SandboxProvider

__all__ = ["SandboxProvider"]
```

```python
# amelia/sandbox/provider.py
"""SandboxProvider protocol — transport-agnostic sandbox lifecycle interface."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class SandboxProvider(Protocol):
    """Manages sandbox lifecycle and command execution.

    Transport-agnostic interface that enables Docker (MVP), Daytona,
    Fly.io, or SSH-based sandbox implementations.
    """

    async def ensure_running(self) -> None:
        """Ensure the sandbox is ready. Start if not running, no-op if already up."""
        ...

    async def exec_stream(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> AsyncIterator[str]:
        """Execute command in sandbox, streaming stdout lines.

        Args:
            command: Command and arguments to execute.
            cwd: Working directory inside the sandbox.
            env: Additional environment variables.
            stdin: Optional bytes to pipe to stdin.

        Yields:
            Lines of stdout output.
        """
        ...

    async def teardown(self) -> None:
        """Stop and clean up the sandbox."""
        ...

    async def health_check(self) -> bool:
        """Check if the sandbox is responsive.

        Returns:
            True if sandbox is running and healthy.
        """
        ...
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/sandbox/test_provider.py -v`
Expected: PASS

**Step 5: Lint and type check**

Run: `uv run ruff check amelia/sandbox/ && uv run mypy amelia/sandbox/`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/sandbox/__init__.py amelia/sandbox/provider.py tests/unit/sandbox/__init__.py tests/unit/sandbox/test_provider.py
git commit -m "feat(sandbox): add SandboxProvider protocol"
```

---

### Task 3: Add `base_url` parameter to `_create_chat_model()`

**Files:**
- Modify: `amelia/drivers/api/deepagents.py`
- Test: `tests/unit/test_api_driver.py` (add to existing tests)

This is a prerequisite for proxy routing — the worker needs to override the OpenRouter base URL to point at the host proxy.

**Step 1: Write the failing test**

Add to `tests/unit/test_api_driver.py` (or create `tests/unit/drivers/test_create_chat_model.py` if cleaner):

```python
# tests/unit/drivers/test_create_chat_model.py
"""Tests for _create_chat_model base_url parameter."""

from unittest.mock import patch

from amelia.drivers.api.deepagents import _create_chat_model


class TestCreateChatModelBaseUrl:
    @patch("amelia.drivers.api.deepagents.init_chat_model")
    def test_openrouter_uses_default_base_url(self, mock_init, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        _create_chat_model("test-model", provider="openrouter")
        _, kwargs = mock_init.call_args
        assert kwargs["base_url"] == "https://openrouter.ai/api/v1"

    @patch("amelia.drivers.api.deepagents.init_chat_model")
    def test_openrouter_accepts_custom_base_url(self, mock_init, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        _create_chat_model(
            "test-model",
            provider="openrouter",
            base_url="http://host.docker.internal:8430/proxy/v1",
        )
        _, kwargs = mock_init.call_args
        assert kwargs["base_url"] == "http://host.docker.internal:8430/proxy/v1"

    @patch("amelia.drivers.api.deepagents.init_chat_model")
    def test_non_openrouter_ignores_base_url(self, mock_init):
        _create_chat_model("gpt-4")
        mock_init.assert_called_once_with("gpt-4")
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/drivers/test_create_chat_model.py -v`
Expected: FAIL — `_create_chat_model` doesn't accept `base_url` parameter

**Step 3: Add `base_url` parameter**

Modify `_create_chat_model` in `amelia/drivers/api/deepagents.py`:

```python
def _create_chat_model(
    model: str,
    provider: str | None = None,
    base_url: str | None = None,
) -> BaseChatModel:
```

In the `provider == "openrouter"` branch, change the hardcoded URL:

```python
    if provider == "openrouter":
        # ... existing validation ...
        resolved_url = base_url or "https://openrouter.ai/api/v1"

        return init_chat_model(
            model=model,
            model_provider="openai",
            base_url=resolved_url,
            api_key=api_key,
            default_headers={
                "HTTP-Referer": site_url,
                "X-Title": site_name,
            },
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/drivers/test_create_chat_model.py -v`
Expected: PASS

**Step 5: Run existing API driver tests to verify no regression**

Run: `uv run pytest tests/unit/test_api_driver.py -v`
Expected: PASS — existing callers don't pass `base_url`, so default behavior is unchanged

**Step 6: Lint and type check**

Run: `uv run ruff check amelia/drivers/api/deepagents.py && uv run mypy amelia/drivers/api/deepagents.py`
Expected: PASS

**Step 7: Commit**

```bash
git add amelia/drivers/api/deepagents.py tests/unit/drivers/test_create_chat_model.py
git commit -m "feat(drivers): add base_url parameter to _create_chat_model for proxy routing"
```

---

### Task 4: Create ProviderConfig and the proxy router

**Files:**
- Create: `amelia/sandbox/proxy.py`
- Test: `tests/unit/sandbox/test_proxy.py`

The proxy is a FastAPI router that forwards LLM requests from the container to the upstream provider, attaching API keys. It also serves git credentials.

**Step 1: Write the failing tests**

```python
# tests/unit/sandbox/test_proxy.py
"""Tests for the LLM + git credential proxy router."""

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.sandbox.proxy import ProviderConfig, create_proxy_router


@pytest.fixture()
def proxy_app(monkeypatch):
    """Create a test app with the proxy router mounted."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

    app = FastAPI()

    async def _resolve_provider(profile_name: str) -> ProviderConfig | None:
        """Test resolver that maps profile names to provider configs."""
        providers = {
            "work": ProviderConfig(
                base_url="https://openrouter.ai/api/v1",
                api_key="sk-or-test-key",
            ),
            "personal": ProviderConfig(
                base_url="https://api.anthropic.com/v1",
                api_key="sk-ant-test-key",
            ),
        }
        return providers.get(profile_name)

    router = create_proxy_router(resolve_provider=_resolve_provider)
    app.include_router(router, prefix="/proxy/v1")
    return app


@pytest.fixture()
def client(proxy_app):
    return TestClient(proxy_app)


class TestProviderConfig:
    def test_provider_config_fields(self):
        config = ProviderConfig(
            base_url="https://openrouter.ai/api/v1",
            api_key="sk-test",
        )
        assert config.base_url == "https://openrouter.ai/api/v1"
        assert config.api_key == "sk-test"


class TestProxyProfileResolution:
    def test_missing_profile_header_returns_400(self, client):
        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
        )
        assert response.status_code == 400
        assert "X-Amelia-Profile" in response.json()["detail"]

    def test_unknown_profile_returns_404(self, client):
        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={"X-Amelia-Profile": "nonexistent"},
        )
        assert response.status_code == 404
        assert "nonexistent" in response.json()["detail"]


class TestProxyGitCredentials:
    def test_git_credentials_endpoint_exists(self, client):
        response = client.post(
            "/proxy/v1/git/credentials",
            content="host=github.com\nprotocol=https\n",
            headers={"X-Amelia-Profile": "work"},
        )
        # Should not 404 — route exists. Actual credential fetching is tested
        # in integration tests since it depends on host git config.
        assert response.status_code in (200, 501)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/sandbox/test_proxy.py -v`
Expected: FAIL — `amelia.sandbox.proxy` does not exist

**Step 3: Implement the proxy router**

```python
# amelia/sandbox/proxy.py
"""LLM + git credential proxy for sandboxed containers.

The proxy attaches API keys to requests from the container so that
keys never enter the sandbox environment. Profile-aware: reads the
X-Amelia-Profile header to resolve which upstream provider to use.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel


class ProviderConfig(BaseModel):
    """Resolved provider configuration for proxy forwarding.

    Attributes:
        base_url: Upstream LLM API base URL.
        api_key: API key to attach to forwarded requests.
    """

    base_url: str
    api_key: str


# Type alias for the provider resolver function
ProviderResolver = Callable[[str], Coroutine[Any, Any, ProviderConfig | None]]


def _get_profile_header(request: Request) -> str:
    """Extract and validate the X-Amelia-Profile header.

    Args:
        request: Incoming HTTP request.

    Returns:
        Profile name from the header.

    Raises:
        HTTPException: If header is missing.
    """
    profile = request.headers.get("X-Amelia-Profile")
    if not profile:
        raise HTTPException(
            status_code=400,
            detail="X-Amelia-Profile header is required",
        )
    return profile


async def _resolve_provider_or_raise(
    profile: str,
    resolve_provider: ProviderResolver,
) -> ProviderConfig:
    """Resolve provider config or raise 404.

    Args:
        profile: Profile name to resolve.
        resolve_provider: Async function that maps profile name to config.

    Returns:
        Resolved ProviderConfig.

    Raises:
        HTTPException: If profile has no provider configuration.
    """
    config = await resolve_provider(profile)
    if config is None:
        raise HTTPException(
            status_code=404,
            detail=f"No provider configuration for profile '{profile}'",
        )
    return config


def create_proxy_router(
    resolve_provider: ProviderResolver,
) -> APIRouter:
    """Create the proxy router with injected provider resolver.

    Args:
        resolve_provider: Async callable that maps a profile name to
            a ProviderConfig (base_url + api_key). Returns None if
            profile is unknown.

    Returns:
        Configured APIRouter with proxy routes.
    """
    router = APIRouter()

    @router.api_route(
        "/chat/completions",
        methods=["POST"],
    )
    async def proxy_chat_completions(request: Request) -> Response:
        """Forward chat completion requests to the upstream LLM provider."""
        profile = _get_profile_header(request)
        provider = await _resolve_provider_or_raise(profile, resolve_provider)
        return await _forward_request(request, provider, "/chat/completions")

    @router.api_route(
        "/embeddings",
        methods=["POST"],
    )
    async def proxy_embeddings(request: Request) -> Response:
        """Forward embedding requests to the upstream LLM provider."""
        profile = _get_profile_header(request)
        provider = await _resolve_provider_or_raise(profile, resolve_provider)
        return await _forward_request(request, provider, "/embeddings")

    @router.post("/git/credentials")
    async def proxy_git_credentials(request: Request) -> Response:
        """Return git credentials from the host's credential store.

        MVP: returns 501 Not Implemented. Full implementation in PR 2
        when the container actually needs git access.
        """
        _get_profile_header(request)
        return Response(
            status_code=501,
            content="Git credential proxy not yet implemented",
        )

    return router


async def _forward_request(
    request: Request,
    provider: ProviderConfig,
    path: str,
) -> Response:
    """Forward an HTTP request to the upstream provider with auth.

    Args:
        request: Original incoming request.
        provider: Resolved provider config with base_url and api_key.
        path: API path to append to base_url.

    Returns:
        Proxied response from the upstream provider.
    """
    body = await request.body()
    upstream_url = f"{provider.base_url.rstrip('/')}{path}"

    # Forward original headers, replacing auth and removing internal headers
    headers = dict(request.headers)
    headers["authorization"] = f"Bearer {provider.api_key}"
    # Remove hop-by-hop and internal headers
    for h in ("host", "x-amelia-profile", "content-length"):
        headers.pop(h, None)

    async with httpx.AsyncClient(timeout=300.0) as client:
        upstream_response = await client.request(
            method=request.method,
            url=upstream_url,
            content=body,
            headers=headers,
        )

    # Pass through the upstream response
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=dict(upstream_response.headers),
    )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/sandbox/test_proxy.py -v`
Expected: PASS

**Step 5: Lint and type check**

Run: `uv run ruff check amelia/sandbox/proxy.py && uv run mypy amelia/sandbox/proxy.py`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/sandbox/proxy.py tests/unit/sandbox/test_proxy.py
git commit -m "feat(sandbox): add LLM + git credential proxy router"
```

---

### Task 5: Add proxy forwarding tests (upstream mocking)

**Files:**
- Modify: `tests/unit/sandbox/test_proxy.py`

Test that the proxy actually forwards requests correctly with authentication headers attached.

**Step 1: Write the tests**

Append to `tests/unit/sandbox/test_proxy.py`:

```python
class TestProxyForwarding:
    def test_chat_completions_forwards_with_auth(self, client, monkeypatch):
        """Verify proxy attaches auth header and forwards to upstream."""
        captured_request = {}

        async def mock_request(self, method, url, content, headers, **kwargs):
            captured_request["method"] = method
            captured_request["url"] = str(url)
            captured_request["headers"] = dict(headers)
            captured_request["content"] = content

            class MockResponse:
                status_code = 200
                content = b'{"choices": []}'
                headers = {"content-type": "application/json"}

            return MockResponse()

        monkeypatch.setattr(httpx.AsyncClient, "request", mock_request)

        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "hi"}]},
            headers={"X-Amelia-Profile": "work"},
        )

        assert response.status_code == 200
        assert captured_request["url"] == "https://openrouter.ai/api/v1/chat/completions"
        assert captured_request["headers"]["authorization"] == "Bearer sk-or-test-key"
        assert "x-amelia-profile" not in captured_request["headers"]

    def test_embeddings_forwards_with_auth(self, client, monkeypatch):
        """Verify embeddings endpoint forwards correctly."""
        captured_request = {}

        async def mock_request(self, method, url, content, headers, **kwargs):
            captured_request["url"] = str(url)
            captured_request["headers"] = dict(headers)

            class MockResponse:
                status_code = 200
                content = b'{"data": []}'
                headers = {"content-type": "application/json"}

            return MockResponse()

        monkeypatch.setattr(httpx.AsyncClient, "request", mock_request)

        response = client.post(
            "/proxy/v1/embeddings",
            json={"model": "test", "input": "hello"},
            headers={"X-Amelia-Profile": "personal"},
        )

        assert response.status_code == 200
        assert captured_request["url"] == "https://api.anthropic.com/v1/embeddings"
        assert captured_request["headers"]["authorization"] == "Bearer sk-ant-test-key"

    def test_upstream_error_passed_through(self, client, monkeypatch):
        """Verify upstream errors are forwarded to the caller."""

        async def mock_request(self, method, url, content, headers, **kwargs):
            class MockResponse:
                status_code = 429
                content = b'{"error": "rate limited"}'
                headers = {"content-type": "application/json"}

            return MockResponse()

        monkeypatch.setattr(httpx.AsyncClient, "request", mock_request)

        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={"X-Amelia-Profile": "work"},
        )

        assert response.status_code == 429
```

**Step 2: Run all proxy tests**

Run: `uv run pytest tests/unit/sandbox/test_proxy.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/unit/sandbox/test_proxy.py
git commit -m "test(sandbox): add proxy forwarding tests with upstream mocking"
```

---

### Task 6: Mount proxy router on the FastAPI server

**Files:**
- Modify: `amelia/server/main.py`
- Test: `tests/unit/server/test_proxy_mount.py`

Wire the proxy router into the existing FastAPI app with a real profile-based provider resolver.

**Step 1: Write the failing test**

```python
# tests/unit/server/test_proxy_mount.py
"""Tests that the proxy router is mounted on the FastAPI application."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def app_client():
    """Create a test client for the full app with mocked database."""
    with (
        patch("amelia.server.main._check_dependencies"),
        patch("amelia.server.main.Database"),
        patch("amelia.server.main.Migrator"),
    ):
        from amelia.server.main import create_app

        app = create_app()
        yield TestClient(app)


class TestProxyMount:
    def test_proxy_chat_completions_route_exists(self, app_client):
        """Verify /proxy/v1/chat/completions route is mounted."""
        response = app_client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
        )
        # Should get 400 (missing profile header), not 404 (route missing)
        assert response.status_code == 400
        assert "X-Amelia-Profile" in response.json()["detail"]

    def test_proxy_embeddings_route_exists(self, app_client):
        """Verify /proxy/v1/embeddings route is mounted."""
        response = app_client.post(
            "/proxy/v1/embeddings",
            json={"model": "test", "input": "hello"},
        )
        assert response.status_code == 400
        assert "X-Amelia-Profile" in response.json()["detail"]

    def test_proxy_git_credentials_route_exists(self, app_client):
        """Verify /proxy/v1/git/credentials route is mounted."""
        response = app_client.post(
            "/proxy/v1/git/credentials",
            content="host=github.com\n",
        )
        assert response.status_code == 400
        assert "X-Amelia-Profile" in response.json()["detail"]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/test_proxy_mount.py -v`
Expected: FAIL — proxy routes not yet mounted, expecting 404 instead of 400

**Step 3: Add proxy mounting to `create_app()`**

In `amelia/server/main.py`, add the import near the other route imports:

```python
from amelia.sandbox.proxy import ProviderConfig, create_proxy_router
```

Inside `create_app()`, after the existing router includes and before the dashboard section, add:

```python
    # Mount sandbox proxy routes
    async def _resolve_provider(profile_name: str) -> ProviderConfig | None:
        """Resolve LLM provider config from profile name.

        Looks up the profile in the database, finds the developer agent's
        provider setting, and returns the corresponding upstream URL and API key.
        """
        import os

        profile_repo = get_profile_repository()
        profile = await profile_repo.get_profile(profile_name)
        if profile is None:
            return None

        # Use developer agent config to determine provider
        try:
            agent_config = profile.get_agent_config("developer")
        except ValueError:
            return None

        provider = agent_config.options.get("provider", "openrouter")

        # Map provider to upstream config
        provider_registry: dict[str, tuple[str, str]] = {
            "openrouter": (
                "https://openrouter.ai/api/v1",
                os.environ.get("OPENROUTER_API_KEY", ""),
            ),
            "anthropic": (
                "https://api.anthropic.com/v1",
                os.environ.get("ANTHROPIC_API_KEY", ""),
            ),
            "openai": (
                "https://api.openai.com/v1",
                os.environ.get("OPENAI_API_KEY", ""),
            ),
        }

        entry = provider_registry.get(provider)
        if entry is None or not entry[1]:
            return None

        return ProviderConfig(base_url=entry[0], api_key=entry[1])

    proxy_router = create_proxy_router(resolve_provider=_resolve_provider)
    application.include_router(proxy_router, prefix="/proxy/v1")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/test_proxy_mount.py -v`
Expected: PASS

**Step 5: Run all existing server tests to verify no regression**

Run: `uv run pytest tests/unit/server/ -v`
Expected: PASS

**Step 6: Lint and type check**

Run: `uv run ruff check amelia/server/main.py amelia/sandbox/proxy.py && uv run mypy amelia/server/main.py`
Expected: PASS

**Step 7: Commit**

```bash
git add amelia/server/main.py tests/unit/server/test_proxy_mount.py
git commit -m "feat(sandbox): mount LLM proxy router on FastAPI server"
```

---

### Task 7: Update `__init__.py` exports and final integration check

**Files:**
- Modify: `amelia/sandbox/__init__.py`

**Step 1: Update sandbox package exports**

```python
# amelia/sandbox/__init__.py
"""Sandbox execution infrastructure for isolated agent environments."""

from amelia.sandbox.provider import SandboxProvider
from amelia.sandbox.proxy import ProviderConfig

__all__ = ["ProviderConfig", "SandboxProvider"]
```

**Step 2: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: PASS

**Step 3: Full lint and type check**

Run: `uv run ruff check amelia/ tests/ && uv run mypy amelia/`
Expected: PASS

**Step 4: Commit**

```bash
git add amelia/sandbox/__init__.py
git commit -m "feat(sandbox): export SandboxProvider and ProviderConfig from package"
```

---

### Task 8: Add `ProfileRepository` handling for `sandbox` field (DB roundtrip)

**Files:**
- Modify: `amelia/server/database/profile_repository.py`
- Test: Add to existing profile repo tests or `tests/unit/server/test_profile_sandbox_db.py`

The `sandbox` field needs to be persisted and restored from the database. Since `Profile` already stores agents as JSONB, sandbox config should follow the same pattern.

**Step 1: Write the failing test**

```python
# tests/unit/server/test_profile_sandbox_db.py
"""Tests for SandboxConfig persistence in ProfileRepository."""

import pytest

from amelia.core.types import SandboxConfig


class TestProfileSandboxSerialization:
    def test_sandbox_config_serializes_to_dict(self):
        config = SandboxConfig(mode="container", image="custom:latest")
        data = config.model_dump()
        assert data["mode"] == "container"
        assert data["image"] == "custom:latest"

    def test_sandbox_config_roundtrips_through_json(self):
        config = SandboxConfig(
            mode="container",
            network_allowlist_enabled=True,
            network_allowed_hosts=["example.com"],
        )
        json_str = config.model_dump_json()
        restored = SandboxConfig.model_validate_json(json_str)
        assert restored == config

    def test_default_sandbox_config_roundtrips(self):
        config = SandboxConfig()
        data = config.model_dump()
        restored = SandboxConfig(**data)
        assert restored.mode == "none"

    def test_profile_with_sandbox_serializes(self):
        from amelia.core.types import AgentConfig, DriverType, Profile

        profile = Profile(
            name="test",
            working_dir="/tmp",
            sandbox=SandboxConfig(mode="container"),
            agents={
                "developer": AgentConfig(
                    driver=DriverType.API,
                    model="test-model",
                ),
            },
        )
        data = profile.model_dump()
        assert data["sandbox"]["mode"] == "container"
```

**Step 2: Run tests to verify they pass (these are serialization tests — they should pass already since `SandboxConfig` is a Pydantic model)**

Run: `uv run pytest tests/unit/server/test_profile_sandbox_db.py -v`
Expected: PASS (Pydantic handles serialization automatically)

**Step 3: Check `_row_to_profile` in `ProfileRepository` — update if needed**

The `_row_to_profile` method needs to handle the `sandbox` column. Since this is stored as JSONB, add handling:

Check if the DB schema needs a migration for the `sandbox` column. If so, create:
- A new migration file `amelia/server/database/migrations/NNN_add_sandbox_config.sql`
- Update `_row_to_profile` to read the `sandbox` column
- Update `create_profile` and `update_profile` to write the `sandbox` column

**Important:** The exact migration number and SQL depends on the current schema. Read the existing migration files to determine the next number.

Look at the current DB schema:

Run: `ls amelia/server/database/migrations/`

Then create the migration SQL:

```sql
-- Add sandbox configuration column to profiles table
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS sandbox JSONB NOT NULL DEFAULT '{}';
```

Update `_row_to_profile`:

```python
def _row_to_profile(self, row: asyncpg.Record) -> Profile:
    agents_data = row["agents"]
    agents = {
        name: AgentConfig(**config) for name, config in agents_data.items()
    }

    sandbox_data = row.get("sandbox", {})
    sandbox = SandboxConfig(**sandbox_data) if sandbox_data else SandboxConfig()

    return Profile(
        name=row["id"],
        tracker=row["tracker"],
        working_dir=row["working_dir"],
        plan_output_dir=row["plan_output_dir"],
        plan_path_pattern=row["plan_path_pattern"],
        sandbox=sandbox,
        agents=agents,
    )
```

Update `create_profile` and `update_profile` to include `sandbox` in the SQL INSERT/UPDATE with `profile.sandbox.model_dump()`.

**Step 4: Run all tests**

Run: `uv run pytest tests/unit/ -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/database/profile_repository.py amelia/server/database/migrations/ tests/unit/server/test_profile_sandbox_db.py
git commit -m "feat(sandbox): persist SandboxConfig in profile database"
```

---

### Task 9: Final verification and cleanup

**Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: PASS

**Step 2: Full lint + type check**

Run: `uv run ruff check amelia/ tests/ && uv run mypy amelia/`
Expected: PASS

**Step 3: Review all changes**

Run: `git diff main --stat`

Verify the changeset matches the expected PR1 scope:
- `amelia/core/types.py` — `SandboxConfig` model, `Profile.sandbox` field
- `amelia/sandbox/__init__.py` — package init with exports
- `amelia/sandbox/provider.py` — `SandboxProvider` protocol
- `amelia/sandbox/proxy.py` — LLM + git credential proxy router
- `amelia/drivers/api/deepagents.py` — `base_url` parameter on `_create_chat_model()`
- `amelia/server/main.py` — proxy router mounted at `/proxy/v1/`
- `amelia/server/database/profile_repository.py` — sandbox field persistence
- `amelia/server/database/migrations/NNN_add_sandbox_config.sql` — DB migration
- `tests/unit/core/test_sandbox_config.py`
- `tests/unit/sandbox/__init__.py`
- `tests/unit/sandbox/test_provider.py`
- `tests/unit/sandbox/test_proxy.py`
- `tests/unit/server/test_proxy_mount.py`
- `tests/unit/server/test_profile_sandbox_db.py`
- `tests/unit/drivers/test_create_chat_model.py`

**Step 4: Commit any remaining changes**

Squash or keep as-is depending on preference.
