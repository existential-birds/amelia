"""Integration tests for brainstorm message flow.

Tests the full message flow with realistic driver behavior:
- Create session -> send message -> verify persistence
- Driver yields: THINKING -> TOOL_CALL -> TOOL_RESULT -> RESULT
- Artifact detection from write_file tool calls

Real components:
- FastAPI route handlers
- BrainstormService
- BrainstormRepository with PostgreSQL test database
- EventBus (without WebSocket connection manager)

Only mocked:
- Driver (execute_agentic as async generator)

Uses httpx.AsyncClient with ASGITransport to keep the ASGI app in the
same event loop as the asyncpg pool (TestClient creates a separate thread
with its own event loop, causing asyncpg event loop mismatches).
"""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverInterface
from amelia.server.database.brainstorm_repository import BrainstormRepository
from amelia.server.services.brainstorm import BrainstormService
from tests.conftest import create_mock_execute_agentic

from .conftest import AsyncClientFactory, _create_app_with_overrides


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
        List of AgenticMessage objects simulating THINKING -> TOOL_CALL -> TOOL_RESULT -> RESULT.
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


def _create_mock_execute_agentic_with_plan_file(
    messages: list[AgenticMessage],
) -> Any:
    """Create a mock execute_agentic that also creates the plan file on disk.

    The service detects artifacts by checking if the plan file exists after
    driver execution. This wrapper creates that file based on the cwd kwarg
    passed by the service, so the filesystem check succeeds.
    """
    from collections.abc import AsyncGenerator as AG

    async def mock_execute_agentic(
        *args: Any, **kwargs: Any
    ) -> AG[AgenticMessage, None]:
        cwd = kwargs.get("cwd", "")
        if cwd:
            # Create any .md file under docs/plans/ so the service finds it.
            # We glob for the plan path the service will generate.
            plans_dir = Path(cwd) / "docs" / "plans"
            plans_dir.mkdir(parents=True, exist_ok=True)
            # The service will check a specific path - we need to create it.
            # Since we can't know the exact path, we scan for what the service
            # stored in session.output_artifact_path by creating a marker.
            # Actually: look for session.output_artifact_path via the instructions kwarg.
            # The instructions contain the plan_path. Extract it.
            instructions = kwargs.get("instructions", "")
            # The instructions contain: "Write the validated design to `{plan_path}`"
            import re
            match = re.search(r"Write the validated design to `([^`]+)`", instructions)
            if match:
                plan_path = match.group(1)
                abs_path = Path(cwd) / plan_path
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_text("# Design\n\nOverview...")

        for msg in messages:
            yield msg

    return mock_execute_agentic


@pytest.fixture
def mock_driver() -> MagicMock:
    """Create a mock driver with realistic message flow."""
    driver = MagicMock(spec=DriverInterface)
    messages = create_realistic_driver_messages()
    driver.execute_agentic = create_mock_execute_agentic(messages)
    return driver


