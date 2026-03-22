"""Tests for the LLM + git credential proxy router."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.sandbox.proxy import PROXY_MAX_BODY_BYTES, ProviderConfig, create_proxy_router


@pytest.fixture
async def proxy_app(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FastAPI]:
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

    proxy = create_proxy_router(resolve_provider=_resolve_provider)
    app.include_router(proxy.router, prefix="/proxy/v1")
    yield app
    await proxy.cleanup()


@pytest.fixture
def client(proxy_app: FastAPI) -> TestClient:
    return TestClient(proxy_app)


class TestProviderConfig:
    def test_provider_config_fields(self) -> None:
        config = ProviderConfig(
            base_url="https://openrouter.ai/api/v1",
            api_key="sk-test",
        )
        assert config.base_url == "https://openrouter.ai/api/v1"
        assert config.api_key == "sk-test"


class TestProxyProfileResolution:
    def test_missing_profile_header_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
        )
        assert response.status_code == 400
        assert "X-Amelia-Profile" in response.json()["detail"]

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


class TestProxyGitCredentials:
    def test_git_credentials_endpoint_exists(self, client: TestClient) -> None:
        response = client.post(
            "/proxy/v1/git/credentials",
            content="host=github.com\nprotocol=https\n",
            headers={"X-Amelia-Profile": "work"},
        )
        # Should not 404 — route exists. Actual credential fetching is tested
        # in integration tests since it depends on host git config.
        assert response.status_code in (200, 501)


class _MockStream(httpx.AsyncByteStream):
    """Async byte stream that yields data once, compatible with httpx streaming.

    The proxy uses ``stream=True`` and ``aiter_raw()``, so tests must provide
    responses with an unconsumed stream. Using ``content=`` would mark the
    response as already consumed, causing the proxy to hang or fail.
    """

    def __init__(self, data: bytes) -> None:
        self._data = data

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._data

    async def aclose(self) -> None:
        pass


def _streaming_response(
    status_code: int, body: bytes, request: httpx.Request
) -> httpx.Response:
    """Build an httpx.Response with an unconsumed async stream.

    The proxy uses ``stream=True`` and ``aiter_raw()``, so the response
    must have an unconsumed stream (``content=`` marks it consumed).
    """
    return httpx.Response(
        status_code=status_code,
        stream=_MockStream(body),
        headers={"content-type": "application/json"},
        request=request,
    )


@pytest.fixture
def mock_upstream(monkeypatch: pytest.MonkeyPatch):
    """Monkeypatch ``httpx.AsyncClient.send`` to return a canned response.

    Returns a callable ``(status, body, *, raise_exc=None)`` that wires up
    the mock and returns a dict where captured request fields are stored.

    If *raise_exc* is given, the mock raises that exception instead of
    returning a response.
    """

    def _configure(
        status: int = 200,
        body: bytes = b'{"choices": []}',
        *,
        raise_exc: Exception | None = None,
    ) -> dict[str, Any]:
        captured: dict[str, Any] = {}

        async def _send(
            self: Any,
            request: httpx.Request,
            *,
            stream: bool = False,
            **kwargs: Any,
        ) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            captured["headers"] = dict(request.headers)
            if raise_exc is not None:
                raise raise_exc
            return _streaming_response(status, body, request)

        monkeypatch.setattr(httpx.AsyncClient, "send", _send)
        return captured

    return _configure


class TestProxyForwarding:
    def test_chat_completions_forwards_with_auth(self, client: TestClient, mock_upstream) -> None:
        """Verify proxy attaches auth header and forwards to upstream."""
        captured = mock_upstream(200, b'{"choices": []}')

        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "hi"}]},
            headers={"X-Amelia-Profile": "work"},
        )

        assert response.status_code == 200
        assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
        assert captured["headers"]["authorization"] == "Bearer sk-or-test-key"
        assert "x-amelia-profile" not in captured["headers"]

    def test_embeddings_forwards_with_auth(self, client: TestClient, mock_upstream) -> None:
        """Verify embeddings endpoint forwards correctly."""
        captured = mock_upstream(200, b'{"data": []}')

        response = client.post(
            "/proxy/v1/embeddings",
            json={"model": "test", "input": "hello"},
            headers={"X-Amelia-Profile": "personal"},
        )

        assert response.status_code == 200
        assert captured["url"] == "https://api.anthropic.com/v1/embeddings"
        assert captured["headers"]["authorization"] == "Bearer sk-ant-test-key"

    def test_upstream_error_passed_through(self, client: TestClient, mock_upstream) -> None:
        """Verify upstream errors are forwarded to the caller."""
        mock_upstream(429, b'{"error": "rate limited"}')

        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={"X-Amelia-Profile": "work"},
        )

        assert response.status_code == 429


class TestProxyErrorSanitization:
    """Upstream errors must not leak internal details to the caller."""

    def test_connect_error_is_generic(self, client: TestClient, mock_upstream) -> None:
        mock_upstream(raise_exc=httpx.ConnectError("Connection refused: 10.0.0.5:443"))

        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={"X-Amelia-Profile": "work"},
        )
        assert response.status_code == 502
        detail = response.json()["detail"]
        assert "10.0.0.5" not in detail
        assert "Connection refused" not in detail

    def test_timeout_error_is_generic(self, client: TestClient, mock_upstream) -> None:
        mock_upstream(raise_exc=httpx.ReadTimeout("Read timed out on host api.openrouter.ai:443"))

        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={"X-Amelia-Profile": "work"},
        )
        assert response.status_code == 504
        detail = response.json()["detail"]
        assert "openrouter" not in detail

    def test_http_error_is_generic(self, client: TestClient, mock_upstream) -> None:
        mock_upstream(raise_exc=httpx.DecodingError("Invalid chunk encoding from 10.0.0.5"))

        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={"X-Amelia-Profile": "work"},
        )
        assert response.status_code == 502
        detail = response.json()["detail"]
        assert "10.0.0.5" not in detail
        assert "DecodingError" not in detail


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

    def test_invalid_content_length_returns_400(
        self, client: TestClient,
    ) -> None:
        """Malformed Content-Length header returns 400."""
        response = client.post(
            "/proxy/v1/chat/completions",
            content=b"x",
            headers={
                "X-Amelia-Profile": "work",
                "Content-Length": "abc",
            },
        )
        assert response.status_code == 400
        assert "Content-Length" in response.json()["detail"]

    def test_actual_body_exceeding_limit_returns_413(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Actual body size (not just Content-Length) is checked."""
        import amelia.sandbox.proxy as proxy_module

        monkeypatch.setattr(proxy_module, "PROXY_MAX_BODY_BYTES", 50)

        app = FastAPI()

        async def _resolve(name: str) -> ProviderConfig | None:
            if name == "work":
                return ProviderConfig(base_url="https://example.com/v1", api_key="k")
            return None

        proxy = create_proxy_router(resolve_provider=_resolve)
        app.include_router(proxy.router, prefix="/proxy/v1")

        with TestClient(app) as c:
            response = c.post(
                "/proxy/v1/chat/completions",
                content=b"x" * 100,
                headers={"X-Amelia-Profile": "work"},
            )
        assert response.status_code == 413

    def test_normal_request_passes_size_check(
        self, client: TestClient, mock_upstream,
    ) -> None:
        """Normal-sized request passes through."""
        mock_upstream(200, b'{"choices": []}')

        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "hi"}]},
            headers={"X-Amelia-Profile": "work"},
        )
        assert response.status_code == 200


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
        self, authed_client: TestClient, mock_upstream,
    ) -> None:
        mock_upstream(200, b'{"choices": []}')

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
        self, authed_client: TestClient, mock_upstream,
    ) -> None:
        """Proxy token must be stripped before forwarding."""
        captured = mock_upstream(200, b'{"choices": []}')

        authed_client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={
                "X-Amelia-Profile": "work",
                "X-Amelia-Proxy-Token": "valid-secret-token",
            },
        )
        assert "x-amelia-proxy-token" not in captured["headers"]

    def test_no_validator_skips_token_check(self, client: TestClient, mock_upstream) -> None:
        """When no token_validator is set, requests pass without a token."""
        mock_upstream(200, b'{"choices": []}')

        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={"X-Amelia-Profile": "work"},
        )
        assert response.status_code == 200


