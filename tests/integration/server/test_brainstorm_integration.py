"""Integration tests for brainstorming endpoints.

Tests the HTTP layer with real route handlers, real BrainstormService,
and real BrainstormRepository (PostgreSQL test database).

Real components:
- FastAPI route handlers
- BrainstormService
- BrainstormRepository with PostgreSQL test database
- Request/Response model validation

Uses httpx.AsyncClient with ASGITransport to keep the ASGI app in the
same event loop as the asyncpg pool (TestClient creates a separate thread
with its own event loop, causing asyncpg event loop mismatches).
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from amelia.server.database.brainstorm_repository import BrainstormRepository
from amelia.server.database.connection import Database
from amelia.server.database.migrator import Migrator
from amelia.server.dependencies import get_orchestrator, get_profile_repository
from amelia.server.events.bus import EventBus
from amelia.server.main import create_app
from amelia.server.routes.brainstorm import get_brainstorm_service
from amelia.server.services.brainstorm import BrainstormService

from .conftest import AsyncClientFactory, noop_lifespan


DATABASE_URL = "postgresql://amelia:amelia@localhost:5432/amelia_test"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def test_db() -> AsyncGenerator[Database, None]:
    """Create and initialize PostgreSQL test database."""
    db = Database(DATABASE_URL)
    await db.connect()
    migrator = Migrator(db)
    await migrator.run()
    yield db
    await db.close()


@pytest.fixture
def test_brainstorm_repository(test_db: Database) -> BrainstormRepository:
    """Create repository backed by test database."""
    return BrainstormRepository(test_db)


@pytest.fixture
def test_event_bus() -> EventBus:
    """Create event bus for testing."""
    return EventBus()


@pytest.fixture
def test_brainstorm_service(
    test_brainstorm_repository: BrainstormRepository,
    test_event_bus: EventBus,
) -> BrainstormService:
    """Create real BrainstormService with test dependencies."""
    return BrainstormService(test_brainstorm_repository, test_event_bus)


@pytest.fixture
async def test_client(
    test_brainstorm_service: BrainstormService,
    async_client_factory: AsyncClientFactory,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create async test client with real dependencies.

    Uses httpx.AsyncClient with ASGITransport so the ASGI app runs in the
    same event loop as the asyncpg pool created by test_db.
    """
    app = create_app()

    app.router.lifespan_context = noop_lifespan
    app.dependency_overrides[get_brainstorm_service] = lambda: test_brainstorm_service

    # Override dependencies that would otherwise require the database lifespan
    mock_profile_repo = AsyncMock()
    mock_profile_repo.get_profile = AsyncMock(return_value=None)
    app.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo

    mock_orch = MagicMock()
    mock_orch.queue_workflow = AsyncMock(return_value="00000000-0000-4000-8000-000000000001")
    app.dependency_overrides[get_orchestrator] = lambda: mock_orch

    async with async_client_factory(app) as client:
        yield client


# =============================================================================
# Test Classes
# =============================================================================


@pytest.mark.integration
class TestBrainstormIntegration:
    """Test brainstorming endpoints are wired correctly."""

    async def test_brainstorm_routes_registered(
        self, test_client: httpx.AsyncClient
    ) -> None:
        """Brainstorm routes should be accessible.

        The POST /sessions endpoint exists (should return 422 for missing body,
        not 404 for missing route).
        """
        response = await test_client.post("/api/brainstorm/sessions", json={})
        # Should be 422 (validation error) not 404 (not found)
        assert response.status_code != 404, (
            f"Expected 422 validation error but got {response.status_code}. "
            "Brainstorm routes may not be registered."
        )
        assert response.status_code == 422

    async def test_list_sessions_endpoint(
        self, test_client: httpx.AsyncClient
    ) -> None:
        """List sessions endpoint should work."""
        response = await test_client.get("/api/brainstorm/sessions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_create_session_returns_201(
        self, test_client: httpx.AsyncClient
    ) -> None:
        """Creating a session should return 201 with session data."""
        response = await test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test", "topic": "Design a cache layer"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "session" in data
        session = data["session"]
        assert "id" in session
        assert session["profile_id"] == "test"
        assert session["topic"] == "Design a cache layer"
        assert session["status"] == "active"

    async def test_get_session_returns_session_with_history(
        self, test_client: httpx.AsyncClient
    ) -> None:
        """Getting a session should return session with messages and artifacts."""
        # Create a session first
        create_response = await test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test", "topic": "API design"},
        )
        assert create_response.status_code == 201
        session_id = create_response.json()["session"]["id"]

        # Get the session
        response = await test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert response.status_code == 200
        data = response.json()
        assert "session" in data
        assert "messages" in data
        assert "artifacts" in data
        assert data["session"]["id"] == session_id

    async def test_get_nonexistent_session_returns_404(
        self, test_client: httpx.AsyncClient
    ) -> None:
        """Getting a non-existent session should return 404."""
        response = await test_client.get("/api/brainstorm/sessions/nonexistent-id")
        assert response.status_code == 404

    async def test_delete_session_returns_204(
        self, test_client: httpx.AsyncClient
    ) -> None:
        """Deleting a session should return 204."""
        # Create a session first
        create_response = await test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        assert create_response.status_code == 201
        session_id = create_response.json()["session"]["id"]

        # Delete the session
        response = await test_client.delete(f"/api/brainstorm/sessions/{session_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = await test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_response.status_code == 404
