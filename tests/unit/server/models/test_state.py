"""Tests for workflow state models."""

from datetime import UTC, datetime
from typing import Any

import pytest

from amelia.core.types import AgentConfig, Profile
from amelia.pipelines.implementation.state import ImplementationState
from amelia.server.models.state import (
    InvalidStateTransitionError,
    ServerExecutionState,
    WorkflowStatus,
    rebuild_server_execution_state,
    validate_transition,
)


# Resolve forward references for ImplementationState
rebuild_server_execution_state()


def make_state(**overrides: Any) -> ServerExecutionState:
    """Create a ServerExecutionState with sensible defaults."""
    defaults: dict[str, Any] = {
        "id": "wf-123",
        "issue_id": "ISSUE-456",
        "worktree_path": "/path/to/repo",
    }
    return ServerExecutionState(**{**defaults, **overrides})


class TestStateTransitions:
    """Tests for state machine transitions."""

    @pytest.mark.parametrize(
        "current,target",
        [
            ("pending", "in_progress"),
            ("pending", "planning"),
            ("pending", "cancelled"),
            ("pending", "failed"),  # Workflows can fail during startup
            ("planning", "blocked"),
            ("planning", "failed"),
            ("planning", "cancelled"),
            ("in_progress", "blocked"),
            ("in_progress", "completed"),
            ("in_progress", "failed"),
            ("in_progress", "cancelled"),
            ("blocked", "in_progress"),
            ("blocked", "failed"),
            ("blocked", "cancelled"),
        ],
    )
    def test_valid_transitions(
        self, current: WorkflowStatus, target: WorkflowStatus
    ) -> None:
        """Valid state transitions do not raise."""
        validate_transition(current, target)

    @pytest.mark.parametrize(
        "current,target",
        [
            ("pending", "completed"),
            # ("pending", "failed") is now valid - workflows can fail during startup
            ("pending", "blocked"),
            ("planning", "pending"),
            ("planning", "completed"),
            ("planning", "in_progress"),
            ("in_progress", "pending"),
            ("in_progress", "in_progress"),
            ("blocked", "pending"),
            ("blocked", "completed"),
        ],
    )
    def test_invalid_transitions(
        self, current: WorkflowStatus, target: WorkflowStatus
    ) -> None:
        """Invalid state transitions raise InvalidStateTransitionError."""
        with pytest.raises(InvalidStateTransitionError) as exc:
            validate_transition(current, target)
        assert exc.value.current == current
        assert exc.value.target == target

    @pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled"])
    def test_terminal_states_cannot_transition(self, terminal: WorkflowStatus) -> None:
        """Terminal states cannot transition to any other state."""
        all_states: list[WorkflowStatus] = [
            "pending",
            "planning",
            "in_progress",
            "blocked",
            "completed",
            "failed",
            "cancelled",
        ]
        for target in all_states:
            if target != terminal:
                with pytest.raises(InvalidStateTransitionError):
                    validate_transition(terminal, target)


class TestServerExecutionState:
    """Tests for ServerExecutionState model."""

    def test_create_state(self) -> None:
        """ServerExecutionState can be created with required fields."""
        state = make_state()

        assert state.id == "wf-123"
        assert state.issue_id == "ISSUE-456"
        assert state.worktree_path == "/path/to/repo"
        assert state.workflow_status == "pending"

    def test_state_json_round_trip(self) -> None:
        """State survives JSON serialization round-trip."""
        original = make_state(
            workflow_status="in_progress",
            started_at=datetime(2025, 1, 1, 12, 0, 0),
        )

        json_str = original.model_dump_json()
        restored = ServerExecutionState.model_validate_json(json_str)

        assert restored.id == original.id
        assert restored.issue_id == original.issue_id
        assert restored.workflow_status == original.workflow_status
        assert restored.started_at == original.started_at


class TestServerExecutionStateComposition:
    """Test ServerExecutionState with embedded ImplementationState."""

    def test_server_state_accepts_execution_state(self) -> None:
        """ServerExecutionState can hold an ImplementationState."""
        profile = Profile(
            name="test",
            tracker="noop",
            working_dir="/tmp/test",
            agents={
                "architect": AgentConfig(driver="cli", model="sonnet"),
                "developer": AgentConfig(driver="cli", model="sonnet"),
                "reviewer": AgentConfig(driver="cli", model="sonnet"),
            },
        )
        core_state = ImplementationState(
            workflow_id="wf-123",
            created_at=datetime.now(UTC),
            status="running",
            profile_id=profile.name,
        )
        server_state = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/tmp/test",
            execution_state=core_state,
        )
        assert server_state.execution_state is not None
        assert server_state.execution_state.profile_id == "test"


class TestServerExecutionStatePlannedAt:
    """Tests for planned_at field."""

    def test_planned_at_defaults_to_none(self) -> None:
        """planned_at should default to None for new workflows."""
        state = make_state()
        assert state.planned_at is None

    def test_planned_at_can_be_set(self) -> None:
        """planned_at can be set to a datetime."""
        now = datetime.now(UTC)
        state = make_state(planned_at=now)
        assert state.planned_at == now

    def test_is_planned_property_false_when_no_plan(self) -> None:
        """is_planned should return False when planned_at is None."""
        state = make_state()
        assert state.is_planned is False

    def test_is_planned_property_true_when_planned(self) -> None:
        """is_planned should return True when planned_at is set."""
        state = make_state(planned_at=datetime.now(UTC))
        assert state.is_planned is True

