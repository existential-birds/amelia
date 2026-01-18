"""Tests for brainstorming event types."""

from amelia.server.models.events import EventType


class TestBrainstormEventTypes:
    """Test brainstorming event types exist."""

    def test_brainstorm_session_created_exists(self) -> None:
        """EventType should include BRAINSTORM_SESSION_CREATED."""
        assert hasattr(EventType, "BRAINSTORM_SESSION_CREATED")
        assert EventType.BRAINSTORM_SESSION_CREATED == "brainstorm_session_created"

    def test_brainstorm_reasoning_exists(self) -> None:
        """EventType should include BRAINSTORM_REASONING."""
        assert hasattr(EventType, "BRAINSTORM_REASONING")
        assert EventType.BRAINSTORM_REASONING == "brainstorm_reasoning"

    def test_brainstorm_tool_call_exists(self) -> None:
        """EventType should include BRAINSTORM_TOOL_CALL."""
        assert hasattr(EventType, "BRAINSTORM_TOOL_CALL")
        assert EventType.BRAINSTORM_TOOL_CALL == "brainstorm_tool_call"

    def test_brainstorm_tool_result_exists(self) -> None:
        """EventType should include BRAINSTORM_TOOL_RESULT."""
        assert hasattr(EventType, "BRAINSTORM_TOOL_RESULT")
        assert EventType.BRAINSTORM_TOOL_RESULT == "brainstorm_tool_result"

    def test_brainstorm_text_exists(self) -> None:
        """EventType should include BRAINSTORM_TEXT."""
        assert hasattr(EventType, "BRAINSTORM_TEXT")
        assert EventType.BRAINSTORM_TEXT == "brainstorm_text"

    def test_brainstorm_message_complete_exists(self) -> None:
        """EventType should include BRAINSTORM_MESSAGE_COMPLETE."""
        assert hasattr(EventType, "BRAINSTORM_MESSAGE_COMPLETE")
        assert EventType.BRAINSTORM_MESSAGE_COMPLETE == "brainstorm_message_complete"

    def test_brainstorm_artifact_created_exists(self) -> None:
        """EventType should include BRAINSTORM_ARTIFACT_CREATED."""
        assert hasattr(EventType, "BRAINSTORM_ARTIFACT_CREATED")
        assert EventType.BRAINSTORM_ARTIFACT_CREATED == "brainstorm_artifact_created"

    def test_brainstorm_session_completed_exists(self) -> None:
        """EventType should include BRAINSTORM_SESSION_COMPLETED."""
        assert hasattr(EventType, "BRAINSTORM_SESSION_COMPLETED")
        assert EventType.BRAINSTORM_SESSION_COMPLETED == "brainstorm_session_completed"
