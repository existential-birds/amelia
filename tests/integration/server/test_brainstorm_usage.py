"""Integration tests for brainstorm token usage tracking.

Tests the full usage flow:
- Driver returns usage via get_usage() after RESULT message -> persisted to database
- GET /sessions/{id} returns messages with usage
- Session usage summary aggregation

Real components:
- FastAPI route handlers
- BrainstormService
- BrainstormRepository with PostgreSQL test database

Only mocked:
- Driver (execute_agentic as async generator, get_usage returns DriverUsage)
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverInterface,
    DriverUsage,
)
from amelia.server.database.brainstorm_repository import BrainstormRepository
from amelia.server.database.connection import Database
from amelia.server.database.migrator import Migrator
from amelia.server.events.bus import EventBus
from amelia.server.main import create_app
from amelia.server.routes.brainstorm import (
    get_brainstorm_service,
    get_cwd,
    get_driver,
)
from amelia.server.services.brainstorm import BrainstormService
from tests.conftest import create_mock_execute_agentic


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


def create_mock_driver_with_usage(
    messages: list[AgenticMessage],
    usage: DriverUsage | None,
) -> MagicMock:
    """Create a mock driver that returns specific usage from get_usage().

    Args:
        messages: AgenticMessage objects to yield from execute_agentic.
        usage: DriverUsage to return from get_usage() (or None).

    Returns:
        Mock driver with execute_agentic and get_usage configured.
    """
    driver = MagicMock(spec=DriverInterface)
    driver.execute_agentic = create_mock_execute_agentic(messages)
    driver.get_usage = MagicMock(return_value=usage)
    return driver


def create_test_client(
    service: BrainstormService,
    driver: MagicMock,
    tmp_path: Path,
) -> TestClient:
    """Create test client with real service and mock driver."""
    app = create_app()

    @asynccontextmanager
    async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
        yield

    app.router.lifespan_context = noop_lifespan
    app.dependency_overrides[get_brainstorm_service] = lambda: service
    app.dependency_overrides[get_driver] = lambda: driver
    app.dependency_overrides[get_cwd] = lambda: str(tmp_path)

    return TestClient(app)


# =============================================================================
# Test Classes
# =============================================================================


@pytest.mark.integration
class TestMessageUsageFromDriver:
    """Test that driver usage is correctly persisted with messages."""

    def test_message_usage_persists_from_driver(
        self,
        test_brainstorm_service: BrainstormService,
        tmp_path: Path,
    ) -> None:
        """Driver usage should be saved with assistant message and returned in GET."""
        # Create driver that returns usage
        messages = [
            AgenticMessage(
                type=AgenticMessageType.THINKING,
                content="Let me analyze this...",
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Here's my analysis of the architecture.",
                session_id="driver-session-123",
            ),
        ]
        usage = DriverUsage(
            input_tokens=1500,
            output_tokens=800,
            cost_usd=0.05,
        )
        mock_driver = create_mock_driver_with_usage(messages, usage)
        client = create_test_client(test_brainstorm_service, mock_driver, tmp_path)

        # Create session
        create_resp = client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test", "topic": "Architecture review"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session"]["id"]

        # Send message
        msg_resp = client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Review the current architecture"},
        )
        assert msg_resp.status_code == 202

        # Verify usage is persisted
        get_resp = client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()

        # Find assistant message
        messages_data = data["messages"]
        assistant_msg = next(
            (m for m in messages_data if m["role"] == "assistant"), None
        )
        assert assistant_msg is not None

        # Verify usage data
        assert assistant_msg["usage"] is not None
        assert assistant_msg["usage"]["input_tokens"] == 1500
        assert assistant_msg["usage"]["output_tokens"] == 800
        assert assistant_msg["usage"]["cost_usd"] == 0.05

    def test_message_without_usage_has_null_usage(
        self,
        test_brainstorm_service: BrainstormService,
        tmp_path: Path,
    ) -> None:
        """Message from driver without usage should have null usage field."""
        # Create driver that returns no usage
        messages = [
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Quick response without usage tracking.",
                session_id="driver-session-no-usage",
            ),
        ]
        mock_driver = create_mock_driver_with_usage(messages, usage=None)
        client = create_test_client(test_brainstorm_service, mock_driver, tmp_path)

        # Create session and send message
        create_resp = client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session"]["id"]

        msg_resp = client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Hello"},
        )
        assert msg_resp.status_code == 202

        # Verify message is saved with null usage
        get_resp = client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()

        assistant_msg = next(
            (m for m in data["messages"] if m["role"] == "assistant"), None
        )
        assert assistant_msg is not None
        assert assistant_msg["usage"] is None


@pytest.mark.integration
class TestSessionUsageSummary:
    """Test session-level usage aggregation."""

    def test_session_usage_summary_aggregates_across_messages(
        self,
        test_brainstorm_service: BrainstormService,
        tmp_path: Path,
    ) -> None:
        """Usage summary should correctly total usage from multiple messages."""
        # Create driver for first message
        messages1 = [
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="First response.",
                session_id="driver-session-1",
            ),
        ]
        usage1 = DriverUsage(
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.03,
        )
        mock_driver1 = create_mock_driver_with_usage(messages1, usage1)
        client1 = create_test_client(test_brainstorm_service, mock_driver1, tmp_path)

        # Create session
        create_resp = client1.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test", "topic": "Multi-turn conversation"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session"]["id"]

        # Send first message
        msg_resp1 = client1.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "First question"},
        )
        assert msg_resp1.status_code == 202

        # Reconfigure driver for second message with different usage
        messages2 = [
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Second response.",
                session_id="driver-session-1",
            ),
        ]
        usage2 = DriverUsage(
            input_tokens=2000,
            output_tokens=1000,
            cost_usd=0.07,
        )
        mock_driver2 = create_mock_driver_with_usage(messages2, usage2)
        client2 = create_test_client(test_brainstorm_service, mock_driver2, tmp_path)

        # Send second message
        msg_resp2 = client2.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Second question"},
        )
        assert msg_resp2.status_code == 202

        # Verify individual messages have their own usage
        get_resp = client2.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()

        assistant_msgs = [m for m in data["messages"] if m["role"] == "assistant"]
        assert len(assistant_msgs) == 2

        # First assistant message (seq=2)
        assert assistant_msgs[0]["usage"]["input_tokens"] == 1000
        assert assistant_msgs[0]["usage"]["output_tokens"] == 500
        assert assistant_msgs[0]["usage"]["cost_usd"] == 0.03

        # Second assistant message (seq=4)
        assert assistant_msgs[1]["usage"]["input_tokens"] == 2000
        assert assistant_msgs[1]["usage"]["output_tokens"] == 1000
        assert assistant_msgs[1]["usage"]["cost_usd"] == 0.07

        # Verify session usage summary is aggregated
        session = data["session"]
        assert session["usage_summary"] is not None
        usage_summary = session["usage_summary"]
        assert usage_summary["total_input_tokens"] == 3000  # 1000 + 2000
        assert usage_summary["total_output_tokens"] == 1500  # 500 + 1000
        assert usage_summary["total_cost_usd"] == pytest.approx(0.10)  # 0.03 + 0.07
        assert usage_summary["message_count"] == 2

    def test_session_without_usage_messages_has_null_summary(
        self,
        test_brainstorm_service: BrainstormService,
        tmp_path: Path,
    ) -> None:
        """Session with no messages having usage should have null usage_summary."""
        # Create driver that returns no usage
        messages = [
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Response without usage.",
            ),
        ]
        mock_driver = create_mock_driver_with_usage(messages, usage=None)
        client = create_test_client(test_brainstorm_service, mock_driver, tmp_path)

        # Create session and send message (which will have null usage)
        create_resp = client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session"]["id"]

        msg_resp = client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Test"},
        )
        assert msg_resp.status_code == 202

        # Verify usage_summary is null (not 0 or empty object)
        get_resp = client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()

        session = data["session"]
        assert session["usage_summary"] is None

    def test_new_session_has_null_usage_summary(
        self,
        test_brainstorm_service: BrainstormService,
        tmp_path: Path,
    ) -> None:
        """Newly created session with no messages should have null usage_summary."""
        messages = [
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Response.",
            ),
        ]
        mock_driver = create_mock_driver_with_usage(messages, usage=None)
        client = create_test_client(test_brainstorm_service, mock_driver, tmp_path)

        # Create session without sending any messages
        create_resp = client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session"]["id"]

        # Verify usage_summary is null for session with no messages
        get_resp = client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()

        assert data["session"]["usage_summary"] is None
        assert len(data["messages"]) == 0


@pytest.mark.integration
class TestUsageWithPartialData:
    """Test edge cases where driver returns partial usage data."""

    def test_usage_with_zero_values_persists_correctly(
        self,
        test_brainstorm_service: BrainstormService,
        tmp_path: Path,
    ) -> None:
        """Usage with zero values should be saved, not treated as null."""
        messages = [
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Response.",
            ),
        ]
        # DriverUsage with explicit zeros
        usage = DriverUsage(
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
        )
        mock_driver = create_mock_driver_with_usage(messages, usage)
        client = create_test_client(test_brainstorm_service, mock_driver, tmp_path)

        # Create session and send message
        create_resp = client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session"]["id"]

        msg_resp = client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Test"},
        )
        assert msg_resp.status_code == 202

        # Verify usage is saved (not null) with zero values
        get_resp = client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()

        assistant_msg = next(
            (m for m in data["messages"] if m["role"] == "assistant"), None
        )
        assert assistant_msg is not None
        # Zero input_tokens should result in saved usage (MessageUsage created)
        assert assistant_msg["usage"] is not None
        assert assistant_msg["usage"]["input_tokens"] == 0
        assert assistant_msg["usage"]["output_tokens"] == 0
        assert assistant_msg["usage"]["cost_usd"] == 0.0

    def test_usage_with_none_fields_defaults_to_zero(
        self,
        test_brainstorm_service: BrainstormService,
        tmp_path: Path,
    ) -> None:
        """DriverUsage with None fields should default to 0 in MessageUsage."""
        messages = [
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Response.",
            ),
        ]
        # DriverUsage with None fields (some drivers may not provide all fields)
        usage = DriverUsage(
            input_tokens=100,
            output_tokens=None,  # Not provided
            cost_usd=None,  # Not provided
        )
        mock_driver = create_mock_driver_with_usage(messages, usage)
        client = create_test_client(test_brainstorm_service, mock_driver, tmp_path)

        # Create session and send message
        create_resp = client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session"]["id"]

        msg_resp = client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Test"},
        )
        assert msg_resp.status_code == 202

        # Verify None fields default to 0
        get_resp = client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()

        assistant_msg = next(
            (m for m in data["messages"] if m["role"] == "assistant"), None
        )
        assert assistant_msg is not None
        assert assistant_msg["usage"]["input_tokens"] == 100
        assert assistant_msg["usage"]["output_tokens"] == 0  # Defaulted from None
        assert assistant_msg["usage"]["cost_usd"] == 0.0  # Defaulted from None
