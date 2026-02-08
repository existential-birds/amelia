"""Test static file serving for dashboard."""

import pytest
from fastapi.testclient import TestClient
from httpx import Response


class TestDashboardServing:
    """Tests for dashboard static file serving."""

    def _assert_spa_response(self, response: Response) -> None:
        """Assert response is either dashboard HTML or 'not built' JSON."""
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            assert b"Amelia Dashboard" in response.content
        else:
            data = response.json()
            assert data["message"] == "Dashboard not built"
            assert "instructions" in data

    @pytest.mark.parametrize("path", ["/", "/workflows", "/settings"])
    def test_spa_routes_return_index_or_message(self, mock_app_client: TestClient, path: str) -> None:
        """SPA routes return dashboard index.html or helpful message."""
        response = mock_app_client.get(path)
        self._assert_spa_response(response)

    @pytest.mark.parametrize("path,expected_status", [
        ("/api/nonexistent", 404),
        ("/ws/events", 404),  # Non-WebSocket GET returns 404
    ])
    def test_reserved_prefixes_not_spa_fallback(
        self, mock_app_client: TestClient, path: str, expected_status: int
    ) -> None:
        """API and WebSocket routes don't fall through to SPA."""
        response = mock_app_client.get(path)
        assert response.status_code == expected_status

    def test_api_health_endpoint(self, mock_app_client: TestClient) -> None:
        """Health endpoint works normally."""
        response = mock_app_client.get("/api/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}
