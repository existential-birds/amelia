"""Unit tests for review-fix developer user prompt construction."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from amelia.agents.schemas.evaluator import Disposition, EvaluatedItem, EvaluationResult
from amelia.core.types import ReviewResult, Severity
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.review.developer_prompt import build_review_fix_prompt


def _evaluated_item(**overrides: Any) -> EvaluatedItem:
    defaults: dict[str, Any] = {
        "number": 1,
        "title": "Missing guard",
        "file_path": "src/app.py",
        "line": 10,
        "disposition": Disposition.IMPLEMENT,
        "reason": "Verified in code",
        "original_issue": "None check missing",
        "suggested_fix": "Add explicit None guard",
    }
    return EvaluatedItem(**{**defaults, **overrides})


class TestBuildReviewFixPrompt:
    """Tests for build_review_fix_prompt."""

    def test_includes_structured_items_and_goal(self) -> None:
        """Prompt lists each item and ends with the goal string."""
        goal = "Fix the following review items:\n\n- [src/app.py:10] x: y — z"
        evaluation_result = EvaluationResult(
            summary="one item",
            items_to_implement=[_evaluated_item()],
        )
        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            goal=goal,
            evaluation_result=evaluation_result,
        )
        prompt = build_review_fix_prompt(state)

        assert "src/app.py:10" in prompt
        assert "Missing guard" in prompt
        assert "None check missing" in prompt
        assert "Add explicit None guard" in prompt
        assert "#1" in prompt
        assert goal in prompt

    def test_missing_goal_raises(self) -> None:
        """Goal is required for the review-fix user prompt."""
        evaluation_result = EvaluationResult(
            summary="x",
            items_to_implement=[_evaluated_item()],
        )
        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            goal=None,
            evaluation_result=evaluation_result,
        )
        with pytest.raises(ValueError, match="goal"):
            build_review_fix_prompt(state)

    def test_missing_evaluation_result_raises(self) -> None:
        """Evaluation result is required for structured items."""
        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            goal="Do the fixes",
            evaluation_result=None,
        )
        with pytest.raises(ValueError, match="evaluation_result"):
            build_review_fix_prompt(state)

    def test_appends_reviewer_feedback_when_present(self) -> None:
        """Rejected comments from last_reviews are appended like plan-based path."""
        goal = "Fix items"
        evaluation_result = EvaluationResult(
            summary="one",
            items_to_implement=[_evaluated_item(number=2, title="T")],
        )
        reviews = [
            ReviewResult(
                reviewer_persona="agentic",
                approved=False,
                comments=["Also update the docstring"],
                severity=Severity.MAJOR,
            )
        ]
        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            goal=goal,
            evaluation_result=evaluation_result,
            last_reviews=reviews,
        )
        prompt = build_review_fix_prompt(state)
        assert "Also update the docstring" in prompt
        assert "reviewer requested" in prompt.lower()
