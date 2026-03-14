"""Tests that the proxy router is mounted on the FastAPI application."""

from unittest.mock import patch

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
        # With no tokens registered, validation passes → 400 (missing profile header)
        assert response.status_code == 400

    def test_proxy_embeddings_route_exists(self, app_client):
        """Verify /proxy/v1/embeddings route is mounted."""
        response = app_client.post(
            "/proxy/v1/embeddings",
            json={"model": "test", "input": "hello"},
        )
        # With no tokens registered, validation passes → 400 (missing profile header)
        assert response.status_code == 400

    def test_proxy_git_credentials_route_exists(self, app_client):
        """Verify /proxy/v1/git/credentials route is mounted."""
        response = app_client.post(
            "/proxy/v1/git/credentials",
            content="host=github.com\n",
        )
        # With no tokens registered, validation passes → 400 (missing profile header)
        assert response.status_code == 400


class TestProxyTokenRegistration:
    """Token registration and validation on the full app."""

    @pytest.fixture()
    def _app_with_token(self):
        """Create app and register a proxy token."""
        with (
            patch("amelia.server.main._check_dependencies"),
            patch("amelia.server.main.Database"),
            patch("amelia.server.main.Migrator"),
        ):
            from amelia.server.main import create_app

            app = create_app()
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
        # Token passes → 400 (missing profile header)
        assert response.status_code == 400
