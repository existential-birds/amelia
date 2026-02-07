"""Integration tests for brainstorm WebSocket event streaming.

Tests that brainstorm operations emit the correct events via EventBus
which are then broadcast to WebSocket clients.

Real components:
- BrainstormService
- BrainstormRepository with PostgreSQL test database
- EventBus (with subscriber to capture events)
- ConnectionManager (for full WebSocket tests)

Only mocked:
- Driver (execute_agentic as async generator)
"""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverInterface
from amelia.server.database.brainstorm_repository import BrainstormRepository
from amelia.server.database.connection import Database
from amelia.server.database.migrator import Migrator
from amelia.server.database.profile_repository import ProfileRepository
from amelia.server.dependencies import get_profile_repository
from amelia.server.events.bus import EventBus
from amelia.server.events.connection_manager import ConnectionManager
from amelia.server.main import create_app
from amelia.server.models.events import EventDomain, EventType, WorkflowEvent
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
def test_profile_repository(test_db: Database) -> ProfileRepository:
    """Create profile repository backed by test database."""
    return ProfileRepository(test_db)


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
    test_profile_repository: ProfileRepository,
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
    app.dependency_overrides[get_profile_repository] = lambda: test_profile_repository
    app.dependency_overrides[get_driver] = lambda: mock_driver
    app.dependency_overrides[get_cwd] = lambda: str(tmp_path)

    return TestClient(app)


# =============================================================================
# Helper Functions
# =============================================================================


