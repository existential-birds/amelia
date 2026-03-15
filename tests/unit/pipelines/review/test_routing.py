"""Tests for review pipeline routing functions."""

from datetime import UTC, datetime
from uuid import uuid4

from langgraph.graph import END

from amelia.agents.schemas.evaluator import (
    Disposition,
    EvaluatedItem,
    EvaluationResult,
)
from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)
from amelia.pipelines.review.routing import route_after_evaluation, route_after_fixes

# Required for EvaluationResult field resolution
rebuild_implementation_state()


def _make_item() -> EvaluatedItem:
    return EvaluatedItem(
        number=1,
        title="Fix typo",
        file_path="foo.py",
        line=1,
        disposition=Disposition.IMPLEMENT,
        reason="typo",
        original_issue="typo in foo",
        suggested_fix="fix it",
    )


def _make_state(
    review_mode: str | None = None,
    has_items: bool = False,
    has_eval: bool = True,
    review_pass: int = 0,
    max_review_passes: int = 3,
) -> ImplementationState:
    eval_result = None
    if has_eval:
        items = [_make_item()] if has_items else []
        eval_result = EvaluationResult(items_to_implement=items, summary="test")

    return ImplementationState(
        workflow_id=uuid4(),
        profile_id="test",
        created_at=datetime.now(UTC),
        status="pending",
        review_mode=review_mode,
        evaluation_result=eval_result,
        review_pass=review_pass,
        max_review_passes=max_review_passes,
    )


class TestRouteAfterEvaluation:

    def test_review_only_routes_to_end(self) -> None:
        state = _make_state(review_mode="review_only", has_items=True)
        assert route_after_evaluation(state) == END

    def test_review_only_routes_to_end_even_without_items(self) -> None:
        state = _make_state(review_mode="review_only", has_items=False)
        assert route_after_evaluation(state) == END

    def test_review_fix_with_items_routes_to_developer(self) -> None:
        state = _make_state(review_mode="review_fix", has_items=True)
        assert route_after_evaluation(state) == "developer_node"

    def test_review_fix_without_items_routes_to_end(self) -> None:
        state = _make_state(review_mode="review_fix", has_items=False)
        assert route_after_evaluation(state) == END

    def test_no_mode_with_items_routes_to_developer(self) -> None:
        state = _make_state(has_items=True)
        assert route_after_evaluation(state) == "developer_node"

    def test_no_mode_without_eval_result_routes_to_end(self) -> None:
        state = _make_state(has_eval=False)
        assert route_after_evaluation(state) == END


class TestRouteAfterFixes:

    def test_max_passes_reached_routes_to_end(self) -> None:
        state = _make_state(review_pass=3, max_review_passes=3)
        assert route_after_fixes(state) == END

    def test_under_max_passes_routes_to_reviewer(self) -> None:
        state = _make_state(review_pass=1, max_review_passes=3)
        assert route_after_fixes(state) == "reviewer_node"
