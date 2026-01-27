"""Tests for Oracle event types."""

from amelia.server.models.events import EventDomain, EventLevel, EventType, get_event_level


class TestOracleEventTypes:
    """Tests for Oracle-specific event types."""

    def test_oracle_event_types_exist(self):
        """Oracle event types should be defined in EventType enum."""
        assert EventType.ORACLE_CONSULTATION_STARTED == "oracle_consultation_started"
        assert EventType.ORACLE_CONSULTATION_THINKING == "oracle_consultation_thinking"
        assert EventType.ORACLE_TOOL_CALL == "oracle_tool_call"
        assert EventType.ORACLE_TOOL_RESULT == "oracle_tool_result"
        assert EventType.ORACLE_CONSULTATION_COMPLETED == "oracle_consultation_completed"
        assert EventType.ORACLE_CONSULTATION_FAILED == "oracle_consultation_failed"

    def test_oracle_domain_exists(self):
        """ORACLE domain should be defined in EventDomain."""
        assert EventDomain.ORACLE == "oracle"

    def test_oracle_started_is_info_level(self):
        """ORACLE_CONSULTATION_STARTED should be info level."""
        assert get_event_level(EventType.ORACLE_CONSULTATION_STARTED) == EventLevel.INFO

    def test_oracle_completed_is_info_level(self):
        """ORACLE_CONSULTATION_COMPLETED should be info level."""
        assert get_event_level(EventType.ORACLE_CONSULTATION_COMPLETED) == EventLevel.INFO

    def test_oracle_failed_is_info_level(self):
        """ORACLE_CONSULTATION_FAILED should be info level."""
        assert get_event_level(EventType.ORACLE_CONSULTATION_FAILED) == EventLevel.INFO

    def test_oracle_thinking_is_trace_level(self):
        """ORACLE_CONSULTATION_THINKING should be trace level (streaming)."""
        assert get_event_level(EventType.ORACLE_CONSULTATION_THINKING) == EventLevel.TRACE

    def test_oracle_tool_call_is_trace_level(self):
        """ORACLE_TOOL_CALL should be trace level."""
        assert get_event_level(EventType.ORACLE_TOOL_CALL) == EventLevel.TRACE

    def test_oracle_tool_result_is_trace_level(self):
        """ORACLE_TOOL_RESULT should be trace level."""
        assert get_event_level(EventType.ORACLE_TOOL_RESULT) == EventLevel.TRACE
