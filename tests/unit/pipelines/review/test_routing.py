"""Tests for review pipeline routing functions."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
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

    @pytest.mark.parametrize(
        ("state_kwargs", "expected"),
        [
            pytest.param(
                {"review_mode": "review_only", "has_items": True},
                END,
                id="review-only-with-items-ends",
            ),
            pytest.param(
                {"review_mode": "review_only", "has_items": False},
                END,
                id="review-only-without-items-ends",
            ),
            pytest.param(
                {"review_mode": "review_fix", "has_items": True},
                "developer_node",
                id="review-fix-with-items-develops",
            ),
            pytest.param(
                {"review_mode": "review_fix", "has_items": False},
                END,
                id="review-fix-without-items-ends",
            ),
            pytest.param(
                {"has_items": True},
                "developer_node",
                id="no-mode-with-items-develops",
            ),
            pytest.param(
                {"has_eval": False},
                END,
                id="no-mode-without-eval-ends",
            ),
        ],
    )
    def test_routes_correctly(
        self, state_kwargs: dict[str, object], expected: str,
    ) -> None:
        state = _make_state(**state_kwargs)  # type: ignore[arg-type]
        assert route_after_evaluation(state) == expected


class TestRouteAfterFixes:

    @pytest.mark.parametrize(
        ("review_pass", "max_review_passes", "expected"),
        [
            pytest.param(3, 3, END, id="max-passes-reached-ends"),
            pytest.param(1, 3, "reviewer_node", id="under-max-continues"),
        ],
    )
    def test_routes_correctly(
        self, review_pass: int, max_review_passes: int, expected: str,
    ) -> None:
        state = _make_state(review_pass=review_pass, max_review_passes=max_review_passes)
        assert route_after_fixes(state) == expected
