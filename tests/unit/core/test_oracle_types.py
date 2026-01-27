"""Tests for OracleConsultation model."""

from datetime import UTC, datetime

from amelia.core.types import OracleConsultation


class TestOracleConsultation:
    """Tests for OracleConsultation Pydantic model."""

    def test_minimal_construction(self):
        """OracleConsultation should construct with required fields only."""
        consultation = OracleConsultation(
            timestamp=datetime.now(tz=UTC),
            problem="How should I refactor the auth module?",
            model="claude-sonnet-4-20250514",
            session_id="abc-123",
        )
        assert consultation.problem == "How should I refactor the auth module?"
        assert consultation.model == "claude-sonnet-4-20250514"
        assert consultation.session_id == "abc-123"
        assert consultation.advice is None
        assert consultation.tokens == {}
        assert consultation.cost_usd is None
        assert consultation.files_consulted == []
        assert consultation.outcome == "success"
        assert consultation.error_message is None

    def test_full_construction(self):
        """OracleConsultation should accept all optional fields."""
        consultation = OracleConsultation(
            timestamp=datetime.now(tz=UTC),
            problem="Refactor auth",
            advice="Use dependency injection.",
            model="claude-sonnet-4-20250514",
            session_id="abc-123",
            tokens={"input": 1000, "output": 500},
            cost_usd=0.015,
            files_consulted=["src/auth.py", "src/middleware.py"],
            outcome="success",
        )
        assert consultation.advice == "Use dependency injection."
        assert consultation.tokens == {"input": 1000, "output": 500}
        assert consultation.cost_usd == 0.015
        assert consultation.files_consulted == ["src/auth.py", "src/middleware.py"]

    def test_error_outcome(self):
        """OracleConsultation should record error state."""
        consultation = OracleConsultation(
            timestamp=datetime.now(tz=UTC),
            problem="Analyze this",
            model="claude-sonnet-4-20250514",
            session_id="abc-123",
            outcome="error",
            error_message="Driver timeout",
        )
        assert consultation.outcome == "error"
        assert consultation.error_message == "Driver timeout"
