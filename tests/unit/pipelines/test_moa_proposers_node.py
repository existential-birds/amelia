"""Tests for MoA proposers fan-out (advisory MoA mode)."""

from datetime import UTC, datetime
from uuid import uuid4

from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)


# Resolve forward references
rebuild_implementation_state()


class TestMoAProposerPlansField:
    """Tests for the moa_proposer_plans state field."""

    def test_default_empty(self):
        """moa_proposer_plans should default to an empty list."""
        state = ImplementationState(
            workflow_id=uuid4(),
            pipeline_type="implementation",
            profile_id="prof-1",
            created_at=datetime.now(tz=UTC),
            status="pending",
        )
        assert state.moa_proposer_plans == []

    def test_accepts_list_of_paths(self):
        """moa_proposer_plans should accept and round-trip a list of plan paths."""
        state = ImplementationState(
            workflow_id=uuid4(),
            pipeline_type="implementation",
            profile_id="prof-1",
            created_at=datetime.now(tz=UTC),
            status="pending",
            moa_proposer_plans=["a.md", "b.md"],
        )
        assert state.moa_proposer_plans == ["a.md", "b.md"]
