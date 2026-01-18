"""Integration tests for brainstorm message sequence integrity.

Tests that multiple messages in a session maintain correct sequence numbers
and message ordering.

Real components:
- FastAPI route handlers
- BrainstormService
- BrainstormRepository with in-memory SQLite

Only mocked:
- Driver (execute_agentic as async generator)
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverInterface
from amelia.server.database.brainstorm_repository import BrainstormRepository
from amelia.server.database.connection import Database
from amelia.server.events.bus import EventBus
from amelia.server.main import create_app
from amelia.server.routes.brainstorm import (
    get_brainstorm_service,
    get_cwd,
    get_driver,
)
from amelia.server.services.brainstorm import BrainstormService
from tests.conftest import create_mock_execute_agentic


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def test_db(temp_db_path: Path) -> AsyncGenerator[Database, None]:
    """Create and initialize in-memory SQLite database."""
    db = Database(temp_db_path)
    await db.connect()
    await db.ensure_schema()
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


def create_simple_driver_response(
    response_content: str,
    session_id: str = "driver-session",
) -> list[AgenticMessage]:
    """Create a simple driver response sequence."""
    return [
        AgenticMessage(
            type=AgenticMessageType.RESULT,
            content=response_content,
            session_id=session_id,
        ),
    ]


@pytest.fixture
def mock_driver_factory() -> Callable[[], MagicMock]:
    """Factory to create mock drivers with specific responses."""
    call_count = [0]  # Use list for mutation in closure

    def _create() -> MagicMock:
        call_count[0] += 1
        driver = MagicMock(spec=DriverInterface)
        messages = create_simple_driver_response(
            response_content=f"Response #{call_count[0]}",
            session_id="driver-session",
        )
        driver.execute_agentic = create_mock_execute_agentic(messages)
        return driver

    return _create


@pytest.fixture
def test_client(
    test_brainstorm_service: BrainstormService,
    mock_driver_factory: Callable[[], MagicMock],
    tmp_path: Path,
) -> TestClient:
    """Create test client that returns a new mock driver for each request."""
    app = create_app()

    @asynccontextmanager
    async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
        yield

    app.router.lifespan_context = noop_lifespan
    app.dependency_overrides[get_brainstorm_service] = lambda: test_brainstorm_service
    app.dependency_overrides[get_driver] = mock_driver_factory
    app.dependency_overrides[get_cwd] = lambda: str(tmp_path)

    return TestClient(app)


# =============================================================================
# Test Classes
# =============================================================================


@pytest.mark.integration
class TestMultiMessageSequence:
    """Test that multiple messages maintain correct sequence numbers."""

    def test_three_messages_have_correct_sequences(
        self,
        test_client: TestClient,
    ) -> None:
        """Sending 3 messages should produce user/assistant pairs with seq 1-6."""
        # Create session
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test", "topic": "Multi-turn conversation"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["id"]

        # Send 3 messages sequentially
        for i in range(1, 4):
            msg_resp = test_client.post(
                f"/api/brainstorm/sessions/{session_id}/message",
                json={"content": f"Message {i}"},
            )
            assert msg_resp.status_code == 202

        # Get session and verify all messages
        get_resp = test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.status_code == 200
        messages = get_resp.json()["messages"]

        # Should have 6 messages: 3 user + 3 assistant
        assert len(messages) == 6

        # Verify sequences are correct
        expected = [
            (1, "user", "Message 1"),
            (2, "assistant", "Response #1"),
            (3, "user", "Message 2"),
            (4, "assistant", "Response #2"),
            (5, "user", "Message 3"),
            (6, "assistant", "Response #3"),
        ]

        for i, (expected_seq, expected_role, expected_content) in enumerate(expected):
            msg = messages[i]
            assert msg["sequence"] == expected_seq, (
                f"Message {i} has wrong sequence: expected {expected_seq}, got {msg['sequence']}"
            )
            assert msg["role"] == expected_role, (
                f"Message {i} has wrong role: expected {expected_role}, got {msg['role']}"
            )
            assert expected_content in msg["content"], (
                f"Message {i} missing expected content '{expected_content}'"
            )

    def test_messages_ordered_by_sequence(
        self,
        test_client: TestClient,
    ) -> None:
        """Messages should be returned in sequence order."""
        # Create session
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["id"]

        # Send 2 messages
        test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "First"},
        )
        test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Second"},
        )

        # Get session
        get_resp = test_client.get(f"/api/brainstorm/sessions/{session_id}")
        messages = get_resp.json()["messages"]

        # Verify messages are in order
        sequences = [m["sequence"] for m in messages]
        assert sequences == sorted(sequences), "Messages not in sequence order"
        assert sequences == [1, 2, 3, 4], f"Unexpected sequences: {sequences}"

    def test_user_messages_have_odd_sequences(
        self,
        test_client: TestClient,
    ) -> None:
        """User messages should have odd sequence numbers (1, 3, 5)."""
        # Create session and send 3 messages
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["id"]

        for i in range(3):
            test_client.post(
                f"/api/brainstorm/sessions/{session_id}/message",
                json={"content": f"User message {i+1}"},
            )

        # Get session
        get_resp = test_client.get(f"/api/brainstorm/sessions/{session_id}")
        messages = get_resp.json()["messages"]

        user_messages = [m for m in messages if m["role"] == "user"]
        user_sequences = [m["sequence"] for m in user_messages]
        assert user_sequences == [1, 3, 5], f"User sequences wrong: {user_sequences}"

    def test_assistant_messages_have_even_sequences(
        self,
        test_client: TestClient,
    ) -> None:
        """Assistant messages should have even sequence numbers (2, 4, 6)."""
        # Create session and send 3 messages
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["id"]

        for i in range(3):
            test_client.post(
                f"/api/brainstorm/sessions/{session_id}/message",
                json={"content": f"User message {i+1}"},
            )

        # Get session
        get_resp = test_client.get(f"/api/brainstorm/sessions/{session_id}")
        messages = get_resp.json()["messages"]

        assistant_messages = [m for m in messages if m["role"] == "assistant"]
        assistant_sequences = [m["sequence"] for m in assistant_messages]
        assert assistant_sequences == [2, 4, 6], (
            f"Assistant sequences wrong: {assistant_sequences}"
        )

    def test_conversation_continuity_across_messages(
        self,
        test_client: TestClient,
    ) -> None:
        """Verify that session maintains driver_session_id across messages."""
        # Create session
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["id"]

        # Initially no driver_session_id
        get_resp = test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.json()["session"]["driver_session_id"] is None

        # Send first message
        test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "First message"},
        )

        # driver_session_id should be set after first message
        get_resp = test_client.get(f"/api/brainstorm/sessions/{session_id}")
        driver_session_id = get_resp.json()["session"]["driver_session_id"]
        assert driver_session_id is not None

        # Send second message
        test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Second message"},
        )

        # driver_session_id should remain the same
        get_resp = test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.json()["session"]["driver_session_id"] == driver_session_id


@pytest.mark.integration
class TestSequenceEdgeCases:
    """Test edge cases in message sequencing."""

    def test_single_message_sequence(
        self,
        test_client: TestClient,
    ) -> None:
        """Single message should produce user=1, assistant=2."""
        # Create session and send one message
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["id"]

        test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Only message"},
        )

        # Get session
        get_resp = test_client.get(f"/api/brainstorm/sessions/{session_id}")
        messages = get_resp.json()["messages"]

        assert len(messages) == 2
        assert messages[0]["sequence"] == 1
        assert messages[0]["role"] == "user"
        assert messages[1]["sequence"] == 2
        assert messages[1]["role"] == "assistant"

    def test_empty_session_has_no_messages(
        self,
        test_client: TestClient,
    ) -> None:
        """New session should have no messages."""
        # Create session but don't send any messages
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["id"]

        # Get session
        get_resp = test_client.get(f"/api/brainstorm/sessions/{session_id}")
        messages = get_resp.json()["messages"]

        assert messages == []
