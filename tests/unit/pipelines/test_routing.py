"""Unit tests for shared routing functions."""

from datetime import UTC, datetime
from typing import Any

from amelia.core.types import ReviewResult
from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)


# Resolve forward references for ImplementationState
rebuild_implementation_state()


class TestRouteAfterReviewOrTask:
    """Tests for route_after_review_or_task function."""

    def _make_state(self, **kwargs: Any) -> ImplementationState:
        """Create test state with defaults."""
        defaults: dict[str, Any] = {
            "workflow_id": "wf-1",
            "profile_id": "default",
            "created_at": datetime.now(UTC),
            "status": "running",
        }
        defaults.update(kwargs)
        return ImplementationState(**defaults)

    def test_legacy_mode_approved_returns_end(self) -> None:
        """In legacy mode (no total_tasks), approved review goes to __end__."""
        from amelia.pipelines.routing import route_after_review_or_task

        state = self._make_state(
            total_tasks=None,
            last_review=ReviewResult(
                reviewer_persona="test",
                approved=True,
                comments=[],
                severity="low",
            ),
        )
        assert route_after_review_or_task(state) == "__end__"

    def test_legacy_mode_rejected_returns_developer(self) -> None:
        """In legacy mode, rejected review loops back to developer."""
        from amelia.pipelines.routing import route_after_review_or_task

        state = self._make_state(
            total_tasks=None,
            last_review=ReviewResult(
                reviewer_persona="test",
                approved=False,
                comments=["Fix this"],
                severity="medium",
            ),
        )
        assert route_after_review_or_task(state) == "developer"

    def test_task_mode_approved_more_tasks_returns_next_task(self) -> None:
        """In task mode with more tasks, approved goes to next_task_node."""
        from amelia.pipelines.routing import route_after_review_or_task

        state = self._make_state(
            total_tasks=3,
            current_task_index=0,
            last_review=ReviewResult(
                reviewer_persona="test",
                approved=True,
                comments=[],
                severity="low",
            ),
        )
        assert route_after_review_or_task(state) == "next_task_node"

    def test_task_mode_approved_last_task_returns_end(self) -> None:
        """In task mode on last task, approved goes to __end__."""
        from amelia.pipelines.routing import route_after_review_or_task

        state = self._make_state(
            total_tasks=3,
            current_task_index=2,
            last_review=ReviewResult(
                reviewer_persona="test",
                approved=True,
                comments=[],
                severity="low",
            ),
        )
        assert route_after_review_or_task(state) == "__end__"
