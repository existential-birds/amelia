"""Tests for brainstorming API routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.models.brainstorm import BrainstormingSession
from amelia.server.routes.brainstorm import router


class TestBrainstormRoutes:
    """Test brainstorming API endpoints."""

    @pytest.fixture
    def mock_service(self) -> MagicMock:
        """Create mock BrainstormService."""
        service = MagicMock()
        service.create_session = AsyncMock()
        service.get_session_with_history = AsyncMock()
        service.list_sessions = AsyncMock(return_value=[])
        service.delete_session = AsyncMock()
        return service

    @pytest.fixture
    def mock_driver(self) -> MagicMock:
        """Create mock driver."""
        return MagicMock()

    @pytest.fixture
    def app(self, mock_service: MagicMock, mock_driver: MagicMock) -> FastAPI:
        """Create test app with mocked dependencies."""
        app = FastAPI()
        app.include_router(router, prefix="/api/brainstorm")

        # Override dependencies
        from amelia.server.routes.brainstorm import (
            get_brainstorm_service,
            get_cwd,
            get_driver,
        )
        app.dependency_overrides[get_brainstorm_service] = lambda: mock_service
        app.dependency_overrides[get_driver] = lambda: mock_driver
        app.dependency_overrides[get_cwd] = lambda: "/test/cwd"

        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app)


class TestCreateSession(TestBrainstormRoutes):
    """Test POST /api/brainstorm/sessions."""

    def test_create_session_minimal(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should create session with minimal fields."""
        now = datetime.now(UTC)
        mock_service.create_session.return_value = BrainstormingSession(
            id="sess-123",
            profile_id="work",
            status="active",
            created_at=now,
            updated_at=now,
        )

        response = client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "work"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "sess-123"
        assert data["status"] == "active"

    def test_create_session_with_topic(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should create session with topic."""
        now = datetime.now(UTC)
        mock_service.create_session.return_value = BrainstormingSession(
            id="sess-123",
            profile_id="work",
            status="active",
            topic="Design a cache",
            created_at=now,
            updated_at=now,
        )

        response = client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "work", "topic": "Design a cache"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["topic"] == "Design a cache"


class TestListSessions(TestBrainstormRoutes):
    """Test GET /api/brainstorm/sessions."""

    def test_list_sessions_empty(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should return empty list when no sessions."""
        response = client.get("/api/brainstorm/sessions")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_sessions_with_filter(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should pass filters to service."""
        now = datetime.now(UTC)
        mock_service.list_sessions.return_value = [
            BrainstormingSession(
                id="sess-1", profile_id="work", status="active",
                created_at=now, updated_at=now,
            )
        ]

        response = client.get(
            "/api/brainstorm/sessions",
            params={"profile_id": "work", "status": "active"},
        )

        assert response.status_code == 200
        mock_service.list_sessions.assert_called_once_with(
            profile_id="work", status="active", limit=50
        )


class TestGetSession(TestBrainstormRoutes):
    """Test GET /api/brainstorm/sessions/{id}."""

    def test_get_session_found(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should return session with history."""
        now = datetime.now(UTC)
        mock_service.get_session_with_history.return_value = {
            "session": BrainstormingSession(
                id="sess-123", profile_id="work", status="active",
                created_at=now, updated_at=now,
            ),
            "messages": [],
            "artifacts": [],
        }

        response = client.get("/api/brainstorm/sessions/sess-123")

        assert response.status_code == 200
        data = response.json()
        assert data["session"]["id"] == "sess-123"

    def test_get_session_not_found(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should return 404 for non-existent session."""
        mock_service.get_session_with_history.return_value = None

        response = client.get("/api/brainstorm/sessions/nonexistent")

        assert response.status_code == 404


class TestDeleteSession(TestBrainstormRoutes):
    """Test DELETE /api/brainstorm/sessions/{id}."""

    def test_delete_session(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should delete session."""
        response = client.delete("/api/brainstorm/sessions/sess-123")

        assert response.status_code == 204
        mock_service.delete_session.assert_called_once_with("sess-123")


class TestSendMessage(TestBrainstormRoutes):
    """Test POST /api/brainstorm/sessions/{id}/message."""

    def test_send_message_returns_message_id(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should return message_id on success."""
        from amelia.drivers.base import AgenticMessage, AgenticMessageType

        # Mock send_message as async generator
        async def mock_send_message(*args, **kwargs):
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Response",
            )

        mock_service.send_message = mock_send_message

        response = client.post(
            "/api/brainstorm/sessions/sess-123/message",
            json={"content": "Design a cache"},
        )

        assert response.status_code == 202
        data = response.json()
        assert "message_id" in data

    def test_send_message_session_not_found(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Should return 404 when session not found."""
        # Mock send_message to raise ValueError (session not found)
        async def mock_send_message(*args, **kwargs):
            raise ValueError("Session not found: nonexistent")
            # Make it an async generator by yielding (unreachable)
            yield  # noqa: B901

        mock_service.send_message = mock_send_message

        response = client.post(
            "/api/brainstorm/sessions/nonexistent/message",
            json={"content": "Design a cache"},
        )

        assert response.status_code == 404
