"""Integration tests for brainstorm message sequence integrity.

Tests that multiple messages in a session maintain correct sequence numbers
and message ordering.

Real components:
- FastAPI route handlers
- BrainstormService
- BrainstormRepository with PostgreSQL test database

Only mocked:
- Driver (execute_agentic as async generator)

Uses httpx.AsyncClient with ASGITransport to keep the ASGI app in the
same event loop as the asyncpg pool (TestClient creates a separate thread
with its own event loop, causing asyncpg event loop mismatches).
"""

from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverInterface
from amelia.server.services.brainstorm import BrainstormService
from tests.conftest import create_mock_execute_agentic

from .conftest import AsyncClientFactory, _create_app_with_overrides


# =============================================================================
# Fixtures
# =============================================================================


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
async def test_client(
    test_brainstorm_service: BrainstormService,
    mock_driver_factory: Callable[[], MagicMock],
    tmp_path: Path,
    async_client_factory: AsyncClientFactory,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create async test client that returns a new mock driver for each request.

    Uses httpx.AsyncClient with ASGITransport so the ASGI app runs in the
    same event loop as the asyncpg pool created by test_db.
    """
    app = _create_app_with_overrides(
        test_brainstorm_service, mock_driver_factory, str(tmp_path)
    )

    async with async_client_factory(app) as client:
        yield client


# =============================================================================
# Test Classes
# =============================================================================


@pytest.mark.integration
class TestMultiMessageSequence:
    """Test that multiple messages maintain correct sequence numbers."""

    async def test_three_messages_have_correct_sequences(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Sending 3 messages should produce user/assistant pairs with seq 1-6."""
        # Create session
        create_resp = await test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test", "topic": "Multi-turn conversation"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session"]["id"]

        # Send 3 messages sequentially
        for i in range(1, 4):
            msg_resp = await test_client.post(
                f"/api/brainstorm/sessions/{session_id}/message",
                json={"content": f"Message {i}"},
            )
            assert msg_resp.status_code == 202

        # Get session and verify all messages
        get_resp = await test_client.get(f"/api/brainstorm/sessions/{session_id}")
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

    async def test_messages_ordered_by_sequence(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Messages should be returned in sequence order."""
        # Create session
        create_resp = await test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["session"]["id"]

        # Send 2 messages
        await test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "First"},
        )
        await test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Second"},
        )

        # Get session
        get_resp = await test_client.get(f"/api/brainstorm/sessions/{session_id}")
        messages = get_resp.json()["messages"]

        # Verify messages are in order
        sequences = [m["sequence"] for m in messages]
        assert sequences == sorted(sequences), "Messages not in sequence order"
        assert sequences == [1, 2, 3, 4], f"Unexpected sequences: {sequences}"

    async def test_user_messages_have_odd_sequences(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """User messages should have odd sequence numbers (1, 3, 5)."""
        # Create session and send 3 messages
        create_resp = await test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["session"]["id"]

        for i in range(3):
            await test_client.post(
                f"/api/brainstorm/sessions/{session_id}/message",
                json={"content": f"User message {i+1}"},
            )

        # Get session
        get_resp = await test_client.get(f"/api/brainstorm/sessions/{session_id}")
        messages = get_resp.json()["messages"]

        user_messages = [m for m in messages if m["role"] == "user"]
        user_sequences = [m["sequence"] for m in user_messages]
        assert user_sequences == [1, 3, 5], f"User sequences wrong: {user_sequences}"

    async def test_assistant_messages_have_even_sequences(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Assistant messages should have even sequence numbers (2, 4, 6)."""
        # Create session and send 3 messages
        create_resp = await test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["session"]["id"]

        for i in range(3):
            await test_client.post(
                f"/api/brainstorm/sessions/{session_id}/message",
                json={"content": f"User message {i+1}"},
            )

        # Get session
        get_resp = await test_client.get(f"/api/brainstorm/sessions/{session_id}")
        messages = get_resp.json()["messages"]

        assistant_messages = [m for m in messages if m["role"] == "assistant"]
        assistant_sequences = [m["sequence"] for m in assistant_messages]
        assert assistant_sequences == [2, 4, 6], (
            f"Assistant sequences wrong: {assistant_sequences}"
        )

    async def test_conversation_continuity_across_messages(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Verify that session maintains driver_session_id across messages."""
        # Create session
        create_resp = await test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["session"]["id"]

        # Initially no driver_session_id
        get_resp = await test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.json()["session"]["driver_session_id"] is None

        # Send first message
        await test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "First message"},
        )

        # driver_session_id should be set after first message
        get_resp = await test_client.get(f"/api/brainstorm/sessions/{session_id}")
        driver_session_id = get_resp.json()["session"]["driver_session_id"]
        assert driver_session_id is not None

        # Send second message
        await test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Second message"},
        )

        # driver_session_id should remain the same
        get_resp = await test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.json()["session"]["driver_session_id"] == driver_session_id


@pytest.mark.integration
class TestSequenceEdgeCases:
    """Test edge cases in message sequencing."""

    async def test_single_message_sequence(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Single message should produce user=1, assistant=2."""
        # Create session and send one message
        create_resp = await test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["session"]["id"]

        await test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Only message"},
        )

        # Get session
        get_resp = await test_client.get(f"/api/brainstorm/sessions/{session_id}")
        messages = get_resp.json()["messages"]

        assert len(messages) == 2
        assert messages[0]["sequence"] == 1
        assert messages[0]["role"] == "user"
        assert messages[1]["sequence"] == 2
        assert messages[1]["role"] == "assistant"

    async def test_empty_session_has_no_messages(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """New session should have no messages."""
        # Create session but don't send any messages
        create_resp = await test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["session"]["id"]

        # Get session
        get_resp = await test_client.get(f"/api/brainstorm/sessions/{session_id}")
        messages = get_resp.json()["messages"]

        assert messages == []