class TestProxySyncTokenValidator:
    """Sync token validators work without async overhead."""

    @pytest.fixture
    async def sync_authed_app(self) -> AsyncIterator[FastAPI]:
        """App with sync token validation enabled."""
        app = FastAPI()

        async def _resolve_provider(profile_name: str) -> ProviderConfig | None:
            if profile_name == "work":
                return ProviderConfig(
                    base_url="https://openrouter.ai/api/v1",
                    api_key="sk-or-test-key",
                )
            return None

        def _validate_token(token: str) -> bool:
            """Sync validator - no async overhead for dict lookups."""
            return token == "sync-valid-token"

        proxy = create_proxy_router(
            resolve_provider=_resolve_provider,
            token_validator=_validate_token,
        )
        app.include_router(proxy.router, prefix="/proxy/v1")
        yield app
        await proxy.cleanup()

    @pytest.fixture
    def sync_authed_client(self, sync_authed_app: FastAPI) -> TestClient:
        return TestClient(sync_authed_app)

    def test_sync_validator_rejects_invalid_token(self, sync_authed_client: TestClient) -> None:
        response = sync_authed_client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={
                "X-Amelia-Profile": "work",
                "X-Amelia-Proxy-Token": "wrong-token",
            },
        )
        assert response.status_code == 401

    def test_sync_validator_accepts_valid_token(
        self, sync_authed_client: TestClient, mock_upstream,
    ) -> None:
        mock_upstream(200, b'{"choices": []}')

        response = sync_authed_client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={
                "X-Amelia-Profile": "work",
                "X-Amelia-Proxy-Token": "sync-valid-token",
            },
        )
        assert response.status_code == 200


class TestProxyBodyLimitConfigurable:
    """Body size limit is configurable via AMELIA_PROXY_MAX_BODY_MB."""

    def test_body_limit_configurable_via_env(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AMELIA_PROXY_MAX_BODY_MB env var controls the body size limit."""
        monkeypatch.setenv("AMELIA_PROXY_MAX_BODY_MB", "5")

        import importlib

        import amelia.sandbox.proxy as proxy_module

        importlib.reload(proxy_module)

        try:
            assert proxy_module.PROXY_MAX_BODY_BYTES == 5 * 1024 * 1024
        finally:
            monkeypatch.delenv("AMELIA_PROXY_MAX_BODY_MB", raising=False)
            importlib.reload(proxy_module)


class TestProxyCleanup:
    async def test_cleanup_closes_http_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify cleanup() closes the httpx.AsyncClient."""
        close_called = []
        original_aclose = httpx.AsyncClient.aclose

        async def tracked_aclose(self: httpx.AsyncClient) -> None:
            close_called.append(True)
            await original_aclose(self)

        monkeypatch.setattr(httpx.AsyncClient, "aclose", tracked_aclose)

        async def _resolve_provider(profile_name: str) -> ProviderConfig | None:
            return None

        proxy = create_proxy_router(resolve_provider=_resolve_provider)
        assert len(close_called) == 0

        await proxy.cleanup()
        assert len(close_called) == 1
