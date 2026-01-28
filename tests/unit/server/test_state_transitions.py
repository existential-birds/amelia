"""Unit tests for state transitions related to planning."""
import pytest

from amelia.server.models.state import (
    InvalidStateTransitionError,
    WorkflowStatus,
    validate_transition,
)


class TestReplanTransition:
    """Tests for BLOCKED -> PENDING transition (replan)."""

    def test_blocked_to_pending_is_valid(self) -> None:
        """BLOCKED -> PENDING should be a valid transition for replan."""
        # Should not raise
        validate_transition(WorkflowStatus.BLOCKED, WorkflowStatus.PENDING)

    def test_pending_to_blocked_is_valid(self) -> None:
        """PENDING -> BLOCKED should be valid (planning complete, awaiting approval)."""
        validate_transition(WorkflowStatus.PENDING, WorkflowStatus.BLOCKED)

    def test_completed_to_pending_is_invalid(self) -> None:
        """Terminal states cannot transition to PENDING."""
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(WorkflowStatus.COMPLETED, WorkflowStatus.PENDING)

    def test_failed_to_pending_is_invalid(self) -> None:
        """Terminal states cannot transition to PENDING."""
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(WorkflowStatus.FAILED, WorkflowStatus.PENDING)
