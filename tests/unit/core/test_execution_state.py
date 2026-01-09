"""Tests for ExecutionState model."""

from amelia.core.state import ExecutionState


class TestExecutionStateRawArchitectOutput:
    """Tests for raw_architect_output field."""

    def test_raw_architect_output_defaults_to_none(self) -> None:
        """raw_architect_output should default to None."""
        state = ExecutionState(profile_id="test")
        assert state.raw_architect_output is None

    def test_raw_architect_output_stores_string(self) -> None:
        """raw_architect_output should store markdown string."""
        markdown = "# Plan\n\n**Goal:** Do something"
        state = ExecutionState(profile_id="test", raw_architect_output=markdown)
        assert state.raw_architect_output == markdown

    def test_raw_architect_output_in_model_copy(self) -> None:
        """raw_architect_output should work with model_copy."""
        state = ExecutionState(profile_id="test")
        new_state = state.model_copy(update={"raw_architect_output": "# Updated"})
        assert new_state.raw_architect_output == "# Updated"
        assert state.raw_architect_output is None  # Original unchanged


class TestTaskExecutionFields:
    """Tests for task execution tracking fields."""

    def test_task_execution_fields_have_correct_defaults(self) -> None:
        """Task execution tracking fields should have sensible defaults."""
        state = ExecutionState(profile_id="test")

        assert state.total_tasks is None  # None = legacy single-session mode
        assert state.current_task_index == 0  # 0-indexed
        assert state.task_review_iteration == 0  # Resets per task
        # Note: max_task_review_iterations is on Profile, not ExecutionState

    def test_task_execution_fields_are_settable(self) -> None:
        """Task execution fields should be settable via model_copy."""
        state = ExecutionState(profile_id="test")

        updated = state.model_copy(update={
            "total_tasks": 3,
            "current_task_index": 1,
            "task_review_iteration": 2,
        })

        assert updated.total_tasks == 3
        assert updated.current_task_index == 1
        assert updated.task_review_iteration == 2