@pytest.fixture
async def test_client(
    test_brainstorm_service: BrainstormService,
    mock_driver: MagicMock,
    tmp_path: Path,
    async_client_factory: AsyncClientFactory,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create async test client with real dependencies and mock driver."""
    app = _create_app_with_overrides(test_brainstorm_service, lambda: mock_driver, str(tmp_path))
    async with async_client_factory(app) as client:
        yield client


# =============================================================================
# Test Classes
# =============================================================================


@pytest.mark.integration
class TestBrainstormMessageFlow:
    """Test full message flow from HTTP request to persistence."""

    async def test_send_message_persists_user_message(
        self,
        test_client: httpx.AsyncClient,
        test_brainstorm_repository: BrainstormRepository,
    ) -> None:
        """Sending a message should persist the user message with seq=1."""
        # Create session
        create_resp = await test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test", "topic": "API design"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session"]["id"]

        # Send message
        msg_resp = await test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "How should I structure the REST API?"},
        )
        assert msg_resp.status_code == 202

        # Verify user message is persisted
        get_resp = await test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()

        messages = data["messages"]
        assert len(messages) >= 1
        user_msg = messages[0]
        assert user_msg["role"] == "user"
        assert user_msg["sequence"] == 1
        assert user_msg["content"] == "How should I structure the REST API?"

    async def test_send_message_persists_assistant_message(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Sending a message should persist the assistant response with seq=2."""
        # Create session
        create_resp = await test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test", "topic": "API design"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session"]["id"]

        # Send message
        msg_resp = await test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "How should I structure the REST API?"},
        )
        assert msg_resp.status_code == 202

        # Verify assistant message is persisted
        get_resp = await test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()

        messages = data["messages"]
        assert len(messages) >= 2

        # Find assistant message
        assistant_msg = next((m for m in messages if m["role"] == "assistant"), None)
        assert assistant_msg is not None
        assert assistant_msg["sequence"] == 2
        assert "Based on my analysis" in assistant_msg["content"]

    async def test_send_message_saves_driver_session_id(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Sending a message should save the driver session ID for continuity."""
        # Create session
        create_resp = await test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session"]["id"]

        # Initially no driver_session_id
        initial_resp = await test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert initial_resp.status_code == 200
        assert initial_resp.json()["session"].get("driver_session_id") is None

        # Send message (mock driver returns session_id in RESULT message)
        msg_resp = await test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Hello"},
        )
        assert msg_resp.status_code == 202

        # Verify driver_session_id is now saved
        final_resp = await test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert final_resp.status_code == 200
        assert final_resp.json()["session"]["driver_session_id"] == "driver-session-123"


@pytest.mark.integration
class TestBrainstormArtifactDetection:
    """Test artifact creation from write_file tool calls."""

    @pytest.fixture
    def mock_driver_with_write_file(self, tmp_path: Path) -> MagicMock:
        """Create a mock driver that creates the plan file on disk.

        The service detects artifacts by checking if the plan file exists
        after driver execution, so the mock must actually create the file.
        """
        driver = MagicMock(spec=DriverInterface)

        messages = [
            AgenticMessage(
                type=AgenticMessageType.THINKING,
                content="I'll create a design document...",
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="I've created the design document.",
                session_id="driver-session-artifact",
            ),
        ]
        driver.execute_agentic = _create_mock_execute_agentic_with_plan_file(messages)
        return driver

    @pytest.fixture
    async def test_client_with_write_file(
        self,
        test_brainstorm_service: BrainstormService,
        mock_driver_with_write_file: MagicMock,
        tmp_path: Path,
        async_client_factory: AsyncClientFactory,
    ) -> AsyncGenerator[httpx.AsyncClient, None]:
        """Create test client with driver that creates plan file."""
        app = _create_app_with_overrides(
            test_brainstorm_service, lambda: mock_driver_with_write_file, str(tmp_path)
        )
        async with async_client_factory(app) as client:
            yield client

    async def test_write_file_creates_artifact(
        self,
        test_client_with_write_file: httpx.AsyncClient,
    ) -> None:
        """Driver creating the plan file should produce an artifact in the session."""
        # Create session
        create_resp = await test_client_with_write_file.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test", "topic": "System design"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session"]["id"]

        # Send message (driver mock will create the plan file on disk)
        msg_resp = await test_client_with_write_file.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Create a design document"},
        )
        assert msg_resp.status_code == 202

        # Verify artifact is created
        get_resp = await test_client_with_write_file.get(
            f"/api/brainstorm/sessions/{session_id}"
        )
        assert get_resp.status_code == 200
        data = get_resp.json()

        artifacts = data["artifacts"]
        assert len(artifacts) == 1
        artifact = artifacts[0]
        assert "docs/plans/" in artifact["path"]
        assert artifact["path"].endswith(".md")
        assert artifact["type"] == "design"  # Inferred from /plans/ in path

    async def test_failed_write_file_does_not_create_artifact(
        self,
        test_brainstorm_service: BrainstormService,
        tmp_path: Path,
        async_client_factory: AsyncClientFactory,
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

        app = _create_app_with_overrides(test_brainstorm_service, lambda: driver, str(tmp_path))
        async with async_client_factory(app) as client:
            # Create session and send message
            create_resp = await client.post(
                "/api/brainstorm/sessions",
                json={"profile_id": "test"},
            )
            session_id = create_resp.json()["session"]["id"]

            await client.post(
                f"/api/brainstorm/sessions/{session_id}/message",
                json={"content": "Create a design document"},
            )

            # Verify NO artifact is created
            get_resp = await client.get(f"/api/brainstorm/sessions/{session_id}")
            assert get_resp.status_code == 200
            assert len(get_resp.json()["artifacts"]) == 0


@pytest.mark.integration
class TestBrainstormHandoffFlow:
    """Test full handoff flow from brainstorming to implementation."""

    @pytest.fixture
    def mock_driver_with_write_file(self) -> MagicMock:
        """Create a mock driver that creates the plan file on disk.

        The service detects artifacts by checking if the plan file exists
        after driver execution, so the mock must actually create the file.
        """
        driver = MagicMock(spec=DriverInterface)
        messages = [
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="I've created the system architecture document.",
                session_id="driver-handoff-session",
            ),
        ]
        driver.execute_agentic = _create_mock_execute_agentic_with_plan_file(messages)
        return driver

    @pytest.fixture
    async def handoff_test_client(
        self,
        test_brainstorm_service: BrainstormService,
        mock_driver_with_write_file: MagicMock,
        tmp_path: Path,
        async_client_factory: AsyncClientFactory,
    ) -> AsyncGenerator[httpx.AsyncClient, None]:
        """Create test client for handoff testing."""
        app = _create_app_with_overrides(
            test_brainstorm_service, lambda: mock_driver_with_write_file, str(tmp_path)
        )
        async with async_client_factory(app) as client:
            yield client

    async def test_full_handoff_flow(
        self,
        handoff_test_client: httpx.AsyncClient,
    ) -> None:
        """Full flow: create session -> send message with write_file -> handoff."""
        # Step 1: Create session
        create_resp = await handoff_test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test", "topic": "System architecture design"},
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session"]["id"]
        assert create_resp.json()["session"]["status"] == "active"

        # Step 2: Send message (driver will emit write_file)
        msg_resp = await handoff_test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Create a system architecture document"},
        )
        assert msg_resp.status_code == 202

        # Verify artifact was created
        get_resp = await handoff_test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert get_resp.status_code == 200
        artifacts = get_resp.json()["artifacts"]
        assert len(artifacts) == 1
        artifact_path = artifacts[0]["path"]
        assert "docs/plans/" in artifact_path
        assert artifact_path.endswith(".md")

        # Step 3: Handoff to implementation
        handoff_resp = await handoff_test_client.post(
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
        final_resp = await handoff_test_client.get(f"/api/brainstorm/sessions/{session_id}")
        assert final_resp.status_code == 200
        assert final_resp.json()["session"]["status"] == "completed"

    async def test_handoff_returns_workflow_id(
        self,
        handoff_test_client: httpx.AsyncClient,
    ) -> None:
        """Handoff should return a workflow_id for the implementation pipeline."""
        # Create session and send message
        create_resp = await handoff_test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["session"]["id"]

        await handoff_test_client.post(
            f"/api/brainstorm/sessions/{session_id}/message",
            json={"content": "Design the system"},
        )

        # Get artifact path
        get_resp = await handoff_test_client.get(f"/api/brainstorm/sessions/{session_id}")
        artifact_path = get_resp.json()["artifacts"][0]["path"]

        # Handoff
        handoff_resp = await handoff_test_client.post(
            f"/api/brainstorm/sessions/{session_id}/handoff",
            json={"artifact_path": artifact_path},
        )

        # Verify workflow_id is a valid UUID-like string
        workflow_id = handoff_resp.json()["workflow_id"]
        assert workflow_id is not None
        assert len(workflow_id) == 36  # UUID format: 8-4-4-4-12
        assert "-" in workflow_id

    async def test_handoff_fails_without_artifact(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Handoff should fail if the artifact doesn't exist."""
        # Create session (no message, so no artifact)
        create_resp = await test_client.post(
            "/api/brainstorm/sessions",
            json={"profile_id": "test"},
        )
        session_id = create_resp.json()["session"]["id"]

        # Try to handoff with non-existent artifact
        handoff_resp = await test_client.post(
            f"/api/brainstorm/sessions/{session_id}/handoff",
            json={"artifact_path": "nonexistent/file.md"},
        )
        assert handoff_resp.status_code == 404

    async def test_handoff_fails_for_nonexistent_session(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Handoff should fail if the session doesn't exist."""
        handoff_resp = await test_client.post(
            "/api/brainstorm/sessions/00000000-0000-4000-8000-000000000099/handoff",
            json={"artifact_path": "docs/design.md"},
        )
        assert handoff_resp.status_code == 404
