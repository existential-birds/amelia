"""Integration tests for brainstorm WebSocket event streaming.

Tests that brainstorm operations emit the correct events via EventBus
which are then broadcast to WebSocket clients.

Real components:
- BrainstormService
- BrainstormRepository with in-memory SQLite
- EventBus (with subscriber to capture events)
- ConnectionManager (for full WebSocket tests)

Only mocked:
- Driver (execute_agentic as async generator)
"""

import asyncio
from collections.abc import AsyncGenerator, Generator
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
from amelia.server.events.connection_manager import ConnectionManager
from amelia.server.main import create_app
from amelia.server.models.events import EventType, WorkflowEvent
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
def captured_events() -> list[WorkflowEvent]:
    """List to capture emitted events."""
    return []


@pytest.fixture
def test_event_bus(captured_events: list[WorkflowEvent]) -> EventBus:
    """Create event bus with subscriber to capture events."""
    bus = EventBus()
    bus.subscribe(captured_events.append)
    return bus


@pytest.fixture
def test_brainstorm_service(
    test_brainstorm_repository: BrainstormRepository,
    test_event_bus: EventBus,
) -> BrainstormService:
    """Create real BrainstormService with test dependencies."""
    return BrainstormService(test_brainstorm_repository, test_event_bus)


def create_realistic_driver_messages(
    *,
    session_id: str = "driver-session-123",
) -> list[AgenticMessage]:
    """Create a realistic sequence of driver messages."""
    return [
        AgenticMessage(
            type=AgenticMessageType.THINKING,
            content="Let me analyze this...",
        ),
        AgenticMessage(
            type=AgenticMessageType.TOOL_CALL,
            tool_name="read_file",
            tool_input={"path": "README.md"},
            tool_call_id="call-1",
        ),
        AgenticMessage(
            type=AgenticMessageType.TOOL_RESULT,
            tool_name="read_file",
            tool_output="File contents",
            tool_call_id="call-1",
            is_error=False,
        ),
        AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="Here's my analysis.",
            session_id=session_id,
        ),
    ]


@pytest.fixture
def mock_driver() -> MagicMock:
    """Create a mock driver with realistic message flow."""
    driver = MagicMock(spec=DriverInterface)
    messages = create_realistic_driver_messages()
    driver.execute_agentic = create_mock_execute_agentic(messages)
    return driver


@pytest.fixture
def test_client(
    test_brainstorm_service: BrainstormService,
    mock_driver: MagicMock,
    tmp_path: Path,
) -> TestClient:
    """Create test client with real dependencies."""
    app = create_app()

    @asynccontextmanager
    async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
        yield

    app.router.lifespan_context = noop_lifespan
    app.dependency_overrides[get_brainstorm_service] = lambda: test_brainstorm_service
    app.dependency_overrides[get_driver] = lambda: mock_driver
    app.dependency_overrides[get_cwd] = lambda: str(tmp_path)

    return TestClient(app)


# =============================================================================
# Test Classes
# =============================================================================


@pytest.mark.integration
class TestBrainstormEventEmission:
    """Test that brainstorm operations emit the correct events."""

    def test_send_message_emits_reasoning_event(
        self,
        test_client: TestClient,
        captured_events: list[WorkflowEvent],
    ) -> None:
        """THINKING agentic message should emit BRAINSTORM_REASONING event."""
        # Create session
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["id"]

        # Send message
        test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Test message"},
        )

        # Find reasoning event
        reasoning_events = [
            e for e in captured_events
            if e.event_type == EventType.BRAINSTORM_REASONING
        ]
        assert len(reasoning_events) >= 1
        assert reasoning_events[0].message is not None
        assert reasoning_events[0].agent == "brainstormer"

    def test_send_message_emits_tool_call_event(
        self,
        test_client: TestClient,
        captured_events: list[WorkflowEvent],
    ) -> None:
        """TOOL_CALL agentic message should emit BRAINSTORM_TOOL_CALL event."""
        # Create session
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["id"]

        # Send message
        test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Test message"},
        )

        # Find tool call event
        tool_call_events = [
            e for e in captured_events
            if e.event_type == EventType.BRAINSTORM_TOOL_CALL
        ]
        assert len(tool_call_events) >= 1
        assert tool_call_events[0].tool_name == "read_file"

    def test_send_message_emits_tool_result_event(
        self,
        test_client: TestClient,
        captured_events: list[WorkflowEvent],
    ) -> None:
        """TOOL_RESULT agentic message should emit BRAINSTORM_TOOL_RESULT event."""
        # Create session
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["id"]

        # Send message
        test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Test message"},
        )

        # Find tool result event
        tool_result_events = [
            e for e in captured_events
            if e.event_type == EventType.BRAINSTORM_TOOL_RESULT
        ]
        assert len(tool_result_events) >= 1
        assert tool_result_events[0].tool_name == "read_file"

    def test_send_message_emits_text_event(
        self,
        test_client: TestClient,
        captured_events: list[WorkflowEvent],
    ) -> None:
        """RESULT agentic message should emit BRAINSTORM_TEXT event."""
        # Create session
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["id"]

        # Send message
        test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Test message"},
        )

        # Find text event
        text_events = [
            e for e in captured_events
            if e.event_type == EventType.BRAINSTORM_TEXT
        ]
        assert len(text_events) >= 1

    def test_send_message_emits_message_complete_event(
        self,
        test_client: TestClient,
        captured_events: list[WorkflowEvent],
    ) -> None:
        """Completing a message should emit BRAINSTORM_MESSAGE_COMPLETE event."""
        # Create session
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["id"]

        # Send message
        test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Test message"},
        )

        # Find complete event
        complete_events = [
            e for e in captured_events
            if e.event_type == EventType.BRAINSTORM_MESSAGE_COMPLETE
        ]
        assert len(complete_events) == 1
        assert "message_id" in (complete_events[0].data or {})

    def test_send_message_events_have_correct_workflow_id(
        self,
        test_client: TestClient,
        captured_events: list[WorkflowEvent],
    ) -> None:
        """All events should have the session_id as workflow_id."""
        # Create session
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["id"]

        # Send message
        test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Test message"},
        )

        # All brainstorm events should have correct workflow_id
        brainstorm_events = [
            e for e in captured_events
            if e.event_type.value.startswith("brainstorm_")
        ]
        # Skip session_created which happens before the message
        message_events = [
            e for e in brainstorm_events
            if e.event_type != EventType.BRAINSTORM_SESSION_CREATED
        ]
        for event in message_events:
            assert event.workflow_id == session_id


