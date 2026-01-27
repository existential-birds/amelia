"""Tests for Oracle consultation state integration."""

from datetime import UTC, datetime

from amelia.core.types import OracleConsultation
from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)


# Resolve forward references
rebuild_implementation_state()


class TestOracleConsultationsState:
    """Tests for oracle_consultations field on pipeline state."""

    def test_default_empty(self):
        """oracle_consultations should default to empty list."""
        state = ImplementationState(
            workflow_id="wf-1",
            pipeline_type="implementation",
            profile_id="prof-1",
            created_at=datetime.now(tz=UTC),
            status="pending",
        )
        assert state.oracle_consultations == []

    def test_append_consultation(self):
        """oracle_consultations should support append via model_copy."""
        consultation = OracleConsultation(
            timestamp=datetime.now(tz=UTC),
            problem="How to refactor?",
            advice="Use DI.",
            model="claude-sonnet-4-20250514",
            session_id="sess-1",
        )
        state = ImplementationState(
            workflow_id="wf-1",
            pipeline_type="implementation",
            profile_id="prof-1",
            created_at=datetime.now(tz=UTC),
            status="running",
        )
        updated = state.model_copy(update={
            "oracle_consultations": [consultation],
        })
        assert len(updated.oracle_consultations) == 1
        assert updated.oracle_consultations[0].advice == "Use DI."
