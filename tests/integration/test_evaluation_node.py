"""Integration tests for call_evaluation_node with real Evaluator.

Tests the evaluation node with real Evaluator agent, mocking only at
the driver.generate() boundary (LLM API call).
"""

from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.agents.schemas.evaluator import (
    Disposition,
    EvaluatedItem,
    EvaluationOutput,
)
from amelia.core.types import ReviewResult, Severity
from amelia.drivers.api import ApiDriver
from amelia.pipelines.review.nodes import call_evaluation_node
from tests.integration.conftest import make_config, make_execution_state, make_profile


@pytest.fixture(autouse=True)
def mock_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set API key env var to allow driver construction."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-for-integration-tests")


@pytest.mark.integration
class TestEvaluationNodeIntegration:
    """Test evaluation node with real Evaluator, mock at driver.generate() level."""

    async def test_evaluation_node_partitions_items_by_disposition(
        self, tmp_path: Path
    ) -> None:
        """Evaluation node should partition items into implement/reject/defer lists.

        Real components: get_driver, ApiDriver, Evaluator
        Mock boundary: ApiDriver.generate (LLM call)
        """
        profile = make_profile(working_dir=str(tmp_path))

        # State with review feedback to evaluate
        review_result = ReviewResult(
            reviewer_persona="Code Reviewer",
            approved=False,
            comments=[
                "[test.py:10] Missing error handling for edge case",
                "[test.py:20] Unused import",
                "[utils.py:5] Consider adding type hints",
            ],
            severity=Severity.MAJOR,
        )
        state = make_execution_state(
            profile=profile,
            goal="Add feature X",
            last_review=review_result,
            code_changes_for_review="diff --git a/test.py",
        )
        config = make_config(thread_id="test-eval-1", profile=profile)

        # Mock LLM response with mixed dispositions
        mock_llm_output = EvaluationOutput(
            evaluated_items=[
                EvaluatedItem(
                    number=1,
                    title="Missing error handling",
                    file_path="test.py",
                    line=10,
                    disposition=Disposition.IMPLEMENT,
                    reason="Valid issue, error handling is needed here",
                    original_issue="Missing error handling for edge case",
                    suggested_fix="Add try/except block",
                ),
                EvaluatedItem(
                    number=2,
                    title="Unused import",
                    file_path="test.py",
                    line=20,
                    disposition=Disposition.REJECT,
                    reason="Import is used in line 45, reviewer missed it",
                    original_issue="Unused import",
                    suggested_fix="Remove import",
                ),
                EvaluatedItem(
                    number=3,
                    title="Type hints",
                    file_path="utils.py",
                    line=5,
                    disposition=Disposition.DEFER,
                    reason="Out of scope for current task",
                    original_issue="Consider adding type hints",
                    suggested_fix="Add type hints to function",
                ),
            ],
            summary="1 item to implement, 1 rejected (false positive), 1 deferred",
        )

        with patch.object(
            ApiDriver, "generate", new_callable=AsyncMock
        ) as mock_generate:
            mock_generate.return_value = (mock_llm_output, "eval-session-123")

            result = await call_evaluation_node(state, cast(RunnableConfig, config))

        # Verify items are partitioned correctly
        assert result["evaluation_result"] is not None
        eval_result = result["evaluation_result"]

        assert len(eval_result.items_to_implement) == 1
        assert eval_result.items_to_implement[0].disposition == Disposition.IMPLEMENT

        assert len(eval_result.items_rejected) == 1
        assert eval_result.items_rejected[0].disposition == Disposition.REJECT

        assert len(eval_result.items_deferred) == 1
        assert eval_result.items_deferred[0].disposition == Disposition.DEFER

        assert eval_result.summary == mock_llm_output.summary

    async def test_evaluation_node_handles_empty_review_comments(
        self, tmp_path: Path
    ) -> None:
        """Evaluation node should return empty result when no comments to evaluate.

        Real components: get_driver, ApiDriver, Evaluator
        Mock boundary: None (no LLM call made for empty comments)
        """
        profile = make_profile(working_dir=str(tmp_path))

        # State with empty review comments
        review_result = ReviewResult(
            reviewer_persona="Code Reviewer",
            approved=True,
            comments=[],  # No comments to evaluate
            severity=Severity.NONE,
        )
        state = make_execution_state(
            profile=profile,
            goal="Add feature X",
            last_review=review_result,
        )
        config = make_config(thread_id="test-eval-empty", profile=profile)

        # No mock needed - Evaluator short-circuits for empty comments
        result = await call_evaluation_node(state, cast(RunnableConfig, config))

        assert result["evaluation_result"] is not None
        eval_result = result["evaluation_result"]
        assert len(eval_result.items_to_implement) == 0
        assert len(eval_result.items_rejected) == 0
        assert len(eval_result.items_deferred) == 0
        assert "no review comments" in eval_result.summary.lower()

    async def test_evaluation_node_uses_agent_config(self, tmp_path: Path) -> None:
        """Evaluation node should use profile.get_agent_config('evaluator').

        Real components: get_driver, ApiDriver, Evaluator
        Mock boundary: ApiDriver.generate (LLM call)

        This verifies the config wiring works end-to-end with real Evaluator.
        """
        from amelia.core.types import AgentConfig, DriverType

        # Profile with explicit evaluator config
        profile = make_profile(
            working_dir=str(tmp_path),
            agents={
                "architect": AgentConfig(driver=DriverType.API, model="sonnet"),
                "developer": AgentConfig(driver=DriverType.API, model="sonnet"),
                "reviewer": AgentConfig(driver=DriverType.API, model="sonnet"),
                "plan_validator": AgentConfig(driver=DriverType.API, model="haiku"),
                "evaluator": AgentConfig(driver=DriverType.API, model="opus"),  # Different model
                "task_reviewer": AgentConfig(driver=DriverType.API, model="haiku"),
            },
        )

        review_result = ReviewResult(
            reviewer_persona="Code Reviewer",
            approved=False,
            comments=["[test.py:1] Issue to evaluate"],
            severity=Severity.MINOR,
        )
        state = make_execution_state(
            profile=profile,
            goal="Test config wiring",
            last_review=review_result,
        )
        config = make_config(thread_id="test-eval-config", profile=profile)

        mock_llm_output = EvaluationOutput(
            evaluated_items=[
                EvaluatedItem(
                    number=1,
                    title="Test issue",
                    file_path="test.py",
                    line=1,
                    disposition=Disposition.IMPLEMENT,
                    reason="Valid",
                    original_issue="Issue to evaluate",
                    suggested_fix="Fix it",
                ),
            ],
            summary="1 item to implement",
        )

        with patch.object(
            ApiDriver, "generate", new_callable=AsyncMock
        ) as mock_generate:
            mock_generate.return_value = (mock_llm_output, "eval-session-456")

            result = await call_evaluation_node(state, cast(RunnableConfig, config))

        # Verify the node completed successfully (config wiring worked)
        assert result["evaluation_result"] is not None
        assert len(result["evaluation_result"].items_to_implement) == 1
