"""Tests for BrainstormService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.server.models.brainstorm import Artifact, BrainstormingSession, Message
from amelia.server.services.brainstorm import BrainstormService


class TestBrainstormService:
    """Test BrainstormService operations."""

    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        """Create mock repository."""
        repo = MagicMock()
        repo.create_session = AsyncMock()
        repo.get_session = AsyncMock(return_value=None)
        repo.update_session = AsyncMock()
        repo.delete_session = AsyncMock()
        repo.list_sessions = AsyncMock(return_value=[])
        repo.save_message = AsyncMock()
        repo.get_messages = AsyncMock(return_value=[])
        repo.get_max_sequence = AsyncMock(return_value=0)
        repo.save_artifact = AsyncMock()
        repo.get_artifacts = AsyncMock(return_value=[])
        return repo

    @pytest.fixture
    def mock_event_bus(self) -> MagicMock:
        """Create mock event bus."""
        bus = MagicMock()
        bus.emit = MagicMock()
        return bus

    @pytest.fixture
    def service(
        self, mock_repository: MagicMock, mock_event_bus: MagicMock
    ) -> BrainstormService:
        """Create service instance."""
        return BrainstormService(mock_repository, mock_event_bus)


class TestCreateSession(TestBrainstormService):
    """Test session creation."""

    async def test_create_session_generates_id(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should generate UUID for new session."""
        session = await service.create_session(
            profile_id="work", topic="Design a cache"
        )

        assert session.id is not None
        assert len(session.id) == 36  # UUID format
        mock_repository.create_session.assert_called_once()

    async def test_create_session_sets_defaults(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should set default status and timestamps."""
        session = await service.create_session(profile_id="work")

        assert session.status == "active"
        assert session.created_at is not None
        assert session.updated_at is not None

    async def test_create_session_emits_event(
        self, service: BrainstormService, mock_event_bus: MagicMock
    ) -> None:
        """Should emit session created event."""
        await service.create_session(profile_id="work")

        mock_event_bus.emit.assert_called_once()
        event = mock_event_bus.emit.call_args[0][0]
        assert event.event_type.value == "brainstorm_session_created"


class TestGetSession(TestBrainstormService):
    """Test session retrieval."""

    async def test_get_session_returns_session_with_messages(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should return session with messages and artifacts."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1", profile_id="work", status="active",
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_messages.return_value = [
            Message(
                id="msg-1", session_id="sess-1", sequence=1,
                role="user", content="Hello", created_at=now,
            )
        ]
        mock_repository.get_artifacts.return_value = []

        result = await service.get_session_with_history("sess-1")

        assert result is not None
        assert result["session"].id == "sess-1"
        assert len(result["messages"]) == 1
        assert result["artifacts"] == []

    async def test_get_session_not_found(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should return None for non-existent session."""
        mock_repository.get_session.return_value = None

        result = await service.get_session_with_history("nonexistent")

        assert result is None


class TestDeleteSession(TestBrainstormService):
    """Test session deletion."""

    async def test_delete_session(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should delete session."""
        await service.delete_session("sess-1")
        mock_repository.delete_session.assert_called_once_with("sess-1")


class TestUpdateSessionStatus(TestBrainstormService):
    """Test session status updates."""

    async def test_update_status(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should update session status."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1", profile_id="work", status="active",
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session

        await service.update_session_status("sess-1", "ready_for_handoff")

        mock_repository.update_session.assert_called_once()
        updated = mock_repository.update_session.call_args[0][0]
        assert updated.status == "ready_for_handoff"

    async def test_update_status_session_not_found(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should raise error if session not found."""
        mock_repository.get_session.return_value = None

        with pytest.raises(ValueError, match="Session not found"):
            await service.update_session_status("nonexistent", "completed")


class TestSendMessage(TestBrainstormService):
    """Test message sending with driver integration."""

    @pytest.fixture
    def mock_driver(self) -> MagicMock:
        """Create mock driver."""
        driver = MagicMock()

        # execute_agentic returns an async iterator
        async def mock_execute_agentic(*args, **kwargs):
            from amelia.drivers.base import AgenticMessage, AgenticMessageType

            yield AgenticMessage(
                type=AgenticMessageType.THINKING,
                content="Let me think about this...",
            )
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Here's my response",
                session_id="claude-sess-789",
            )

        driver.execute_agentic = mock_execute_agentic
        return driver

    async def test_send_message_saves_user_message(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_driver: MagicMock,
    ) -> None:
        """Should save user message to database."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1",
            profile_id="work",
            status="active",
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0

        # Consume the async generator
        messages = []
        async for msg in service.send_message(
            session_id="sess-1",
            content="Design a cache",
            driver=mock_driver,
            cwd="/tmp/project",
        ):
            messages.append(msg)

        # Verify user message was saved
        save_calls = mock_repository.save_message.call_args_list
        user_msg_call = save_calls[0][0][0]
        assert user_msg_call.role == "user"
        assert user_msg_call.content == "Design a cache"
        assert user_msg_call.sequence == 1

    async def test_send_message_emits_events(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
        mock_driver: MagicMock,
    ) -> None:
        """Should emit events for driver messages."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1",
            profile_id="work",
            status="active",
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0

        messages = []
        async for msg in service.send_message(
            session_id="sess-1",
            content="Design a cache",
            driver=mock_driver,
            cwd="/tmp/project",
        ):
            messages.append(msg)

        # Verify events were emitted (thinking + result + message_complete)
        assert mock_event_bus.emit.call_count >= 2

    async def test_send_message_updates_driver_session_id(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_driver: MagicMock,
    ) -> None:
        """Should update driver_session_id from result."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1",
            profile_id="work",
            status="active",
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0

        messages = []
        async for msg in service.send_message(
            session_id="sess-1",
            content="Hello",
            driver=mock_driver,
            cwd="/tmp/project",
        ):
            messages.append(msg)

        # Verify session was updated with driver session ID
        update_calls = mock_repository.update_session.call_args_list
        assert len(update_calls) > 0
        # Find the call that updated driver_session_id
        updated_session = update_calls[-1][0][0]
        assert updated_session.driver_session_id == "claude-sess-789"

    async def test_send_message_session_not_found(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_driver: MagicMock,
    ) -> None:
        """Should raise error if session not found."""
        mock_repository.get_session.return_value = None

        with pytest.raises(ValueError, match="Session not found"):
            async for _ in service.send_message(
                session_id="nonexistent",
                content="Hello",
                driver=mock_driver,
                cwd="/tmp/project",
            ):
                pass


class TestArtifactDetection(TestBrainstormService):
    """Test artifact detection from tool results."""

    @pytest.fixture
    def mock_driver_with_write(self) -> MagicMock:
        """Create mock driver that writes a file."""
        driver = MagicMock()

        async def mock_execute_agentic(*args, **kwargs):
            from amelia.drivers.base import AgenticMessage, AgenticMessageType

            yield AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="write_file",
                tool_input={"path": "docs/plans/2026-01-18-cache-design.md"},
                tool_call_id="call-1",
            )
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="write_file",
                tool_output="File written successfully",
                tool_call_id="call-1",
            )
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="I've written the design document.",
                session_id="claude-sess-789",
            )

        driver.execute_agentic = mock_execute_agentic
        return driver

    async def test_detects_artifact_from_write_file(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
        mock_driver_with_write: MagicMock,
    ) -> None:
        """Should save artifact when write_file tool is used."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1",
            profile_id="work",
            status="active",
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0

        messages = []
        async for msg in service.send_message(
            session_id="sess-1",
            content="Write the design doc",
            driver=mock_driver_with_write,
            cwd="/tmp/project",
        ):
            messages.append(msg)

        # Verify artifact was saved
        mock_repository.save_artifact.assert_called_once()
        artifact = mock_repository.save_artifact.call_args[0][0]
        assert artifact.path == "docs/plans/2026-01-18-cache-design.md"
        assert artifact.type == "design"  # Inferred from path

    async def test_emits_artifact_created_event(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
        mock_driver_with_write: MagicMock,
    ) -> None:
        """Should emit BRAINSTORM_ARTIFACT_CREATED event."""
        from amelia.server.models.events import EventType

        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1",
            profile_id="work",
            status="active",
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0

        messages = []
        async for msg in service.send_message(
            session_id="sess-1",
            content="Write the design doc",
            driver=mock_driver_with_write,
            cwd="/tmp/project",
        ):
            messages.append(msg)

        # Find artifact created event
        artifact_events = [
            call[0][0]
            for call in mock_event_bus.emit.call_args_list
            if call[0][0].event_type == EventType.BRAINSTORM_ARTIFACT_CREATED
        ]
        assert len(artifact_events) == 1
        assert artifact_events[0].data["path"] == "docs/plans/2026-01-18-cache-design.md"


class TestHandoff(TestBrainstormService):
    """Test handoff to implementation pipeline."""

    async def test_handoff_updates_session_status(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should update session status to completed."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1", profile_id="work", status="ready_for_handoff",
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = [
            Artifact(
                id="art-1", session_id="sess-1", type="design",
                path="docs/plans/design.md", created_at=now,
            )
        ]

        result = await service.handoff_to_implementation(
            session_id="sess-1",
            artifact_path="docs/plans/design.md",
        )

        assert result is not None
        # Session should be updated to completed
        update_calls = mock_repository.update_session.call_args_list
        updated_session = update_calls[-1][0][0]
        assert updated_session.status == "completed"

    async def test_handoff_returns_workflow_id(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should return a new workflow ID."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1", profile_id="work", status="ready_for_handoff",
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = [
            Artifact(
                id="art-1", session_id="sess-1", type="design",
                path="docs/plans/design.md", created_at=now,
            )
        ]

        result = await service.handoff_to_implementation(
            session_id="sess-1",
            artifact_path="docs/plans/design.md",
        )

        assert "workflow_id" in result
        assert len(result["workflow_id"]) == 36  # UUID

    async def test_handoff_artifact_not_found(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should raise error if artifact not found."""
        now = datetime.now(UTC)
        mock_session = BrainstormingSession(
            id="sess-1", profile_id="work", status="ready_for_handoff",
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = []  # No artifacts

        with pytest.raises(ValueError, match="Artifact not found"):
            await service.handoff_to_implementation(
                session_id="sess-1",
                artifact_path="docs/plans/design.md",
            )

    async def test_handoff_session_not_found(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should raise error if session not found."""
        mock_repository.get_session.return_value = None

        with pytest.raises(ValueError, match="Session not found"):
            await service.handoff_to_implementation(
                session_id="nonexistent",
                artifact_path="docs/plans/design.md",
            )
