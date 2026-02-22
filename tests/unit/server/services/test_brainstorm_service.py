"""Tests for BrainstormService."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from amelia.drivers.base import AgenticMessage
from amelia.server.models.brainstorm import (
    Artifact,
    BrainstormingSession,
    Message,
    MessageRole,
    SessionStatus,
)
from amelia.server.models.events import EventDomain
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
        repo.get_session_usage = AsyncMock(return_value=None)
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

    @pytest.fixture
    def mock_cleanup(self) -> AsyncMock:
        """Create mock async cleanup callback."""
        return AsyncMock(return_value=True)

    @pytest.fixture
    def service_with_cleanup(
        self,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
        mock_cleanup: MagicMock,
    ) -> BrainstormService:
        """Create service with cleanup callback."""
        return BrainstormService(
            mock_repository, mock_event_bus, driver_cleanup=mock_cleanup
        )


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
        assert len(str(session.id)) == 36  # UUID format
        mock_repository.create_session.assert_called_once()

    async def test_create_session_sets_defaults(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should set default status and timestamps."""
        session = await service.create_session(profile_id="work")

        assert session.status == SessionStatus.ACTIVE
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
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id, profile_id="work", status=SessionStatus.ACTIVE,
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_messages.return_value = [
            Message(
                id=uuid4(), session_id=sess_id, sequence=1,
                role=MessageRole.USER, content="Hello", created_at=now,
            )
        ]
        mock_repository.get_artifacts.return_value = []

        result = await service.get_session_with_history(str(sess_id))

        assert result is not None
        assert result["session"].id == sess_id
        assert len(result["messages"]) == 1
        assert result["artifacts"] == []

    async def test_get_session_not_found(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should return None for non-existent session."""
        mock_repository.get_session.return_value = None

        result = await service.get_session_with_history(uuid4())

        assert result is None


class TestDeleteSession(TestBrainstormService):
    """Test session deletion."""

    async def test_delete_session(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should delete session."""
        sess_id = uuid4()
        await service.delete_session(sess_id)
        mock_repository.delete_session.assert_called_once_with(sess_id)


class TestUpdateSessionStatus(TestBrainstormService):
    """Test session status updates."""

    async def test_update_status(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should update session status."""
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id, profile_id="work", status=SessionStatus.ACTIVE,
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session

        await service.update_session_status(str(sess_id), SessionStatus.READY_FOR_HANDOFF)

        mock_repository.update_session.assert_called_once()
        updated = mock_repository.update_session.call_args[0][0]
        assert updated.status == SessionStatus.READY_FOR_HANDOFF

    async def test_update_status_session_not_found(
        self, service: BrainstormService, mock_repository: MagicMock
    ) -> None:
        """Should raise error if session not found."""
        mock_repository.get_session.return_value = None

        with pytest.raises(ValueError, match="Session not found"):
            await service.update_session_status(uuid4(), SessionStatus.COMPLETED)


class TestSendMessage(TestBrainstormService):
    """Test message sending with driver integration."""

    @pytest.fixture
    def mock_driver(self) -> MagicMock:
        """Create mock driver."""
        driver = MagicMock()

        # execute_agentic returns an async iterator
        async def mock_execute_agentic(
            *args: object, **kwargs: object
        ) -> AsyncIterator[AgenticMessage]:
            from amelia.drivers.base import AgenticMessageType

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
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0

        # Consume the async generator
        messages = []
        async for msg in service.send_message(
            session_id=sess_id,
            content="Design a cache",
            driver=mock_driver,
            cwd="/tmp/project",
        ):
            messages.append(msg)

        # Verify user message was saved
        save_calls = mock_repository.save_message.call_args_list
        user_msg_call = save_calls[0][0][0]
        assert user_msg_call.role == MessageRole.USER
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
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0

        messages = []
        async for msg in service.send_message(
            session_id=sess_id,
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
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0

        messages = []
        async for msg in service.send_message(
            session_id=sess_id,
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
                session_id=uuid4(),
                content="Hello",
                driver=mock_driver,
                cwd="/tmp/project",
            ):
                pass


class TestArtifactDetection(TestBrainstormService):
    """Test artifact detection via filesystem check after driver completes."""

    @pytest.fixture
    def mock_driver_result_only(self) -> MagicMock:
        """Create mock driver that only yields a RESULT (no tool events)."""
        driver = MagicMock()

        async def mock_execute_agentic(
            *args: object, **kwargs: object
        ) -> AsyncIterator[AgenticMessage]:
            from amelia.drivers.base import AgenticMessageType

            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="I've written the design document.",
                session_id="claude-sess-789",
            )

        driver.execute_agentic = mock_execute_agentic
        return driver

    def _make_session(self, sess_id: UUID) -> BrainstormingSession:
        now = datetime.now(UTC)
        return BrainstormingSession(
            id=sess_id,
            profile_id="work",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )

    async def test_detects_artifact_when_plan_file_exists(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
        mock_driver_result_only: MagicMock,
        tmp_path: object,
    ) -> None:
        """Should save artifact when the plan file exists on disk after driver completes."""
        from pathlib import Path
        from unittest.mock import patch

        sess_id = uuid4()
        mock_repository.get_session.return_value = self._make_session(sess_id)
        mock_repository.get_max_sequence.return_value = 0

        # Patch Path.is_file to return True for the plan path
        original_is_file = Path.is_file

        def fake_is_file(self: Path) -> bool:
            if "docs/plans/" in str(self):
                return True
            return original_is_file(self)

        with patch.object(Path, "is_file", fake_is_file):
            messages = []
            async for msg in service.send_message(
                session_id=sess_id,
                content="Design a caching layer",
                driver=mock_driver_result_only,
                cwd="/tmp/project",
            ):
                messages.append(msg)

        mock_repository.save_artifact.assert_called_once()
        artifact = mock_repository.save_artifact.call_args[0][0]
        assert "docs/plans/" in artifact.path

    async def test_no_artifact_when_plan_file_missing(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
        mock_driver_result_only: MagicMock,
    ) -> None:
        """Should not save artifact when the plan file does not exist on disk."""
        from pathlib import Path
        from unittest.mock import patch

        sess_id = uuid4()
        mock_repository.get_session.return_value = self._make_session(sess_id)
        mock_repository.get_max_sequence.return_value = 0

        # Path.is_file returns False by default for non-existent paths,
        # but be explicit
        with patch.object(Path, "is_file", return_value=False):
            messages = []
            async for msg in service.send_message(
                session_id=sess_id,
                content="Design a caching layer",
                driver=mock_driver_result_only,
                cwd="/tmp/nonexistent",
            ):
                messages.append(msg)

        mock_repository.save_artifact.assert_not_called()

    async def test_artifact_created_event_emitted(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
        mock_driver_result_only: MagicMock,
    ) -> None:
        """Should emit BRAINSTORM_ARTIFACT_CREATED event when plan file exists."""
        from pathlib import Path
        from unittest.mock import patch

        from amelia.server.models.events import EventType

        sess_id = uuid4()
        mock_repository.get_session.return_value = self._make_session(sess_id)
        mock_repository.get_max_sequence.return_value = 0

        original_is_file = Path.is_file

        def fake_is_file(self: Path) -> bool:
            if "docs/plans/" in str(self):
                return True
            return original_is_file(self)

        with patch.object(Path, "is_file", fake_is_file):
            messages = []
            async for msg in service.send_message(
                session_id=sess_id,
                content="Design a caching layer",
                driver=mock_driver_result_only,
                cwd="/tmp/project",
            ):
                messages.append(msg)

        artifact_events = [
            call[0][0]
            for call in mock_event_bus.emit.call_args_list
            if call[0][0].event_type == EventType.BRAINSTORM_ARTIFACT_CREATED
        ]
        assert len(artifact_events) == 1
        event = artifact_events[0]
        assert event.domain == EventDomain.BRAINSTORM
        assert "docs/plans/" in event.data["path"]


class TestHandoff(TestBrainstormService):
    """Test handoff to implementation pipeline."""

    async def test_handoff_updates_session_status(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should update session status to completed."""
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id, profile_id="work", status=SessionStatus.READY_FOR_HANDOFF,
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = [
            Artifact(
                id=uuid4(), session_id=sess_id, type="design",
                path="docs/plans/design.md", created_at=now,
            )
        ]

        result = await service.handoff_to_implementation(
            session_id=sess_id,
            artifact_path="docs/plans/design.md",
        )

        assert result is not None
        # Session should be updated to completed
        update_calls = mock_repository.update_session.call_args_list
        updated_session = update_calls[-1][0][0]
        assert updated_session.status == SessionStatus.COMPLETED

    async def test_handoff_returns_workflow_id(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should return a new workflow ID."""
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id, profile_id="work", status=SessionStatus.READY_FOR_HANDOFF,
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = [
            Artifact(
                id=uuid4(), session_id=sess_id, type="design",
                path="docs/plans/design.md", created_at=now,
            )
        ]

        result = await service.handoff_to_implementation(
            session_id=sess_id,
            artifact_path="docs/plans/design.md",
        )

        assert "workflow_id" in result
        assert len(str(result["workflow_id"])) == 36  # UUID

    async def test_handoff_artifact_not_found(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should raise error if artifact not found."""
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id, profile_id="work", status=SessionStatus.READY_FOR_HANDOFF,
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = []  # No artifacts

        with pytest.raises(ValueError, match="Artifact not found"):
            await service.handoff_to_implementation(
                session_id=sess_id,
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
                session_id=uuid4(),
                artifact_path="docs/plans/design.md",
            )

    async def test_handoff_calls_orchestrator_queue_workflow(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should call orchestrator.queue_workflow with correct parameters."""
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id, profile_id="work", status=SessionStatus.READY_FOR_HANDOFF,
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = [
            Artifact(
                id=uuid4(), session_id=sess_id, type="design",
                path="docs/plans/design.md", created_at=now,
            )
        ]

        mock_orchestrator = MagicMock()
        mock_orchestrator.queue_workflow = AsyncMock(return_value="wf-real-123")

        result = await service.handoff_to_implementation(
            session_id=sess_id,
            artifact_path="docs/plans/design.md",
            issue_title="Implement feature X",
            orchestrator=mock_orchestrator,
            worktree_path="/path/to/worktree",
        )

        assert result["workflow_id"] == "wf-real-123"
        mock_orchestrator.queue_workflow.assert_called_once()

    async def test_handoff_raises_for_non_noop_tracker(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should raise ValueError for non-none tracker."""
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id, profile_id="work", status=SessionStatus.READY_FOR_HANDOFF,
            created_at=now, updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = [
            Artifact(
                id=uuid4(), session_id=sess_id, type="design",
                path="docs/plans/design.md", created_at=now,
            )
        ]

        mock_orchestrator = MagicMock()
        # Simulate ValueError from orchestrator when tracker is not none
        mock_orchestrator.queue_workflow = AsyncMock(
            side_effect=ValueError("task_title can only be used with none tracker")
        )

        with pytest.raises(ValueError, match="none tracker"):
            await service.handoff_to_implementation(
                session_id=sess_id,
                artifact_path="docs/plans/design.md",
                issue_title="Implement feature X",
                orchestrator=mock_orchestrator,
                worktree_path="/path/to/worktree",
            )

    async def test_handoff_passes_artifact_path_to_workflow_request(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should pass artifact_path when creating workflow request."""
        # Setup session and artifact
        sess_id = uuid4()
        session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            driver_session_id=None,
            status=SessionStatus.ACTIVE,
            topic="Test design",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        artifact = Artifact(
            id=uuid4(),
            session_id=sess_id,
            path="/path/to/design.md",
            type="design",
            title="Design Doc",
            created_at=datetime.now(UTC),
        )
        mock_repository.get_session.return_value = session
        mock_repository.get_artifacts.return_value = [artifact]

        # Create mock orchestrator that captures the request
        mock_orchestrator = AsyncMock()
        mock_orchestrator.queue_workflow = AsyncMock(return_value="workflow-456")

        # Execute handoff
        result = await service.handoff_to_implementation(
            session_id=sess_id,
            artifact_path="/path/to/design.md",
            issue_title="Implement design",
            orchestrator=mock_orchestrator,
            worktree_path="/path/to/repo",
        )

        # Verify workflow was created with artifact_path
        mock_orchestrator.queue_workflow.assert_called_once()
        request = mock_orchestrator.queue_workflow.call_args[0][0]
        assert request.artifact_path == "/path/to/design.md"
        assert result["workflow_id"] == "workflow-456"

    async def test_handoff_generates_short_issue_id_from_title(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should generate slugified issue_id from title + session hash."""
        now = datetime.now(UTC)
        sess_id = UUID("d9336c40-4ce9-4b12-81e1-099bb70eaa01")
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            status=SessionStatus.READY_FOR_HANDOFF,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = [
            Artifact(
                id=uuid4(), session_id=sess_id,
                type="design", path="docs/plans/design.md", created_at=now,
            )
        ]
        mock_orchestrator = MagicMock()
        mock_orchestrator.queue_workflow = AsyncMock(return_value="wf-123")

        await service.handoff_to_implementation(
            session_id=sess_id,
            artifact_path="docs/plans/design.md",
            issue_title="Add dark mode support",
            orchestrator=mock_orchestrator,
            worktree_path="/path/to/worktree",
        )

        request = mock_orchestrator.queue_workflow.call_args[0][0]
        assert request.issue_id == "add-dark-mode-d9336c40"
        assert len(request.issue_id) <= 24

    async def test_handoff_falls_back_without_title(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should use brainstorm-{hash} when no title provided."""
        now = datetime.now(UTC)
        sess_id = UUID("d9336c40-4ce9-4b12-81e1-099bb70eaa01")
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            status=SessionStatus.READY_FOR_HANDOFF,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = [
            Artifact(
                id=uuid4(), session_id=sess_id,
                type="design", path="docs/plans/design.md", created_at=now,
            )
        ]
        mock_orchestrator = MagicMock()
        mock_orchestrator.queue_workflow = AsyncMock(return_value="wf-123")

        await service.handoff_to_implementation(
            session_id=sess_id,
            artifact_path="docs/plans/design.md",
            orchestrator=mock_orchestrator,
            worktree_path="/path/to/worktree",
        )

        request = mock_orchestrator.queue_workflow.call_args[0][0]
        assert request.issue_id == "brainstorm-d9336c40"

    async def test_handoff_uses_session_topic_when_no_title(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should slugify session.topic when issue_title is not provided."""
        now = datetime.now(UTC)
        sess_id = UUID("d9336c40-4ce9-4b12-81e1-099bb70eaa01")
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            status=SessionStatus.READY_FOR_HANDOFF,
            topic="Add dark mode",
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = [
            Artifact(
                id=uuid4(), session_id=sess_id,
                type="design", path="docs/plans/design.md", created_at=now,
            )
        ]
        mock_orchestrator = MagicMock()
        mock_orchestrator.queue_workflow = AsyncMock(return_value="wf-123")

        await service.handoff_to_implementation(
            session_id=sess_id,
            artifact_path="docs/plans/design.md",
            orchestrator=mock_orchestrator,
            worktree_path="/path/to/worktree",
        )

        request = mock_orchestrator.queue_workflow.call_args[0][0]
        assert request.issue_id == "add-dark-mode-d9336c40"

    async def test_handoff_falls_back_for_empty_slug(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """Should use fallback when title produces empty slug."""
        now = datetime.now(UTC)
        sess_id = UUID("d9336c40-4ce9-4b12-81e1-099bb70eaa01")
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            status=SessionStatus.READY_FOR_HANDOFF,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = [
            Artifact(
                id=uuid4(), session_id=sess_id,
                type="design", path="docs/plans/design.md", created_at=now,
            )
        ]
        mock_orchestrator = MagicMock()
        mock_orchestrator.queue_workflow = AsyncMock(return_value="wf-123")

        await service.handoff_to_implementation(
            session_id=sess_id,
            artifact_path="docs/plans/design.md",
            issue_title="!!!@@@",
            orchestrator=mock_orchestrator,
            worktree_path="/path/to/worktree",
        )

        request = mock_orchestrator.queue_workflow.call_args[0][0]
        assert request.issue_id == "brainstorm-d9336c40"


class TestDeleteSessionCleanup(TestBrainstormService):
    """Test driver cleanup on session deletion."""

    async def test_delete_session_calls_cleanup(
        self,
        service_with_cleanup: BrainstormService,
        mock_repository: MagicMock,
        mock_cleanup: MagicMock,
    ) -> None:
        """Should call driver cleanup when deleting session with driver_session_id."""
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            driver_type="claude",
            driver_session_id="driver-sess-123",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session

        await service_with_cleanup.delete_session(sess_id)

        mock_cleanup.assert_called_once_with("claude", "driver-sess-123")

    async def test_delete_session_skips_cleanup_without_driver_session(
        self,
        service_with_cleanup: BrainstormService,
        mock_repository: MagicMock,
        mock_cleanup: MagicMock,
    ) -> None:
        """Should not call cleanup when session has no driver_session_id."""
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            driver_session_id=None,
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session

        await service_with_cleanup.delete_session(sess_id)

        mock_cleanup.assert_not_called()

    async def test_delete_session_continues_if_cleanup_fails(
        self,
        service_with_cleanup: BrainstormService,
        mock_repository: MagicMock,
        mock_cleanup: MagicMock,
    ) -> None:
        """Should still delete session even if cleanup callback fails."""
        # Setup: make cleanup raise an exception
        mock_cleanup.side_effect = Exception("cleanup failed")

        # Create a session with driver_type and driver_session_id
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            driver_type="claude",
            driver_session_id="driver-sess-123",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session

        # Should not raise, should still delete the session
        await service_with_cleanup.delete_session(sess_id)

        # Verify cleanup was attempted
        mock_cleanup.assert_called_once_with("claude", "driver-sess-123")
        # Verify session was still deleted despite cleanup failure
        mock_repository.delete_session.assert_called_once_with(sess_id)


class TestUpdateSessionStatusCleanup(TestBrainstormService):
    """Test driver cleanup on terminal status."""

    @pytest.mark.parametrize("terminal_status", [SessionStatus.COMPLETED, SessionStatus.FAILED])
    async def test_cleanup_called_on_terminal_status(
        self,
        service_with_cleanup: BrainstormService,
        mock_repository: MagicMock,
        mock_cleanup: MagicMock,
        terminal_status: SessionStatus,
    ) -> None:
        """Should call driver cleanup when status becomes terminal."""
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            driver_type="claude",
            driver_session_id="driver-sess-123",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session

        await service_with_cleanup.update_session_status(sess_id, terminal_status)

        mock_cleanup.assert_called_once_with("claude", "driver-sess-123")

    async def test_cleanup_not_called_on_active_status(
        self,
        service_with_cleanup: BrainstormService,
        mock_repository: MagicMock,
        mock_cleanup: MagicMock,
    ) -> None:
        """Should not call cleanup when status is not terminal."""
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            driver_session_id="driver-sess-123",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session

        await service_with_cleanup.update_session_status(sess_id, SessionStatus.ACTIVE)

        mock_cleanup.assert_not_called()


class TestNoPrimeSession:
    """Tests verifying prime_session is removed."""

    def test_service_has_no_prime_session_method(self) -> None:
        """BrainstormService should not have prime_session method."""
        from amelia.server.services.brainstorm import BrainstormService
        assert not hasattr(BrainstormService, "prime_session")


class TestGetSessionWithHistory(TestBrainstormService):
    """Test get_session_with_history returns messages correctly."""

    async def test_get_session_with_history_returns_messages(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """get_session_with_history should return all messages."""
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = []
        mock_repository.get_session_usage.return_value = None

        mock_repository.get_messages.return_value = [
            Message(
                id=uuid4(),
                session_id=sess_id,
                sequence=1,
                role=MessageRole.USER,
                content="User's message",
                created_at=now,
            ),
            Message(
                id=uuid4(),
                session_id=sess_id,
                sequence=2,
                role=MessageRole.ASSISTANT,
                content="Assistant response",
                created_at=now,
            ),
        ]

        result = await service.get_session_with_history(sess_id)

        # Verify get_messages was called
        mock_repository.get_messages.assert_called_once()

        # Verify result contains messages
        assert result is not None
        assert len(result["messages"]) == 2


class TestGetSessionWithHistoryNoFiltering(TestBrainstormService):
    """Tests verifying system message filtering is removed."""

    async def test_get_messages_called_without_include_system(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
    ) -> None:
        """get_messages should be called without include_system parameter.

        System message filtering is no longer needed since priming is removed.
        The repository's get_messages method now returns all messages.
        """
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_artifacts.return_value = []
        mock_repository.get_messages.return_value = []
        mock_repository.get_session_usage.return_value = None

        await service.get_session_with_history(sess_id)

        # Verify get_messages was called with only the session_id
        # (no include_system parameter should be passed)
        mock_repository.get_messages.assert_called_once_with(sess_id)


class TestSendMessageNewArchitecture:
    """Tests for send_message with new prompt architecture."""

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
        repo.get_session_usage = AsyncMock(return_value=None)
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

    def test_send_message_has_no_is_system_param(self) -> None:
        """send_message should not have is_system parameter."""
        import inspect

        sig = inspect.signature(BrainstormService.send_message)
        assert "is_system" not in sig.parameters

    async def test_first_message_uses_template(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """First message (max_seq == 0) should prepend 'Help me design:' template."""
        from amelia.server.services.brainstorm import BRAINSTORMER_USER_PROMPT_TEMPLATE

        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0  # First message

        # Create a mock driver that captures the prompt
        captured_prompts: list[str] = []

        async def mock_execute_agentic(
            prompt: str, **kwargs: object
        ) -> AsyncIterator[AgenticMessage]:
            from amelia.drivers.base import AgenticMessageType

            captured_prompts.append(prompt)
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Response",
                session_id="sess-driver-1",
            )

        mock_driver = MagicMock()
        mock_driver.execute_agentic = mock_execute_agentic
        mock_driver.get_usage = MagicMock(return_value=None)

        async for _ in service.send_message(
            session_id=sess_id,
            content="a caching layer",
            driver=mock_driver,
            cwd="/tmp/project",
        ):
            pass

        # Verify prompt was formatted with template
        expected = BRAINSTORMER_USER_PROMPT_TEMPLATE.format(idea="a caching layer")
        assert len(captured_prompts) == 1
        assert captured_prompts[0] == expected

    async def test_subsequent_message_uses_content_directly(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Subsequent messages (max_seq > 0) should use content directly."""
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 2  # Not first message

        # Create a mock driver that captures the prompt
        captured_prompts: list[str] = []

        async def mock_execute_agentic(
            prompt: str, **kwargs: object
        ) -> AsyncIterator[AgenticMessage]:
            from amelia.drivers.base import AgenticMessageType

            captured_prompts.append(prompt)
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Response",
                session_id="sess-driver-1",
            )

        mock_driver = MagicMock()
        mock_driver.execute_agentic = mock_execute_agentic
        mock_driver.get_usage = MagicMock(return_value=None)

        async for _ in service.send_message(
            session_id=sess_id,
            content="Yes, use Redis",
            driver=mock_driver,
            cwd="/tmp/project",
        ):
            pass

        # Verify prompt was NOT formatted with template
        assert len(captured_prompts) == 1
        assert captured_prompts[0] == "Yes, use Redis"

    async def test_system_prompt_always_passed(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Instructions should contain BRAINSTORMER_SYSTEM_PROMPT content with resolved path."""
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0

        # Create a mock driver that captures the instructions
        captured_instructions: list[str | None] = []

        async def mock_execute_agentic(
            prompt: str, instructions: str | None = None, **kwargs: object
        ) -> AsyncIterator[AgenticMessage]:
            from amelia.drivers.base import AgenticMessageType

            captured_instructions.append(instructions)
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Response",
                session_id="sess-driver-1",
            )

        mock_driver = MagicMock()
        mock_driver.execute_agentic = mock_execute_agentic
        mock_driver.get_usage = MagicMock(return_value=None)

        async for _ in service.send_message(
            session_id=sess_id,
            content="a caching layer",
            driver=mock_driver,
            cwd="/tmp/project",
        ):
            pass

        # Verify instructions contain system prompt content (with resolved path)
        assert len(captured_instructions) == 1
        assert captured_instructions[0] is not None
        assert "design collaborator" in captured_instructions[0]
        assert "Write the validated design to" in captured_instructions[0]

    async def test_user_message_stored_with_original_content(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """User message in DB should store original content, not formatted prompt."""
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0  # First message

        async def mock_execute_agentic(
            prompt: str, **kwargs: object
        ) -> AsyncIterator[AgenticMessage]:
            from amelia.drivers.base import AgenticMessageType

            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Response",
                session_id="sess-driver-1",
            )

        mock_driver = MagicMock()
        mock_driver.execute_agentic = mock_execute_agentic
        mock_driver.get_usage = MagicMock(return_value=None)

        async for _ in service.send_message(
            session_id=sess_id,
            content="a caching layer",
            driver=mock_driver,
            cwd="/tmp/project",
        ):
            pass

        # Verify user message stored original content
        save_calls = mock_repository.save_message.call_args_list
        user_msg = save_calls[0][0][0]
        assert user_msg.content == "a caching layer"
        assert user_msg.role == MessageRole.USER

    async def test_user_message_has_no_is_system_field(
        self,
        service: BrainstormService,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """User message should not have is_system=True (field removed or False)."""
        now = datetime.now(UTC)
        sess_id = uuid4()
        mock_session = BrainstormingSession(
            id=sess_id,
            profile_id="work",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        mock_repository.get_session.return_value = mock_session
        mock_repository.get_max_sequence.return_value = 0

        async def mock_execute_agentic(
            prompt: str, **kwargs: object
        ) -> AsyncIterator[AgenticMessage]:
            from amelia.drivers.base import AgenticMessageType

            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Response",
                session_id="sess-driver-1",
            )

        mock_driver = MagicMock()
        mock_driver.execute_agentic = mock_execute_agentic
        mock_driver.get_usage = MagicMock(return_value=None)

        async for _ in service.send_message(
            session_id=sess_id,
            content="a caching layer",
            driver=mock_driver,
            cwd="/tmp/project",
        ):
            pass

        # Verify user message does not have is_system=True
        save_calls = mock_repository.save_message.call_args_list
        user_msg = save_calls[0][0][0]
        # Either is_system field is absent or defaults to False
        assert not getattr(user_msg, "is_system", False)


class TestSendMessagePlanPath:
    """Tests for plan path resolution in send_message."""

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
        repo.get_session_usage = AsyncMock(return_value=None)
        return repo

    @pytest.fixture
    def mock_event_bus(self) -> MagicMock:
        """Create mock event bus."""
        bus = MagicMock()
        bus.emit = MagicMock()
        return bus

    @pytest.fixture
    def mock_profile_repo(self) -> MagicMock:
        """Create mock profile repository."""
        from amelia.core.types import Profile

        profile = Profile(
            name="work",
            repo_root="/tmp/project",
            plan_path_pattern="plans/{date}-{issue_key}-design.md",
        )
        repo = MagicMock()
        repo.get_profile = AsyncMock(return_value=profile)
        return repo

    @pytest.fixture
    def _make_session(self) -> object:
        """Factory for brainstorming sessions."""

        def _factory(
            topic: str | None = None, session_id: str | None = None
        ) -> BrainstormingSession:
            from uuid import UUID as _UUID

            now = datetime.now(UTC)
            sid = _UUID(session_id) if session_id else uuid4()
            return BrainstormingSession(
                id=sid,
                profile_id="work",
                status=SessionStatus.ACTIVE,
                topic=topic,
                created_at=now,
                updated_at=now,
            )

        return _factory

    @staticmethod
    def _make_driver() -> tuple[MagicMock, list[str | None]]:
        """Create mock driver that captures instructions."""
        captured: list[str | None] = []

        async def mock_execute_agentic(
            prompt: str, instructions: str | None = None, **kwargs: object
        ) -> AsyncIterator[AgenticMessage]:
            from amelia.drivers.base import AgenticMessageType

            captured.append(instructions)
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Response",
                session_id="sess-driver-1",
            )

        driver = MagicMock()
        driver.execute_agentic = mock_execute_agentic
        driver.get_usage = MagicMock(return_value=None)
        return driver, captured

    async def test_instructions_include_resolved_plan_path(
        self,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
        mock_profile_repo: MagicMock,
        _make_session: object,
    ) -> None:
        """With profile and topic, instructions contain the resolved path."""
        service = BrainstormService(
            mock_repository, mock_event_bus, profile_repo=mock_profile_repo
        )
        session = _make_session(topic="caching layer")  # type: ignore[operator]
        mock_repository.get_session.return_value = session

        driver, captured = self._make_driver()

        async for _ in service.send_message(
            session_id=session.id,
            content="a caching layer",
            driver=driver,
            cwd="/tmp/project",
        ):
            pass

        assert len(captured) == 1
        instructions = captured[0]
        assert instructions is not None
        # Path should contain profile pattern with slugified topic
        assert "plans/" in instructions
        assert "caching-layer" in instructions
        assert "-design.md" in instructions

        # Verify output_artifact_path was persisted on session
        update_calls = mock_repository.update_session.call_args_list
        # First update_session call stores the artifact path
        updated_session = update_calls[0][0][0]
        assert updated_session.output_artifact_path is not None
        assert "caching-layer" in updated_session.output_artifact_path

    async def test_instructions_use_session_id_fallback_when_no_topic(
        self,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
        mock_profile_repo: MagicMock,
        _make_session: object,
    ) -> None:
        """Without topic, path uses brainstorm-{id[:8]} fallback."""
        service = BrainstormService(
            mock_repository, mock_event_bus, profile_repo=mock_profile_repo
        )
        session = _make_session(topic=None, session_id="abcd1234-0000-0000-0000-000000000000")  # type: ignore[operator]
        mock_repository.get_session.return_value = session

        driver, captured = self._make_driver()

        async for _ in service.send_message(
            session_id=session.id,
            content="an idea",
            driver=driver,
            cwd="/tmp/project",
        ):
            pass

        assert len(captured) == 1
        instructions = captured[0]
        assert instructions is not None
        assert "brainstorm-abcd1234" in instructions

        # Verify output_artifact_path was persisted on session
        update_calls = mock_repository.update_session.call_args_list
        updated_session = update_calls[0][0][0]
        assert updated_session.output_artifact_path is not None
        assert "brainstorm-abcd1234" in updated_session.output_artifact_path

    async def test_instructions_use_default_pattern_without_profile_repo(
        self,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
        _make_session: object,
    ) -> None:
        """Without profile_repo, falls back to default pattern."""
        service = BrainstormService(mock_repository, mock_event_bus)
        session = _make_session(topic="auth system")  # type: ignore[operator]
        mock_repository.get_session.return_value = session

        driver, captured = self._make_driver()

        async for _ in service.send_message(
            session_id=session.id,
            content="auth system",
            driver=driver,
            cwd="/tmp/project",
        ):
            pass

        assert len(captured) == 1
        instructions = captured[0]
        assert instructions is not None
        # Default pattern: docs/plans/{date}-{issue_key}.md
        assert "docs/plans/" in instructions
        assert "auth-system" in instructions

        # Verify output_artifact_path was persisted on session
        update_calls = mock_repository.update_session.call_args_list
        updated_session = update_calls[0][0][0]
        assert updated_session.output_artifact_path is not None
        assert "auth-system" in updated_session.output_artifact_path

    async def test_reuses_stored_path_on_subsequent_messages(
        self,
        mock_repository: MagicMock,
        mock_event_bus: MagicMock,
        mock_profile_repo: MagicMock,
        _make_session: object,
    ) -> None:
        """On subsequent messages, should reuse stored output_artifact_path."""
        service = BrainstormService(
            mock_repository, mock_event_bus, profile_repo=mock_profile_repo
        )
        session = _make_session(topic="caching layer")  # type: ignore[operator]
        session.output_artifact_path = "plans/existing-plan.md"
        mock_repository.get_session.return_value = session
        mock_repository.get_max_sequence.return_value = 1  # Not first message

        driver, captured = self._make_driver()

        async for _ in service.send_message(
            session_id=session.id,
            content="continue please",
            driver=driver,
            cwd="/tmp/project",
        ):
            pass

        assert len(captured) == 1
        instructions = captured[0]
        assert instructions is not None
        assert "plans/existing-plan.md" in instructions
