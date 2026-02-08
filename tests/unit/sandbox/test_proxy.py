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
