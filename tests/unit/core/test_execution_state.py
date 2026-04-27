"""Tests for ImplementationState model."""

from datetime import UTC, datetime
from uuid import uuid4

from amelia.pipelines.implementation.state import ImplementationState


_wf_id = uuid4()


class TestExecutionStatePlanMarkdown:
    """Tests for plan_markdown field (canonical architect output)."""

    def test_plan_markdown_defaults_to_none(self) -> None:
        """plan_markdown should default to None."""
        state = ImplementationState(
            workflow_id=_wf_id,
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
        )
        assert state.plan_markdown is None

    def test_plan_markdown_stores_string(self) -> None:
        """plan_markdown should store markdown string."""
        markdown = "# Plan\n\n**Goal:** Do something"
        state = ImplementationState(
            workflow_id=_wf_id,
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            plan_markdown=markdown,
        )
        assert state.plan_markdown == markdown

    def test_plan_markdown_in_model_copy(self) -> None:
        """plan_markdown should work with model_copy."""
        state = ImplementationState(
            workflow_id=_wf_id,
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
        )
        new_state = state.model_copy(update={"plan_markdown": "# Updated"})
        assert new_state.plan_markdown == "# Updated"
        assert state.plan_markdown is None  # Original unchanged


class TestArchitectErrorField:
    """Tests for architect_error field."""

    def test_architect_error_defaults_to_none(self) -> None:
        """architect_error should default to None."""
        state = ImplementationState(
            workflow_id=_wf_id,
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
        )
        assert state.architect_error is None

    def test_architect_error_stores_error_message(self) -> None:
        """architect_error should store error message string."""
        error_msg = "RuntimeError: LLM call failed"
        state = ImplementationState(
            workflow_id=_wf_id,
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            architect_error=error_msg,
        )
        assert state.architect_error == error_msg

    def test_architect_error_separate_from_plan_markdown(self) -> None:
        """architect_error and plan_markdown should be independent."""
        state = ImplementationState(
            workflow_id=_wf_id,
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            plan_markdown="# Plan content",
            architect_error="Some error occurred",
        )
        assert state.plan_markdown == "# Plan content"
        assert state.architect_error == "Some error occurred"


class TestTaskExecutionFields:
    """Tests for task execution tracking fields."""

    def test_task_execution_fields_have_correct_defaults(self) -> None:
        """Task execution tracking fields should have sensible defaults."""
        state = ImplementationState(
            workflow_id=_wf_id,
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
        )

        assert state.total_tasks == 1  # 1 = single-task mode (default)
        assert state.current_task_index == 0  # 0-indexed
        assert state.task_review_iteration == 0  # Resets per task
        # Note: max_task_review_iterations is on Profile, not ExecutionState

    def test_task_execution_fields_are_settable(self) -> None:
        """Task execution fields should be settable via model_copy."""
        state = ImplementationState(
            workflow_id=_wf_id,
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
        )

        updated = state.model_copy(update={
            "total_tasks": 3,
            "current_task_index": 1,
            "task_review_iteration": 2,
        })

        assert updated.total_tasks == 3
        assert updated.current_task_index == 1
        assert updated.task_review_iteration == 2