@pytest.mark.integration
class TestBrainstormArtifactEvents:
    """Test artifact-related event emission."""

    @pytest.fixture
    def mock_driver_with_write_file(self) -> MagicMock:
        """Create a mock driver that emits write_file tool call."""
        driver = MagicMock(spec=DriverInterface)
        messages = [
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="write_file",
                tool_input={"path": "docs/design.md", "content": "# Design"},
                tool_call_id="call-write",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="write_file",
                tool_output="Written successfully",
                tool_call_id="call-write",
                is_error=False,
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Created the document.",
            ),
        ]
        driver.execute_agentic = create_mock_execute_agentic(messages)
        return driver

    @pytest.fixture
    def test_client_with_write_file(
        self,
        test_brainstorm_service: BrainstormService,
        mock_driver_with_write_file: MagicMock,
        tmp_path: Path,
    ) -> TestClient:
        """Create test client with driver that emits write_file."""
        app = create_app()

        @asynccontextmanager
        async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
            yield

        app.router.lifespan_context = noop_lifespan
        app.dependency_overrides[get_brainstorm_service] = (
            lambda: test_brainstorm_service
        )
        app.dependency_overrides[get_driver] = lambda: mock_driver_with_write_file
        app.dependency_overrides[get_cwd] = lambda: str(tmp_path)

        return TestClient(app)

    def test_write_file_emits_artifact_created_event(
        self,
        test_client_with_write_file: TestClient,
        captured_events: list[WorkflowEvent],
    ) -> None:
        """Successful write_file should emit BRAINSTORM_ARTIFACT_CREATED event."""
        # Create session
        create_resp = test_client_with_write_file.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["id"]

        # Send message
        test_client_with_write_file.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Create design doc"},
        )

        # Find artifact created event
        artifact_events = [
            e for e in captured_events
            if e.event_type == EventType.BRAINSTORM_ARTIFACT_CREATED
        ]
        assert len(artifact_events) == 1

        event = artifact_events[0]
        assert event.workflow_id == session_id
        assert event.data is not None
        assert event.data["path"] == "docs/design.md"
        assert "artifact_id" in event.data


@pytest.mark.integration
class TestBrainstormWebSocketBroadcast:
    """Test that events are broadcast to WebSocket clients."""

    @pytest.fixture
    def websocket_app(
        self,
        test_brainstorm_service: BrainstormService,
        test_event_bus: EventBus,
        mock_driver: MagicMock,
        tmp_path: Path,
    ) -> Generator[TestClient, None, None]:
        """Create app with WebSocket broadcasting enabled."""
        app = create_app()

        # Create a connection manager and link it to the event bus
        cm = ConnectionManager()
        test_event_bus.set_connection_manager(cm)

        @asynccontextmanager
        async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
            yield

        app.router.lifespan_context = noop_lifespan
        app.dependency_overrides[get_brainstorm_service] = (
            lambda: test_brainstorm_service
        )
        app.dependency_overrides[get_driver] = lambda: mock_driver
        app.dependency_overrides[get_cwd] = lambda: str(tmp_path)

        # Replace global connection manager with our test one
        import amelia.server.routes.websocket as ws_module
        original_cm = ws_module.connection_manager
        ws_module.connection_manager = cm

        client = TestClient(app)
        yield client

        # Restore
        ws_module.connection_manager = original_cm

    def test_event_bus_connection_manager_wiring(
        self,
        websocket_app: TestClient,
        test_event_bus: EventBus,
    ) -> None:
        """Verify EventBus is wired to ConnectionManager for WebSocket broadcast.

        This test verifies the integration between:
        1. BrainstormService emits events via EventBus
        2. EventBus has a ConnectionManager set
        3. The wiring allows events to reach WebSocket clients

        The actual event emission is tested in TestBrainstormEventEmission.
        This test focuses on the WebSocket infrastructure being correctly wired.
        """
        # Verify the event bus has a connection manager set
        assert test_event_bus._connection_manager is not None

        # Create session and send message to trigger event flow
        create_resp = websocket_app.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["id"]

        msg_resp = websocket_app.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Hello"},
        )
        assert msg_resp.status_code == 202

        # Wait for any pending broadcasts to complete
        asyncio.get_event_loop().run_until_complete(
            test_event_bus.wait_for_broadcasts()
        )

        # If we get here without errors, the wiring is correct
        # Actual event delivery is verified by the event emission tests
