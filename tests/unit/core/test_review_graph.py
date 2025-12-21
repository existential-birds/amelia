# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for review graph functions."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock, patch

from amelia.core.orchestrator import (
    call_developer_node_for_review,
    create_synthetic_plan_from_review,
    should_continue_review_fix,
)
from amelia.core.state import ExecutionPlan, ExecutionState, ReviewResult
from amelia.core.types import Issue, Profile


class TestCreateSyntheticPlanFromReview:
    """Tests for create_synthetic_plan_from_review function."""

    def test_creates_plan_with_single_batch(
        self, mock_review_result_factory: Callable[..., ReviewResult]
    ) -> None:
        """Creates execution plan with single batch containing review comments."""
        review = mock_review_result_factory(
            approved=False,
            comments=["Fix naming convention", "Add error handling"],
            severity="medium",
        )

        plan = create_synthetic_plan_from_review(review)

        assert plan.goal == "Address code review feedback"
        assert len(plan.batches) == 1
        assert plan.batches[0].batch_number == 1

    def test_includes_all_comments_in_step_description(
        self, mock_review_result_factory: Callable[..., ReviewResult]
    ) -> None:
        """All review comments are included in the step description."""
        review = mock_review_result_factory(
            approved=False,
            comments=["Comment 1", "Comment 2", "Comment 3"],
            severity="low",
        )

        plan = create_synthetic_plan_from_review(review)
        step = plan.batches[0].steps[0]

        assert "Comment 1" in step.description
        assert "Comment 2" in step.description
        assert "Comment 3" in step.description

    def test_step_has_correct_properties(
        self, mock_review_result_factory: Callable[..., ReviewResult]
    ) -> None:
        """Synthetic step has correct action type and properties."""
        review = mock_review_result_factory(
            approved=False,
            comments=["Fix bug"],
            severity="high",
        )

        plan = create_synthetic_plan_from_review(review)
        step = plan.batches[0].steps[0]

        assert step.id == "REVIEW-FIX-1"
        assert step.action_type == "code"
        assert step.requires_human_judgment is False


class TestShouldContinueReviewFix:
    """Tests for should_continue_review_fix routing function."""

    def test_returns_end_when_approved(self, mock_profile_factory: Callable[..., Profile], mock_review_result_factory: Callable[..., ReviewResult]) -> None:
        """Returns END when review is approved."""
        state = ExecutionState(
            profile=mock_profile_factory(),
            last_review=mock_review_result_factory(approved=True, comments=[], severity="low"),
            review_iteration=0,
        )

        result = should_continue_review_fix(state)

        assert result == "__end__"

    def test_returns_end_at_max_iterations(self, mock_profile_factory: Callable[..., Profile], mock_review_result_factory: Callable[..., ReviewResult]) -> None:
        """Returns END when max iterations (3) reached, even if not approved."""
        state = ExecutionState(
            profile=mock_profile_factory(),
            last_review=mock_review_result_factory(approved=False, comments=["Still wrong"], severity="medium"),
            review_iteration=3,
        )

        result = should_continue_review_fix(state)

        assert result == "__end__"

    def test_returns_developer_when_rejected_under_max(self, mock_profile_factory: Callable[..., Profile], mock_review_result_factory: Callable[..., ReviewResult]) -> None:
        """Returns 'developer' when review rejected and under max iterations."""
        state = ExecutionState(
            profile=mock_profile_factory(),
            last_review=mock_review_result_factory(approved=False, comments=["Fix this"], severity="medium"),
            review_iteration=1,
        )

        result = should_continue_review_fix(state)

        assert result == "developer"

    def test_continues_at_iteration_2(self, mock_profile_factory: Callable[..., Profile], mock_review_result_factory: Callable[..., ReviewResult]) -> None:
        """At iteration 2, still continues to developer (max is 3)."""
        state = ExecutionState(
            profile=mock_profile_factory(),
            last_review=mock_review_result_factory(approved=False, comments=["Almost"], severity="low"),
            review_iteration=2,
        )

        result = should_continue_review_fix(state)

        assert result == "developer"


class TestCallDeveloperNodeForReview:
    """Tests for call_developer_node_for_review function."""

    async def test_returns_review_iteration_in_result(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
        mock_execution_plan_factory: Callable[..., ExecutionPlan],
        mock_review_result_factory: Callable[..., ReviewResult],
    ) -> None:
        """Returns review_iteration in result dict with incremented value."""
        # Create a state with a rejected review and review_iteration=1
        state = ExecutionState(
            profile=mock_profile_factory(),
            issue=mock_issue_factory(),
            execution_plan=mock_execution_plan_factory(),
            last_review=mock_review_result_factory(
                approved=False,
                comments=["Needs fixes"],
                severity="medium"
            ),
            review_iteration=1,
        )

        # Mock call_developer_node to return a minimal result
        mock_developer_result = {
            "code_changes_for_review": "test changes",
            "current_batch_index": 1,
        }

        with patch(
            "amelia.core.orchestrator.call_developer_node",
            new_callable=AsyncMock,
            return_value=mock_developer_result,
        ):
            result = await call_developer_node_for_review(state, config=None)

        # Assert review_iteration is in the result and incremented
        assert "review_iteration" in result
        assert result["review_iteration"] == state.review_iteration + 1
        assert result["review_iteration"] == 2
