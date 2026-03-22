"""Tests that the proxy router is mounted on the FastAPI application."""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@contextmanager
def _patched_app():
    """Create the FastAPI app with mocked database dependencies."""
    with (
        patch("amelia.server.main._check_dependencies"),
        patch("amelia.server.main.Database"),
        patch("amelia.server.main.Migrator"),
    ):
        from amelia.server.main import create_app

        yield create_app()


@pytest.fixture()
def app_client():
    """Create a test client for the full app with mocked database."""
    with _patched_app() as app:
        yield TestClient(app)


class TestProxyMount:
    @pytest.mark.parametrize(
        "method,path,kwargs",
        [
            pytest.param(
                "post",
                "/proxy/v1/chat/completions",
                {"json": {"model": "test", "messages": []}},
                id="chat-completions",
            ),
            pytest.param(
                "post",
                "/proxy/v1/embeddings",
                {"json": {"model": "test", "input": "hello"}},
                id="embeddings",
            ),
            pytest.param(
                "post",
                "/proxy/v1/git/credentials",
                {"content": "host=github.com\n"},
                id="git-credentials",
            ),
        ],
    )
    def test_proxy_route_exists(self, app_client, method: str, path: str, kwargs: dict) -> None:
        """Verify proxy route is mounted and returns 400 (missing profile header)."""
        response = getattr(app_client, method)(path, **kwargs)
        assert response.status_code == 400


class TestProxyTokenRegistration:
    """Token registration and validation on the full app."""

    @pytest.fixture()
    def _app_with_token(self):
        """Create app and register a proxy token."""
        with _patched_app() as app:
            app.state.register_proxy_token("valid-token-abc", "container-1")
            yield TestClient(app)

    def test_proxy_rejects_invalid_token_when_registered(self, _app_with_token):
        """When tokens are registered, wrong token gets 401."""
        response = _app_with_token.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={"X-Amelia-Proxy-Token": "wrong-token"},
        )
        assert response.status_code == 401

    def test_proxy_accepts_valid_token_when_registered(self, _app_with_token):
        """When tokens are registered, correct token passes validation."""
        response = _app_with_token.post(
            "/proxy/v1/chat/completions",
            json={"model": "test", "messages": []},
            headers={"X-Amelia-Proxy-Token": "valid-token-abc"},
        )
        # Token passes -> 400 (missing profile header)
        assert response.status_code == 400
