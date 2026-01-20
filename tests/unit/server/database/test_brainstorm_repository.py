"""Tests for BrainstormRepository."""

from datetime import UTC, datetime

import pytest

from amelia.server.database.brainstorm_repository import BrainstormRepository
from amelia.server.database.connection import Database
from amelia.server.models.brainstorm import (
    Artifact,
    BrainstormingSession,
    Message,
    MessagePart,
)


class TestBrainstormRepository:
    """Test BrainstormRepository CRUD operations."""

    @pytest.fixture
    async def db(self, temp_db_path) -> Database:
        """Create database with schema."""
        async with Database(temp_db_path) as db:
            await db.ensure_schema()
            yield db

    @pytest.fixture
    def repository(self, db: Database) -> BrainstormRepository:
        """Create repository instance."""
        return BrainstormRepository(db)

    @pytest.fixture
    def sample_session(self) -> BrainstormingSession:
        """Create a sample session for testing."""
        now = datetime.now(UTC)
        return BrainstormingSession(
            id="sess-test-123",
            profile_id="work",
            status="active",
            topic="Design a caching layer",
            created_at=now,
            updated_at=now,
        )


class TestSessionCRUD(TestBrainstormRepository):
    """Test session CRUD operations."""

    async def test_create_session(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should create a new session."""
        await repository.create_session(sample_session)

        result = await repository.get_session(sample_session.id)
        assert result is not None
        assert result.id == sample_session.id
        assert result.profile_id == "work"
        assert result.status == "active"
        assert result.topic == "Design a caching layer"

    async def test_get_session_not_found(
        self, repository: BrainstormRepository
    ) -> None:
        """Should return None for non-existent session."""
        result = await repository.get_session("nonexistent")
        assert result is None

    async def test_update_session(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should update session fields."""
        await repository.create_session(sample_session)

        sample_session.status = "ready_for_handoff"
        sample_session.driver_session_id = "claude-sess-456"
        sample_session.updated_at = datetime.now(UTC)

        await repository.update_session(sample_session)

        result = await repository.get_session(sample_session.id)
        assert result is not None
        assert result.status == "ready_for_handoff"
        assert result.driver_session_id == "claude-sess-456"

    async def test_delete_session(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should delete session."""
        await repository.create_session(sample_session)
        await repository.delete_session(sample_session.id)

        result = await repository.get_session(sample_session.id)
        assert result is None

    async def test_list_sessions_by_profile(
        self, repository: BrainstormRepository
    ) -> None:
        """Should list sessions filtered by profile."""
        now = datetime.now(UTC)
        session1 = BrainstormingSession(
            id="sess-1", profile_id="work", status="active",
            created_at=now, updated_at=now,
        )
        session2 = BrainstormingSession(
            id="sess-2", profile_id="personal", status="active",
            created_at=now, updated_at=now,
        )
        await repository.create_session(session1)
        await repository.create_session(session2)

        work_sessions = await repository.list_sessions(profile_id="work")
        assert len(work_sessions) == 1
        assert work_sessions[0].id == "sess-1"

    async def test_list_sessions_by_status(
        self, repository: BrainstormRepository
    ) -> None:
        """Should list sessions filtered by status."""
        now = datetime.now(UTC)
        session1 = BrainstormingSession(
            id="sess-1", profile_id="work", status="active",
            created_at=now, updated_at=now,
        )
        session2 = BrainstormingSession(
            id="sess-2", profile_id="work", status="completed",
            created_at=now, updated_at=now,
        )
        await repository.create_session(session1)
        await repository.create_session(session2)

        active_sessions = await repository.list_sessions(status="active")
        assert len(active_sessions) == 1
        assert active_sessions[0].id == "sess-1"


class TestMessageCRUD(TestBrainstormRepository):
    """Test message CRUD operations."""

    async def test_save_message(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should save a message."""
        await repository.create_session(sample_session)

        message = Message(
            id="msg-1",
            session_id=sample_session.id,
            sequence=1,
            role="user",
            content="Design a caching layer",
            created_at=datetime.now(UTC),
        )
        await repository.save_message(message)

        messages = await repository.get_messages(sample_session.id)
        assert len(messages) == 1
        assert messages[0].content == "Design a caching layer"

    async def test_save_message_with_parts(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should save message with parts."""
        await repository.create_session(sample_session)

        message = Message(
            id="msg-2",
            session_id=sample_session.id,
            sequence=1,
            role="assistant",
            content="Here's my analysis...",
            parts=[
                MessagePart(type="reasoning", text="Let me think..."),
                MessagePart(type="text", text="Here's my analysis..."),
            ],
            created_at=datetime.now(UTC),
        )
        await repository.save_message(message)

        messages = await repository.get_messages(sample_session.id)
        assert len(messages) == 1
        assert messages[0].parts is not None
        assert len(messages[0].parts) == 2
        assert messages[0].parts[0].type == "reasoning"

    async def test_get_messages_ordered(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should return messages in sequence order."""
        await repository.create_session(sample_session)

        for i in range(3, 0, -1):  # Insert in reverse order
            msg = Message(
                id=f"msg-{i}",
                session_id=sample_session.id,
                sequence=i,
                role="user" if i % 2 else "assistant",
                content=f"Message {i}",
                created_at=datetime.now(UTC),
            )
            await repository.save_message(msg)

        messages = await repository.get_messages(sample_session.id)
        assert [m.sequence for m in messages] == [1, 2, 3]

    async def test_get_max_sequence(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should return max sequence number."""
        await repository.create_session(sample_session)

        # No messages yet
        assert await repository.get_max_sequence(sample_session.id) == 0

        # Add messages
        for i in range(1, 4):
            msg = Message(
                id=f"msg-{i}",
                session_id=sample_session.id,
                sequence=i,
                role="user",
                content=f"Message {i}",
                created_at=datetime.now(UTC),
            )
            await repository.save_message(msg)

        assert await repository.get_max_sequence(sample_session.id) == 3

    async def test_save_message_with_is_system(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should save and retrieve message with is_system flag."""
        await repository.create_session(sample_session)

        # Save a system message
        system_msg = Message(
            id="msg-system-1",
            session_id=sample_session.id,
            sequence=1,
            role="user",
            content="System priming content",
            is_system=True,
            created_at=datetime.now(UTC),
        )
        await repository.save_message(system_msg)

        # Save a regular message
        regular_msg = Message(
            id="msg-regular-1",
            session_id=sample_session.id,
            sequence=2,
            role="user",
            content="User authored content",
            is_system=False,
            created_at=datetime.now(UTC),
        )
        await repository.save_message(regular_msg)

        messages = await repository.get_messages(sample_session.id)
        assert len(messages) == 2
        assert messages[0].is_system is True
        assert messages[1].is_system is False

    async def test_get_messages_include_system_default(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should include system messages by default."""
        await repository.create_session(sample_session)

        # Save system and regular messages
        for i, is_sys in [(1, True), (2, False), (3, True)]:
            msg = Message(
                id=f"msg-{i}",
                session_id=sample_session.id,
                sequence=i,
                role="user",
                content=f"Message {i}",
                is_system=is_sys,
                created_at=datetime.now(UTC),
            )
            await repository.save_message(msg)

        messages = await repository.get_messages(sample_session.id)
        assert len(messages) == 3

    async def test_get_messages_exclude_system(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should filter out system messages when include_system=False."""
        await repository.create_session(sample_session)

        # Save system and regular messages
        for i, is_sys in [(1, True), (2, False), (3, True), (4, False)]:
            msg = Message(
                id=f"msg-{i}",
                session_id=sample_session.id,
                sequence=i,
                role="user",
                content=f"Message {i}",
                is_system=is_sys,
                created_at=datetime.now(UTC),
            )
            await repository.save_message(msg)

        messages = await repository.get_messages(sample_session.id, include_system=False)
        assert len(messages) == 2
        assert all(not m.is_system for m in messages)
        assert [m.sequence for m in messages] == [2, 4]

    async def test_is_system_defaults_to_false(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should default is_system to False when not specified."""
        await repository.create_session(sample_session)

        message = Message(
            id="msg-1",
            session_id=sample_session.id,
            sequence=1,
            role="user",
            content="Regular message",
            created_at=datetime.now(UTC),
        )
        await repository.save_message(message)

        messages = await repository.get_messages(sample_session.id)
        assert len(messages) == 1
        assert messages[0].is_system is False


class TestArtifactCRUD(TestBrainstormRepository):
    """Test artifact CRUD operations."""

    async def test_save_artifact(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should save an artifact."""
        await repository.create_session(sample_session)

        artifact = Artifact(
            id="art-1",
            session_id=sample_session.id,
            type="design",
            path="docs/plans/design.md",
            title="Caching Design",
            created_at=datetime.now(UTC),
        )
        await repository.save_artifact(artifact)

        artifacts = await repository.get_artifacts(sample_session.id)
        assert len(artifacts) == 1
        assert artifacts[0].path == "docs/plans/design.md"

    async def test_get_artifacts_empty(
        self, repository: BrainstormRepository, sample_session: BrainstormingSession
    ) -> None:
        """Should return empty list for session with no artifacts."""
        await repository.create_session(sample_session)
        artifacts = await repository.get_artifacts(sample_session.id)
        assert artifacts == []
