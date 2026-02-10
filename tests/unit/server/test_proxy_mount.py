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
