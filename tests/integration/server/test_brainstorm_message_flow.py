"""Integration tests for brainstorm message flow.

Tests the full message flow with realistic driver behavior:
- Create session → send message → verify persistence
- Driver yields: THINKING → TOOL_CALL → TOOL_RESULT → RESULT
- Artifact detection from write_file tool calls

Real components:
- FastAPI route handlers
- BrainstormService
- BrainstormRepository with in-memory SQLite
- EventBus (without WebSocket connection manager)

Only mocked:
- Driver (execute_agentic as async generator)
"""

from collections.abc import AsyncGenerator
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


def create_realistic_driver_messages(
    *,
    thinking_content: str = "Let me analyze this request...",
    tool_name: str = "read_file",
    tool_input: dict[str, Any] | None = None,
    tool_output: str = "File contents here",
    result_content: str = "Based on my analysis, here's the answer.",
    session_id: str = "driver-session-123",
) -> list[AgenticMessage]:
    """Create a realistic sequence of driver messages.

    Returns:
        List of AgenticMessage objects simulating THINKING → TOOL_CALL → TOOL_RESULT → RESULT.
    """
    if tool_input is None:
        tool_input = {"path": "README.md"}

    return [
        AgenticMessage(
            type=AgenticMessageType.THINKING,
            content=thinking_content,
        ),
        AgenticMessage(
            type=AgenticMessageType.TOOL_CALL,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_call_id="call-1",
        ),
        AgenticMessage(
            type=AgenticMessageType.TOOL_RESULT,
            tool_name=tool_name,
            tool_output=tool_output,
            tool_call_id="call-1",
            is_error=False,
        ),
        AgenticMessage(
            type=AgenticMessageType.RESULT,
            content=result_content,
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
    """Create test client with real dependencies and mock driver."""
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
class TestBrainstormMessageFlow:
    """Test full message flow from HTTP request to persistence."""

    def test_send_message_persists_user_message(
        self,
        test_client: TestClient,
        test_brainstorm_repository: BrainstormRepository,
    ) -> None:
        """Sending a message should persist the user message with seq=1."""
        # Create session
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test", "topic": "API design"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["id"]

        # Send message
        msg_resp = test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "How should I structure the REST API?"},
        )
        assert msg_resp.status_code == 202

        # Verify user message is persisted
        get_resp = test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()

        messages = data["messages"]
        assert len(messages) >= 1
        user_msg = messages[0]
        assert user_msg["role"] == "user"
        assert user_msg["sequence"] == 1
        assert user_msg["content"] == "How should I structure the REST API?"

    def test_send_message_persists_assistant_message(
        self,
        test_client: TestClient,
    ) -> None:
        """Sending a message should persist the assistant response with seq=2."""
        # Create session
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test", "topic": "API design"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["id"]

        # Send message
        msg_resp = test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "How should I structure the REST API?"},
        )
        assert msg_resp.status_code == 202

        # Verify assistant message is persisted
        get_resp = test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()

        messages = data["messages"]
        assert len(messages) >= 2

        # Find assistant message
        assistant_msg = next((m for m in messages if m["role"] == "assistant"), None)
        assert assistant_msg is not None
        assert assistant_msg["sequence"] == 2
        assert "Based on my analysis" in assistant_msg["content"]

    def test_send_message_saves_driver_session_id(
        self,
        test_client: TestClient,
    ) -> None:
        """Sending a message should save the driver session ID for continuity."""
        # Create session
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["id"]

        # Initially no driver_session_id
        initial_resp = test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert initial_resp.status_code == 200
        assert initial_resp.json()["session"].get("driver_session_id") is None

        # Send message (mock driver returns session_id in RESULT message)
        msg_resp = test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Hello"},
        )
        assert msg_resp.status_code == 202

        # Verify driver_session_id is now saved
        final_resp = test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert final_resp.status_code == 200
        assert final_resp.json()["session"]["driver_session_id"] == "driver-session-123"


@pytest.mark.integration
class TestBrainstormArtifactDetection:
    """Test artifact creation from write_file tool calls."""

    @pytest.fixture
    def mock_driver_with_write_file(self, tmp_path: Path) -> MagicMock:
        """Create a mock driver that emits write_file tool call."""
        driver = MagicMock(spec=DriverInterface)
        artifact_path = "docs/plans/test-design.md"

        messages = [
            AgenticMessage(
                type=AgenticMessageType.THINKING,
                content="I'll create a design document...",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="write_file",
                tool_input={"path": artifact_path, "content": "# Design\n\nOverview..."},
                tool_call_id="call-write-1",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="write_file",
                tool_output=f"Successfully wrote to {artifact_path}",
                tool_call_id="call-write-1",
                is_error=False,
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="I've created the design document at docs/plans/test-design.md",
                session_id="driver-session-artifact",
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

    def test_write_file_creates_artifact(
        self,
        test_client_with_write_file: TestClient,
    ) -> None:
        """write_file tool call should create an artifact in the session."""
        # Create session
        create_resp = test_client_with_write_file.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test", "topic": "System design"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["id"]

        # Send message (driver will emit write_file)
        msg_resp = test_client_with_write_file.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Create a design document"},
        )
        assert msg_resp.status_code == 202

        # Verify artifact is created
        get_resp = test_client_with_write_file.get(
            f"/api/brainstorm/sessions/{session_id}"
        )
        assert get_resp.status_code == 200
        data = get_resp.json()

        artifacts = data["artifacts"]
        assert len(artifacts) == 1
        artifact = artifacts[0]
        assert artifact["path"] == "docs/plans/test-design.md"
        assert artifact["type"] == "design"  # Inferred from /plans/ in path

    def test_failed_write_file_does_not_create_artifact(
        self,
        test_brainstorm_service: BrainstormService,
        tmp_path: Path,
    ) -> None:
        """Failed write_file should not create an artifact."""
        # Create driver that fails write_file
        driver = MagicMock(spec=DriverInterface)
        messages = [
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="write_file",
                tool_input={"path": "docs/design.md"},
                tool_call_id="call-fail",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="write_file",
                tool_output="Permission denied",
                tool_call_id="call-fail",
                is_error=True,  # Failure!
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Failed to write file.",
            ),
        ]
        driver.execute_agentic = create_mock_execute_agentic(messages)

        app = create_app()

        @asynccontextmanager
        async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
            yield

        app.router.lifespan_context = noop_lifespan
        app.dependency_overrides[get_brainstorm_service] = (
            lambda: test_brainstorm_service
        )
        app.dependency_overrides[get_driver] = lambda: driver
        app.dependency_overrides[get_cwd] = lambda: str(tmp_path)

        client = TestClient(app)

        # Create session and send message
        create_resp = client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["id"]

        client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Create a design document"},
        )

        # Verify NO artifact is created
        get_resp = client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.status_code == 200
        assert len(get_resp.json()["artifacts"]) == 0


