"""Tests for brainstorming Pydantic models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from amelia.server.models.brainstorm import (
    Artifact,
    BrainstormingSession,
    Message,
    MessagePart,
)


class TestSessionStatus:
    """Test SessionStatus literal type."""

    def test_valid_statuses(self) -> None:
        """SessionStatus should accept valid status values."""
        session = BrainstormingSession(
            id="test-id",
            profile_id="test-profile",
            status="active",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert session.status == "active"

        session.status = "ready_for_handoff"
        assert session.status == "ready_for_handoff"


class TestBrainstormingSession:
    """Test BrainstormingSession model."""

    def test_minimal_session(self) -> None:
        """Session should be created with minimal required fields."""
        now = datetime.now(UTC)
        session = BrainstormingSession(
            id="session-123",
            profile_id="work",
            status="active",
            created_at=now,
            updated_at=now,
        )
        assert session.id == "session-123"
        assert session.profile_id == "work"
        assert session.status == "active"
        assert session.driver_session_id is None
        assert session.topic is None

    def test_full_session(self) -> None:
        """Session should be created with all fields."""
        now = datetime.now(UTC)
        session = BrainstormingSession(
            id="session-123",
            profile_id="work",
            driver_session_id="claude-sess-456",
            status="ready_for_handoff",
            topic="Design a caching layer",
            created_at=now,
            updated_at=now,
        )
        assert session.driver_session_id == "claude-sess-456"
        assert session.topic == "Design a caching layer"

    def test_invalid_status_rejected(self) -> None:
        """Invalid status should raise ValidationError."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            BrainstormingSession(
                id="session-123",
                profile_id="work",
                status="invalid_status",  # type: ignore[arg-type]  # Intentional: testing ValidationError on invalid Literal value
                created_at=now,
                updated_at=now,
            )


class TestMessagePart:
    """Test MessagePart model."""

    def test_text_part(self) -> None:
        """Text part should store text content."""
        part = MessagePart(type="text", text="Hello world")
        assert part.type == "text"
        assert part.text == "Hello world"

    def test_tool_call_part(self) -> None:
        """Tool call part should store tool details."""
        part = MessagePart(
            type="tool-call",
            tool_call_id="call-123",
            tool_name="read_file",
            args={"path": "/tmp/file.txt"},
        )
        assert part.type == "tool-call"
        assert part.tool_call_id == "call-123"
        assert part.tool_name == "read_file"
        assert part.args == {"path": "/tmp/file.txt"}

    def test_tool_result_part(self) -> None:
        """Tool result part should store result details."""
        part = MessagePart(
            type="tool-result",
            tool_call_id="call-123",
            result="file contents here",
        )
        assert part.type == "tool-result"
        assert part.tool_call_id == "call-123"
        assert part.result == "file contents here"

    def test_reasoning_part(self) -> None:
        """Reasoning part should store thinking content."""
        part = MessagePart(type="reasoning", text="Let me think about this...")
        assert part.type == "reasoning"
        assert part.text == "Let me think about this..."


class TestMessage:
    """Test Message model."""

    def test_user_message(self) -> None:
        """User message should be created correctly."""
        msg = Message(
            id="msg-123",
            session_id="session-456",
            sequence=1,
            role="user",
            content="Design a caching layer",
            created_at=datetime.now(UTC),
        )
        assert msg.role == "user"
        assert msg.content == "Design a caching layer"
        assert msg.parts is None

    def test_assistant_message_with_parts(self) -> None:
        """Assistant message should support parts."""
        msg = Message(
            id="msg-124",
            session_id="session-456",
            sequence=2,
            role="assistant",
            content="Here's my analysis...",
            parts=[
                MessagePart(type="reasoning", text="First, let me understand..."),
                MessagePart(type="text", text="Here's my analysis..."),
            ],
            created_at=datetime.now(UTC),
        )
        assert msg.role == "assistant"
        assert msg.parts is not None
        assert len(msg.parts) == 2
        assert msg.parts[0].type == "reasoning"


class TestMessageNoIsSystem:
    """Tests verifying is_system field is removed."""

    def test_message_has_no_is_system_field(self) -> None:
        """Message model should not have is_system field."""
        assert "is_system" not in Message.model_fields


class TestArtifact:
    """Test Artifact model."""

    def test_artifact_creation(self) -> None:
        """Artifact should be created with all fields."""
        artifact = Artifact(
            id="art-123",
            session_id="session-456",
            type="design",
            path="docs/plans/2026-01-18-caching-design.md",
            title="Caching Layer Design",
            created_at=datetime.now(UTC),
        )
        assert artifact.id == "art-123"
        assert artifact.type == "design"
        assert artifact.path == "docs/plans/2026-01-18-caching-design.md"
        assert artifact.title == "Caching Layer Design"

    def test_artifact_without_title(self) -> None:
        """Artifact title should be optional."""
        artifact = Artifact(
            id="art-123",
            session_id="session-456",
            type="spec",
            path="docs/specs/feature.md",
            created_at=datetime.now(UTC),
        )
        assert artifact.title is None
