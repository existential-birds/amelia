"""Unit tests for pipeline routing functions."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from amelia.core.types import AgentConfig, DriverType, Profile, ReviewResult, Severity
from amelia.pipelines.implementation.routing import route_after_start, route_after_task_review
from amelia.pipelines.implementation.state import ImplementationState


class TestRouteAfterStart:
    """Tests for route_after_start routing function."""

    def test_routes_to_architect_when_not_external_plan(self) -> None:
        """Should route to architect when external_plan is False."""
        state = ImplementationState(
            workflow_id=uuid4(),
            profile_id="test",
            created_at=datetime.now(UTC),
            status="pending",
            external_plan=False,
        )
        assert route_after_start(state) == "architect"

    def test_routes_to_plan_validator_when_external_plan(self) -> None:
        """Should route to plan_validator when external_plan is True."""
        state = ImplementationState(
            workflow_id=uuid4(),
            profile_id="test",
            created_at=datetime.now(UTC),
            status="pending",
            external_plan=True,
        )
        assert route_after_start(state) == "plan_validator"


class TestRouteAfterTaskReview:
    """Tests for route_after_task_review routing function."""

    @pytest.fixture
    def profile(self) -> Profile:
        """Profile with task_reviewer max_iterations=2."""
        return Profile(
            name="test",
            repo_root="/tmp/test",
            agents={
                "task_reviewer": AgentConfig(
                    driver=DriverType.CLI, model="sonnet", options={"max_iterations": 2}
                ),
            },
        )

    def test_approved_non_final_task_routes_to_next_task(self, profile: Profile) -> None:
        """Approved + more tasks remaining -> next_task_node."""
        state = ImplementationState(
            workflow_id=uuid4(),
            profile_id="test",
            created_at=datetime.now(UTC),
            status="running",
            current_task_index=0,
            total_tasks=3,
            last_review=ReviewResult(
                reviewer_persona="Agentic", approved=True, comments=[], severity=Severity.NONE
            ),
        )
        assert route_after_task_review(state, profile) == "next_task_node"

    def test_approved_final_task_routes_to_end(self, profile: Profile) -> None:
        """Approved + last task -> __end__."""
        state = ImplementationState(
            workflow_id=uuid4(),
            profile_id="test",
            created_at=datetime.now(UTC),
            status="running",
            current_task_index=2,
            total_tasks=3,
            last_review=ReviewResult(
                reviewer_persona="Agentic", approved=True, comments=[], severity=Severity.NONE
            ),
        )
        assert route_after_task_review(state, profile) == "__end__"

    def test_not_approved_within_iterations_routes_to_developer(self, profile: Profile) -> None:
        """Not approved + iterations remaining -> developer."""
        state = ImplementationState(
            workflow_id=uuid4(),
            profile_id="test",
            created_at=datetime.now(UTC),
            status="running",
            current_task_index=0,
            total_tasks=3,
            task_review_iteration=1,
            last_review=ReviewResult(
                reviewer_persona="Agentic", approved=False, comments=["fix X"], severity=Severity.MAJOR
            ),
        )
        assert route_after_task_review(state, profile) == "developer"

    def test_max_iterations_non_final_task_advances_to_next(self, profile: Profile) -> None:
        """Max iterations on non-final task -> next_task_node (NOT __end__)."""
        state = ImplementationState(
            workflow_id=uuid4(),
            profile_id="test",
            created_at=datetime.now(UTC),
            status="running",
            current_task_index=0,
            total_tasks=3,
            task_review_iteration=2,  # == max_iterations
            last_review=ReviewResult(
                reviewer_persona="Agentic", approved=False, comments=["fix X"], severity=Severity.MAJOR
            ),
        )
        assert route_after_task_review(state, profile) == "next_task_node"

    def test_max_iterations_final_task_routes_to_end(self, profile: Profile) -> None:
        """Max iterations on final task -> __end__."""
        state = ImplementationState(
            workflow_id=uuid4(),
            profile_id="test",
            created_at=datetime.now(UTC),
            status="running",
            current_task_index=2,
            total_tasks=3,
            task_review_iteration=2,  # == max_iterations
            last_review=ReviewResult(
                reviewer_persona="Agentic", approved=False, comments=["fix X"], severity=Severity.MAJOR
            ),
        )
        assert route_after_task_review(state, profile) == "__end__"