@pytest.mark.integration
class TestBrainstormHandoffFlow:
    """Test full handoff flow from brainstorming to implementation."""

    @pytest.fixture
    def mock_driver_with_write_file(self) -> MagicMock:
        """Create a mock driver that emits write_file tool call."""
        driver = MagicMock(spec=DriverInterface)
        messages = [
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="write_file",
                tool_input={
                    "path": "docs/design/system-architecture.md",
                    "content": "# System Architecture\n\n## Overview\n...",
                },
                tool_call_id="call-write",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="write_file",
                tool_output="Successfully wrote docs/design/system-architecture.md",
                tool_call_id="call-write",
                is_error=False,
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="I've created the system architecture document.",
                session_id="driver-handoff-session",
            ),
        ]
        driver.execute_agentic = create_mock_execute_agentic(messages)
        return driver

    @pytest.fixture
    def handoff_test_client(
        self,
        test_brainstorm_service: BrainstormService,
        mock_driver_with_write_file: MagicMock,
        tmp_path: Path,
    ) -> TestClient:
        """Create test client for handoff testing."""
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

    def test_full_handoff_flow(
        self,
        handoff_test_client: TestClient,
    ) -> None:
        """Full flow: create session → send message with write_file → handoff."""
        # Step 1: Create session
        create_resp = handoff_test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test", "topic": "System architecture design"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["id"]
        assert create_resp.json()["status"] == "active"

        # Step 2: Send message (driver will emit write_file)
        msg_resp = handoff_test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Create a system architecture document"},
        )
        assert msg_resp.status_code == 202

        # Verify artifact was created
        get_resp = handoff_test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.status_code == 200
        artifacts = get_resp.json()["artifacts"]
        assert len(artifacts) == 1
        artifact_path = artifacts[0]["path"]
        assert artifact_path == "docs/design/system-architecture.md"

        # Step 3: Handoff to implementation
        handoff_resp = handoff_test_client.post(
            f"/api/brainstorm/sessions/{session_id}/handoff",
            json={
                "artifact_path": artifact_path,
                "issue_title": "Implement system architecture",
                "issue_description": "Build the system as designed",
            },
        )
        assert handoff_resp.status_code == 200
        handoff_data = handoff_resp.json()
        assert "workflow_id" in handoff_data
        assert handoff_data["status"] == "created"

        # Verify session status changed to completed
        final_resp = handoff_test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert final_resp.status_code == 200
        assert final_resp.json()["session"]["status"] == "completed"

    def test_handoff_returns_workflow_id(
        self,
        handoff_test_client: TestClient,
    ) -> None:
        """Handoff should return a workflow_id for the implementation pipeline."""
        # Create session and send message
        create_resp = handoff_test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["id"]

        handoff_test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Design the system"},
        )

        # Get artifact path
        get_resp = handoff_test_client.get(f"/api/brainstorm/sessions/{session_id}")
        artifact_path = get_resp.json()["artifacts"][0]["path"]

        # Handoff
        handoff_resp = handoff_test_client.post(
            f"/api/brainstorm/sessions/{session_id}/handoff",
            json={"artifact_path": artifact_path},
        )

        # Verify workflow_id is a valid UUID-like string
        workflow_id = handoff_resp.json()["workflow_id"]
        assert workflow_id is not None
        assert len(workflow_id) == 36  # UUID format: 8-4-4-4-12
        assert "-" in workflow_id

    def test_handoff_fails_without_artifact(
        self,
        test_client: TestClient,
    ) -> None:
        """Handoff should fail if the artifact doesn't exist."""
        # Create session (no message, so no artifact)
        create_resp = test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["id"]

        # Try to handoff with non-existent artifact
        handoff_resp = test_client.post(
            f"/api/brainstorm/sessions/{session_id}/handoff",
            json={"artifact_path": "nonexistent/file.md"},
        )
        assert handoff_resp.status_code == 404

    def test_handoff_fails_for_nonexistent_session(
        self,
        test_client: TestClient,
    ) -> None:
        """Handoff should fail if the session doesn't exist."""
        handoff_resp = test_client.post(
            "/api/brainstorm/sessions/nonexistent-session-id/handoff",
            json={"artifact_path": "docs/design.md"},
        )
        assert handoff_resp.status_code == 404
