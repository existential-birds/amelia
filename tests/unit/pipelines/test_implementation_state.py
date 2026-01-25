"""Unit tests for ImplementationState."""

from datetime import UTC, datetime

from amelia.pipelines.implementation.state import ImplementationState


class TestExternalPlanField:
    """Tests for external_plan field on ImplementationState."""

    def test_external_plan_defaults_to_false(self) -> None:
        """external_plan should default to False."""
        state = ImplementationState(
            workflow_id="wf-001",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="pending",
        )
        assert state.external_plan is False

    def test_external_plan_can_be_set_to_true(self) -> None:
        """external_plan can be explicitly set to True."""
        state = ImplementationState(
            workflow_id="wf-001",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="pending",
            external_plan=True,
        )
        assert state.external_plan is True
