"""Tests for workflow state models."""

from datetime import datetime
from typing import Any

import pytest

from amelia.server.models.state import (
    InvalidStateTransitionError,
    PlanCache,
    ServerExecutionState,
    WorkflowStatus,
    validate_transition,
)


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
            ("pending", "blocked"),
            ("pending", "cancelled"),
            ("pending", "failed"),  # Workflows can fail during startup
            ("in_progress", "blocked"),
            ("in_progress", "completed"),
            ("in_progress", "failed"),
            ("in_progress", "cancelled"),
            ("blocked", "pending"),
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
            ("in_progress", "pending"),
            ("in_progress", "in_progress"),
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

    @pytest.mark.parametrize("terminal", ["completed", "cancelled"])
    def test_terminal_states_cannot_transition(self, terminal: WorkflowStatus) -> None:
        """Terminal states cannot transition to any other state."""
        all_states: list[WorkflowStatus] = [
            WorkflowStatus.PENDING,
            WorkflowStatus.IN_PROGRESS,
            WorkflowStatus.BLOCKED,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        ]
        for target in all_states:
            if target != terminal:
                with pytest.raises(InvalidStateTransitionError):
                    validate_transition(terminal, target)

    def test_failed_only_allows_in_progress(self) -> None:
        """FAILED state can only transition to IN_PROGRESS (for resume)."""
        all_states: list[WorkflowStatus] = [
            WorkflowStatus.PENDING,
            WorkflowStatus.BLOCKED,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        ]
        # These should all be invalid
        for target in all_states:
            with pytest.raises(InvalidStateTransitionError):
                validate_transition(WorkflowStatus.FAILED, target)
        # Only IN_PROGRESS is valid (for resume)
        validate_transition(WorkflowStatus.FAILED, WorkflowStatus.IN_PROGRESS)


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


class TestPlanCache:
    """Tests for PlanCache model."""

    def test_create_plan_cache_with_defaults(self) -> None:
        """PlanCache can be created with all defaults."""
        cache = PlanCache()

        assert cache.goal is None
        assert cache.plan_markdown is None
        assert cache.plan_path is None
        assert cache.total_tasks is None
        assert cache.current_task_index is None

    def test_create_plan_cache_with_values(self) -> None:
        """PlanCache can be created with explicit values."""
        cache = PlanCache(
            goal="Implement feature X",
            plan_markdown="# Plan\n- Step 1",
            plan_path="/path/to/plan.md",
            total_tasks=5,
            current_task_index=2,
        )

        assert cache.goal == "Implement feature X"
        assert cache.plan_markdown == "# Plan\n- Step 1"
        assert cache.plan_path == "/path/to/plan.md"
        assert cache.total_tasks == 5
        assert cache.current_task_index == 2

    def test_plan_cache_json_round_trip(self) -> None:
        """PlanCache survives JSON serialization round-trip."""
        original = PlanCache(
            goal="Test goal",
            plan_markdown="# Test Plan",
            total_tasks=3,
        )

        json_str = original.model_dump_json()
        restored = PlanCache.model_validate_json(json_str)

        assert restored.goal == original.goal
        assert restored.plan_markdown == original.plan_markdown
        assert restored.total_tasks == original.total_tasks

    def test_from_checkpoint_values(self) -> None:
        """from_checkpoint_values reads plan_path directly from values."""
        values = {
            "goal": "Test goal",
            "plan_markdown": "# Plan",
            "plan_path": "/path/to/plan.md",
            "total_tasks": 5,
            "current_task_index": 1,
        }

        cache = PlanCache.from_checkpoint_values(values)

        assert cache.goal == "Test goal"
        assert cache.plan_markdown == "# Plan"
        assert cache.plan_path == "/path/to/plan.md"
        assert cache.total_tasks == 5
        assert cache.current_task_index == 1

    def test_from_checkpoint_values_handles_missing_values(self) -> None:
        """from_checkpoint_values handles missing values gracefully."""
        values: dict[str, Any] = {}

        cache = PlanCache.from_checkpoint_values(values)

        assert cache.goal is None
        assert cache.plan_markdown is None
        assert cache.plan_path is None


class TestServerExecutionStateWithNewFields:
    """Tests for ServerExecutionState new fields (profile_id, plan_cache, issue_cache)."""

    def test_state_with_profile_id(self) -> None:
        """ServerExecutionState accepts profile_id field."""
        state = make_state(profile_id="test-profile")

        assert state.profile_id == "test-profile"

    def test_state_with_plan_cache(self) -> None:
        """ServerExecutionState accepts plan_cache field."""
        plan_cache = PlanCache(goal="Test goal", plan_markdown="# Plan")
        state = make_state(plan_cache=plan_cache)

        assert state.plan_cache is not None
        assert state.plan_cache.goal == "Test goal"
        assert state.plan_cache.plan_markdown == "# Plan"

    def test_state_with_issue_cache(self) -> None:
        """ServerExecutionState accepts issue_cache field."""
        issue_json = '{"key": "TEST-1", "summary": "Test issue"}'
        state = make_state(issue_cache=issue_json)

        assert state.issue_cache == issue_json

    def test_state_json_round_trip_with_new_fields(self) -> None:
        """State with new fields survives JSON serialization round-trip."""
        plan_cache = PlanCache(goal="Test goal", total_tasks=3)
        original = make_state(
            profile_id="my-profile",
            plan_cache=plan_cache,
            issue_cache='{"key": "TEST-1"}',
        )

        json_str = original.model_dump_json()
        restored = ServerExecutionState.model_validate_json(json_str)

        assert restored.profile_id == "my-profile"
        assert restored.plan_cache is not None
        assert restored.plan_cache.goal == "Test goal"
        assert restored.issue_cache == '{"key": "TEST-1"}'

