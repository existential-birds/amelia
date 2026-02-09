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

    proxy = create_proxy_router(resolve_provider=_resolve_provider)
    app.include_router(proxy.router, prefix="/proxy/v1")
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


class _MockStream(httpx.AsyncByteStream):
    """Async byte stream that yields data once, compatible with httpx streaming."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    async def __aiter__(self):
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


class TestProxyForwarding:
    def test_chat_completions_forwards_with_auth(self, client, monkeypatch):
        """Verify proxy attaches auth header and forwards to upstream."""
        captured_request = {}

        async def mock_send(self, request, *, stream=False, **kwargs):
            captured_request["method"] = request.method
            captured_request["url"] = str(request.url)
            captured_request["headers"] = dict(request.headers)
            return _streaming_response(200, b'{"choices": []}', request)

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

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

        async def mock_send(self, request, *, stream=False, **kwargs):
            captured_request["url"] = str(request.url)
            captured_request["headers"] = dict(request.headers)
            return _streaming_response(200, b'{"data": []}', request)

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

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

        async def mock_send(self, request, *, stream=False, **kwargs):
            return _streaming_response(429, b'{"error": "rate limited"}', request)

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

        response = client.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={"X-Amelia-Profile": "work"},
        )

        assert response.status_code == 429


class TestProxyCleanup:
    async def test_cleanup_closes_http_client(self, monkeypatch):
        """Verify cleanup() closes the httpx.AsyncClient."""
        close_called = []
        original_aclose = httpx.AsyncClient.aclose

        async def tracked_aclose(self):
            close_called.append(True)
            await original_aclose(self)

        monkeypatch.setattr(httpx.AsyncClient, "aclose", tracked_aclose)

        async def _resolve_provider(profile_name: str) -> ProviderConfig | None:
            return None

        proxy = create_proxy_router(resolve_provider=_resolve_provider)
        assert len(close_called) == 0

        await proxy.cleanup()
        assert len(close_called) == 1
