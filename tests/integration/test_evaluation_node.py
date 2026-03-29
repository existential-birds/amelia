"""Integration tests for call_evaluation_node with real Evaluator.

Tests the evaluation node with real Evaluator agent, mocking only at
the driver.execute_agentic() boundary (LLM API call).
"""

from pathlib import Path
from typing import Any, cast
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
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.pipelines.review.nodes import call_evaluation_node
from tests.conftest import create_mock_execute_agentic
from tests.integration.conftest import make_config, make_execution_state, make_profile


@pytest.fixture(autouse=True)
def mock_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set API key env var to allow driver construction."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-for-integration-tests")


@pytest.mark.integration
class TestEvaluationNodeIntegration:
    """Test evaluation node with real Evaluator, mock at driver.execute_agentic() level."""

    async def test_evaluation_node_partitions_items_by_disposition(
        self, tmp_path: Path
    ) -> None:
        """Evaluation node should partition items into implement/reject/defer lists.

        Real components: get_driver, ApiDriver, Evaluator
        Mock boundary: ApiDriver.execute_agentic (LLM call)
        """
        profile = make_profile(repo_root=str(tmp_path))

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
            last_reviews=[review_result],
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

        mock_messages = [
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="submit_evaluation",
                tool_input=mock_llm_output.model_dump(mode="json"),
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="done",
                session_id="eval-session-123",
            ),
        ]
        with (
            patch.object(ApiDriver, "generate", new_callable=AsyncMock) as mock_generate,
            patch.object(
                ApiDriver, "execute_agentic", create_mock_execute_agentic(mock_messages)
            ),
        ):
            result = await call_evaluation_node(state, cast(RunnableConfig, config))

        mock_generate.assert_not_called()

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
        profile = make_profile(repo_root=str(tmp_path))

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
            last_reviews=[review_result],
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
        Mock boundary: ApiDriver.execute_agentic (LLM call)

        This verifies the config wiring works end-to-end with real Evaluator.
        """
        from amelia.core.types import AgentConfig, DriverType

        # Profile with explicit evaluator config
        profile = make_profile(
            repo_root=str(tmp_path),
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
            last_reviews=[review_result],
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

        mock_messages = [
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="submit_evaluation",
                tool_input=mock_llm_output.model_dump(mode="json"),
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="done",
                session_id="eval-session-456",
            ),
        ]
        with (
            patch.object(ApiDriver, "generate", new_callable=AsyncMock) as mock_generate,
            patch.object(
                ApiDriver, "execute_agentic", create_mock_execute_agentic(mock_messages)
            ),
        ):
            result = await call_evaluation_node(state, cast(RunnableConfig, config))

        mock_generate.assert_not_called()

        # Verify the node completed successfully (config wiring worked)
        assert result["evaluation_result"] is not None
        assert len(result["evaluation_result"].items_to_implement) == 1


@pytest.mark.integration
class TestEvaluationNodeToolCapture:
    """Evaluator tool-based submission via execute_agentic(submit_evaluation)."""

    async def test_evaluation_node_uses_execute_agentic_with_submit_evaluation(
        self, tmp_path: Path
    ) -> None:
        """Uses execute_agentic with allowed_tools submit_evaluation; generate is unused."""
        profile = make_profile(repo_root=str(tmp_path))

        review_result = ReviewResult(
            reviewer_persona="Code Reviewer",
            approved=False,
            comments=["[test.py:10] Missing error handling"],
            severity=Severity.MAJOR,
        )
        state = make_execution_state(
            profile=profile,
            goal="Add feature X",
            last_reviews=[review_result],
            code_changes_for_review="diff --git a/test.py",
        )
        config = make_config(thread_id="test-eval-tool-1", profile=profile)

        mock_llm_output = EvaluationOutput(
            evaluated_items=[
                EvaluatedItem(
                    number=1,
                    title="Missing error handling",
                    file_path="test.py",
                    line=10,
                    disposition=Disposition.IMPLEMENT,
                    reason="Valid issue",
                    original_issue="Missing error handling",
                    suggested_fix="Add try/except",
                ),
                EvaluatedItem(
                    number=2,
                    title="Other",
                    file_path="x.py",
                    line=1,
                    disposition=Disposition.REJECT,
                    reason="Nope",
                    original_issue="Other",
                    suggested_fix="",
                ),
                EvaluatedItem(
                    number=3,
                    title="Later",
                    file_path="y.py",
                    line=2,
                    disposition=Disposition.DEFER,
                    reason="Scope",
                    original_issue="Later",
                    suggested_fix="",
                ),
            ],
            summary="partitioned via tool",
        )

        captured_kwargs: list[dict[str, Any]] = []
        mock_messages = [
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="submit_evaluation",
                tool_input=mock_llm_output.model_dump(mode="json"),
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="done",
                session_id="eval-session-tool",
            ),
        ]

        with (
            patch.object(ApiDriver, "generate", new_callable=AsyncMock) as mock_generate,
            patch.object(
                ApiDriver,
                "execute_agentic",
                create_mock_execute_agentic(mock_messages, captured_kwargs),
            ),
        ):
            result = await call_evaluation_node(state, cast(RunnableConfig, config))

        mock_generate.assert_not_called()

        assert len(captured_kwargs) >= 1
        assert captured_kwargs[0]["allowed_tools"] == ["submit_evaluation"]

        assert result["evaluation_result"] is not None
        ev = result["evaluation_result"]
        assert len(ev.items_to_implement) == 1
        assert ev.items_to_implement[0].disposition == Disposition.IMPLEMENT
        assert len(ev.items_rejected) == 1
        assert len(ev.items_deferred) == 1
        assert ev.summary == "partitioned via tool"

    async def test_evaluation_node_first_call_wins(self, tmp_path: Path) -> None:
        """Only the first submit_evaluation tool call is applied."""
        profile = make_profile(repo_root=str(tmp_path))
        review_result = ReviewResult(
            reviewer_persona="Code Reviewer",
            approved=False,
            comments=["[a.py:1] one"],
            severity=Severity.MINOR,
        )
        state = make_execution_state(
            profile=profile,
            goal="G",
            last_reviews=[review_result],
        )
        config = make_config(thread_id="test-eval-first-wins", profile=profile)

        first_out = EvaluationOutput(
            evaluated_items=[
                EvaluatedItem(
                    number=1,
                    title="t",
                    file_path="a.py",
                    line=1,
                    disposition=Disposition.IMPLEMENT,
                    reason="r",
                    original_issue="one",
                    suggested_fix="f",
                ),
            ],
            summary="first summary",
        )
        second_out = EvaluationOutput(
            evaluated_items=[
                EvaluatedItem(
                    number=99,
                    title="other",
                    file_path="b.py",
                    line=9,
                    disposition=Disposition.REJECT,
                    reason="x",
                    original_issue="x",
                    suggested_fix="x",
                ),
            ],
            summary="second summary",
        )

        mock_messages = [
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="submit_evaluation",
                tool_input=first_out.model_dump(mode="json"),
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="submit_evaluation",
                tool_input=second_out.model_dump(mode="json"),
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="done",
                session_id="s",
            ),
        ]

        with (
            patch.object(ApiDriver, "generate", new_callable=AsyncMock),
            patch.object(ApiDriver, "execute_agentic", create_mock_execute_agentic(mock_messages)),
        ):
            result = await call_evaluation_node(state, cast(RunnableConfig, config))

        ev = result["evaluation_result"]
        assert ev.summary == "first summary"
        assert len(ev.items_to_implement) == 1
        assert ev.items_to_implement[0].number == 1
        assert len(ev.items_rejected) == 0

    async def test_evaluation_node_raises_on_missing_submit_evaluation(
        self, tmp_path: Path
    ) -> None:
        """RuntimeError when the stream has no submit_evaluation tool call."""
        profile = make_profile(repo_root=str(tmp_path))
        review_result = ReviewResult(
            reviewer_persona="Code Reviewer",
            approved=False,
            comments=["[z.py:1] c"],
            severity=Severity.MINOR,
        )
        state = make_execution_state(
            profile=profile,
            goal="G",
            last_reviews=[review_result],
        )
        config = make_config(thread_id="test-eval-missing-tool", profile=profile)

        mock_messages = [
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="no tool",
                session_id="s-only",
            ),
        ]

        with (
            patch.object(ApiDriver, "generate", new_callable=AsyncMock),
            patch.object(ApiDriver, "execute_agentic", create_mock_execute_agentic(mock_messages)),
            pytest.raises(RuntimeError, match="Evaluator did not call submit_evaluation"),
        ):
            await call_evaluation_node(state, cast(RunnableConfig, config))