def create_session_and_send_message(
    client: TestClient,
    message: str = "Test message",
) -> str:
    """Create a brainstorm session and send a message.

    Args:
        client: The test client to use.
        message: The message content to send.

    Returns:
        The session ID.
    """
    create_resp = client.post(
        "/api/brainstorm/sessions",
        json={"profile_id": "test"},
    )
    assert create_resp.status_code == 201, f"Failed to create session: {create_resp.json()}"
    session_id = create_resp.json()["session"]["id"]

    msg_resp = client.post(
        f"/api/brainstorm/sessions/{session_id}/message",
        json={"content": message},
    )
    assert msg_resp.status_code == 202, f"Failed to send message: {msg_resp.json()}"

    return session_id


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
        create_session_and_send_message(test_client)

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
        create_session_and_send_message(test_client)

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
        create_session_and_send_message(test_client)

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
        create_session_and_send_message(test_client)

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
        create_session_and_send_message(test_client)

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
        session_id = create_session_and_send_message(test_client)

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
        test_profile_repository: ProfileRepository,
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
        app.dependency_overrides[get_profile_repository] = (
            lambda: test_profile_repository
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
        session_id = create_session_and_send_message(
            test_client_with_write_file, message="Create design doc"
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
        assert "id" in event.data


@pytest.mark.integration
class TestBrainstormWebSocketBroadcast:
    """Test that events are broadcast to WebSocket clients."""

    @pytest.fixture
    def websocket_app(
        self,
        test_brainstorm_service: BrainstormService,
        test_profile_repository: ProfileRepository,
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
        app.dependency_overrides[get_profile_repository] = (
            lambda: test_profile_repository
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

    async def test_event_bus_connection_manager_wiring(
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
        create_session_and_send_message(websocket_app, message="Hello")

        # Wait for any pending broadcasts to complete
        await test_event_bus.wait_for_broadcasts()

        # If we get here without errors, the wiring is correct
        # Actual event delivery is verified by the event emission tests


@pytest.mark.integration
class TestBrainstormEventDataField:
    """Test that BrainstormService emits events with correct data for wire format.

    These tests verify that _agentic_message_to_event includes session_id and
    message_id in the data field, which is required for the WebSocket wire format.
    """

    @pytest.mark.parametrize(
        "event_type",
        [EventType.BRAINSTORM_TEXT, EventType.BRAINSTORM_REASONING],
    )
    def test_event_has_session_id_in_data(
        self,
        test_client: TestClient,
        captured_events: list[WorkflowEvent],
        event_type: EventType,
    ) -> None:
        """Brainstorm events must have session_id in data for wire format."""
        session_id = create_session_and_send_message(test_client)

        # Find events of the specified type
        matching_events = [
            e for e in captured_events
            if e.event_type == event_type
        ]
        assert len(matching_events) >= 1

        # Verify wire format data is present
        event = matching_events[0]
        assert event.data is not None, "Event data field must not be None"
        assert "session_id" in event.data, "Event must have session_id in data"
        assert event.data["session_id"] == session_id

    def test_message_complete_event_has_session_id_and_message_id(
        self,
        test_client: TestClient,
        captured_events: list[WorkflowEvent],
    ) -> None:
        """BRAINSTORM_MESSAGE_COMPLETE must have session_id and message_id in data."""
        session_id = create_session_and_send_message(test_client)

        # Find complete event
        complete_events = [
            e for e in captured_events
            if e.event_type == EventType.BRAINSTORM_MESSAGE_COMPLETE
        ]
        assert len(complete_events) == 1

        # Verify wire format data is present
        event = complete_events[0]
        assert event.data is not None, "Event data field must not be None"
        assert "session_id" in event.data, "Event must have session_id in data"
        assert event.data["session_id"] == session_id
        assert "message_id" in event.data, "Event must have message_id in data"


@pytest.mark.integration
class TestBrainstormWireFormat:
    """Test that brainstorm events use the dedicated wire format over WebSocket."""

    @pytest.fixture
    def mock_websocket(self) -> AsyncMock:
        """Create a mock WebSocket connection."""
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        return ws

    @pytest.fixture
    def connection_manager(self) -> ConnectionManager:
        """Create a ConnectionManager instance."""
        return ConnectionManager()

    async def test_brainstorm_events_use_dedicated_wire_format(
        self,
        connection_manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Brainstorm domain events arrive with type='brainstorm' over WebSocket."""
        # Connect and subscribe
        await connection_manager.connect(mock_websocket)
        await connection_manager.subscribe_all(mock_websocket)

        # Create a brainstorm event
        event = WorkflowEvent(
            id=str(uuid4()),
            workflow_id="session-123",
            sequence=0,
            timestamp=datetime.now(UTC),
            agent="brainstormer",
            event_type=EventType.BRAINSTORM_TEXT,
            message="Streaming text",
            domain=EventDomain.BRAINSTORM,
            data={
                "session_id": "session-123",
                "message_id": "msg-1",
                "text": "Hello world",
            },
        )

        # Broadcast the event
        await connection_manager.broadcast(event)

        # Verify the wire format
        mock_websocket.send_json.assert_called_once()
        payload = mock_websocket.send_json.call_args[0][0]

        assert payload["type"] == "brainstorm"
        assert payload["event_type"] == "text"  # brainstorm_ prefix stripped
        assert payload["session_id"] == "session-123"
        assert payload["message_id"] == "msg-1"
        assert payload["data"]["text"] == "Hello world"
        assert "timestamp" in payload

    async def test_workflow_events_use_event_wrapper(
        self,
        connection_manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Workflow domain events use the standard {type: 'event', payload: ...} format."""
        await connection_manager.connect(mock_websocket)
        await connection_manager.subscribe_all(mock_websocket)

        event = WorkflowEvent(
            id=str(uuid4()),
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
            domain=EventDomain.WORKFLOW,
        )

        await connection_manager.broadcast(event)

        mock_websocket.send_json.assert_called_once()
        payload = mock_websocket.send_json.call_args[0][0]

        assert payload["type"] == "event"
        assert "payload" in payload
        assert payload["payload"]["id"] == event.id

    async def test_brainstorm_message_complete_event(
        self,
        connection_manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Message complete events are correctly routed with error data if present."""
        await connection_manager.connect(mock_websocket)
        await connection_manager.subscribe_all(mock_websocket)

        event = WorkflowEvent(
            id=str(uuid4()),
            workflow_id="session-123",
            sequence=0,
            timestamp=datetime.now(UTC),
            agent="brainstormer",
            event_type=EventType.BRAINSTORM_MESSAGE_COMPLETE,
            message="Complete",
            domain=EventDomain.BRAINSTORM,
            data={
                "session_id": "session-123",
                "message_id": "msg-1",
                "error": "Connection failed",
            },
        )

        await connection_manager.broadcast(event)

        payload = mock_websocket.send_json.call_args[0][0]

        assert payload["type"] == "brainstorm"
        assert payload["event_type"] == "message_complete"
        assert payload["data"]["error"] == "Connection failed"
