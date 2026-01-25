"""Tests for the Evaluator agent."""
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.agents.evaluator import (
    Disposition,
    EvaluatedItem,
    EvaluationOutput,
    EvaluationResult,
    Evaluator,
)
from amelia.core.types import AgentConfig, Profile, ReviewResult
from amelia.pipelines.implementation.state import ImplementationState


class TestEvaluatedItem:
    """Tests for EvaluatedItem model."""

    def test_evaluated_item_all_dispositions(self) -> None:
        """Test that all disposition values are valid."""
        for disp in Disposition:
            item = EvaluatedItem(
                number=1,
                title="Test",
                file_path="test.py",
                line=1,
                disposition=disp,
                reason="Test reason",
                original_issue="Test issue",
                suggested_fix="Test fix",
            )
            assert item.disposition == disp


class TestEvaluationResult:
    """Tests for EvaluationResult model."""

    def test_evaluation_result_default_empty_lists(self) -> None:
        """Test that EvaluationResult defaults to empty lists."""
        result = EvaluationResult(summary="Test summary")
        assert result.items_to_implement == []
        assert result.items_rejected == []
        assert result.items_deferred == []
        assert result.items_needing_clarification == []


class TestEvaluator:
    """Tests for Evaluator agent."""

    def test_evaluator_init_with_agent_config(self) -> None:
        """Evaluator should accept AgentConfig and create its own driver."""
        config = AgentConfig(driver="cli", model="sonnet")

        with patch("amelia.agents.evaluator.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_get_driver.return_value = mock_driver

            evaluator = Evaluator(config)

            mock_get_driver.assert_called_once_with("cli", model="sonnet")
            assert evaluator.driver is mock_driver

    def test_evaluator_init_stores_options(self) -> None:
        """Evaluator should store options from AgentConfig."""
        config = AgentConfig(
            driver="api",
            model="anthropic/claude-sonnet-4",
            options={"max_iterations": 5},
        )

        with patch("amelia.agents.evaluator.get_driver") as mock_get_driver:
            mock_get_driver.return_value = MagicMock()

            evaluator = Evaluator(config)

            assert evaluator.options == {"max_iterations": 5}

    @pytest.fixture
    def evaluator(self, mock_driver: MagicMock) -> Evaluator:
        """Create an Evaluator instance with mocked driver."""
        config = AgentConfig(driver="cli", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            return Evaluator(config)

    def test_system_prompt_returns_default_when_no_custom_prompt(
        self, mock_driver: MagicMock
    ) -> None:
        """Test that system_prompt returns default SYSTEM_PROMPT when no custom prompt."""
        config = AgentConfig(driver="cli", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)
        assert evaluator.system_prompt == Evaluator.SYSTEM_PROMPT
        assert "expert code evaluation agent" in evaluator.system_prompt

    def test_system_prompt_returns_default_when_empty_prompts_dict(
        self, mock_driver: MagicMock
    ) -> None:
        """Test that system_prompt returns default when prompts dict is empty."""
        config = AgentConfig(driver="cli", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config, prompts={})
        assert evaluator.system_prompt == Evaluator.SYSTEM_PROMPT

    def test_system_prompt_returns_default_when_key_not_present(
        self, mock_driver: MagicMock
    ) -> None:
        """Test that system_prompt returns default when evaluator.system key is absent."""
        config = AgentConfig(driver="cli", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config, prompts={"other.key": "other value"})
        assert evaluator.system_prompt == Evaluator.SYSTEM_PROMPT

    def test_system_prompt_returns_custom_prompt_when_configured(
        self, mock_driver: MagicMock
    ) -> None:
        """Test that system_prompt returns custom prompt when evaluator.system is set."""
        custom_prompt = "You are a custom code evaluator..."
        prompts = {"evaluator.system": custom_prompt}
        config = AgentConfig(driver="cli", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config, prompts=prompts)
        assert evaluator.system_prompt == custom_prompt
        assert evaluator.system_prompt != Evaluator.SYSTEM_PROMPT

    @pytest.fixture
    def evaluation_output_with_items(self) -> EvaluationOutput:
        """Create evaluation output with mixed dispositions."""
        return EvaluationOutput(
            evaluated_items=[
                EvaluatedItem(
                    number=1,
                    title="Bug fix needed",
                    file_path="src/main.py",
                    line=10,
                    disposition=Disposition.IMPLEMENT,
                    reason="Valid bug report",
                    original_issue="Null pointer exception",
                    suggested_fix="Add null check",
                ),
                EvaluatedItem(
                    number=2,
                    title="Style issue",
                    file_path="src/utils.py",
                    line=20,
                    disposition=Disposition.REJECT,
                    reason="Existing codebase pattern",
                    original_issue="Wrong naming convention",
                    suggested_fix="Rename variable",
                ),
                EvaluatedItem(
                    number=3,
                    title="Performance improvement",
                    file_path="src/data.py",
                    line=30,
                    disposition=Disposition.DEFER,
                    reason="Out of scope for this issue",
                    original_issue="Slow database query",
                    suggested_fix="Add index",
                ),
                EvaluatedItem(
                    number=4,
                    title="Unclear requirement",
                    file_path="src/api.py",
                    line=40,
                    disposition=Disposition.CLARIFY,
                    reason="Need clarification on expected behavior",
                    original_issue="API response format",
                    suggested_fix="Change format?",
                ),
            ],
            summary="Mixed evaluation results",
        )

    async def test_evaluate_with_review_feedback(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
        evaluation_output_with_items: EvaluationOutput,
    ) -> None:
        """Test evaluation with review comments."""
        # Setup state with review feedback
        review_result = ReviewResult(
            reviewer_persona="General",
            approved=False,
            comments=["Issue 1", "Issue 2", "Issue 3", "Issue 4"],
            severity="medium",
        )
        state, profile = mock_execution_state_factory(
            goal="Fix bugs",
            last_review=review_result,
            code_changes_for_review="diff content",
        )

        # Mock driver to return evaluation output
        mock_driver.generate = AsyncMock(
            return_value=(evaluation_output_with_items, "session-123")
        )

        config = AgentConfig(driver="cli", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)
        result, session_id = await evaluator.evaluate(
            state, profile, workflow_id="wf-123"
        )

        assert session_id == "session-123"
        assert len(result.items_to_implement) == 1
        assert len(result.items_rejected) == 1
        assert len(result.items_deferred) == 1
        assert len(result.items_needing_clarification) == 1
        assert result.summary == "Mixed evaluation results"

        # Verify driver was called with correct schema
        mock_driver.generate.assert_called_once()
        call_kwargs = mock_driver.generate.call_args.kwargs
        assert call_kwargs["schema"] == EvaluationOutput

    async def test_evaluate_empty_comments(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        """Test evaluation with empty review comments returns empty result."""
        # Setup state with empty review comments
        review_result = ReviewResult(
            reviewer_persona="General",
            approved=True,
            comments=[],
            severity="low",
        )
        state, profile = mock_execution_state_factory(
            goal="Fix bugs",
            last_review=review_result,
        )

        config = AgentConfig(driver="cli", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)
        result, session_id = await evaluator.evaluate(
            state, profile, workflow_id="wf-123"
        )

        # Should return empty result without calling driver
        assert result.items_to_implement == []
        assert result.items_rejected == []
        assert result.items_deferred == []
        assert result.items_needing_clarification == []
        assert "No review comments" in result.summary

        # Driver should NOT be called for empty comments
        mock_driver.generate.assert_not_called()

    async def test_evaluate_partitions_by_disposition(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        """Test that items are correctly partitioned by disposition."""
        # Create output with multiple items of same disposition
        evaluation_output = EvaluationOutput(
            evaluated_items=[
                EvaluatedItem(
                    number=1,
                    title="Bug 1",
                    file_path="a.py",
                    line=1,
                    disposition=Disposition.IMPLEMENT,
                    reason="Valid",
                    original_issue="Bug",
                    suggested_fix="Fix",
                ),
                EvaluatedItem(
                    number=2,
                    title="Bug 2",
                    file_path="b.py",
                    line=2,
                    disposition=Disposition.IMPLEMENT,
                    reason="Valid",
                    original_issue="Bug",
                    suggested_fix="Fix",
                ),
                EvaluatedItem(
                    number=3,
                    title="Reject 1",
                    file_path="c.py",
                    line=3,
                    disposition=Disposition.REJECT,
                    reason="Invalid",
                    original_issue="Issue",
                    suggested_fix="N/A",
                ),
            ],
            summary="Partitioned results",
        )

        review_result = ReviewResult(
            reviewer_persona="General",
            approved=False,
            comments=["Comment 1", "Comment 2", "Comment 3"],
            severity="medium",
        )
        state, profile = mock_execution_state_factory(
            goal="Fix bugs",
            last_review=review_result,
        )

        mock_driver.generate = AsyncMock(return_value=(evaluation_output, None))

        config = AgentConfig(driver="cli", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)
        result, _ = await evaluator.evaluate(state, profile, workflow_id="wf-123")

        # Verify correct partitioning
        assert len(result.items_to_implement) == 2
        assert len(result.items_rejected) == 1
        assert len(result.items_deferred) == 0
        assert len(result.items_needing_clarification) == 0

        # Verify item numbers are preserved
        implement_numbers = [item.number for item in result.items_to_implement]
        assert 1 in implement_numbers
        assert 2 in implement_numbers

    async def test_evaluate_requires_last_review(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        """Test that evaluation raises error when no last_review in state."""
        state, profile = mock_execution_state_factory(
            goal="Fix bugs",
            last_review=None,
        )

        config = AgentConfig(driver="cli", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)
        with pytest.raises(ValueError, match="must have last_review"):
            await evaluator.evaluate(state, profile, workflow_id="wf-123")

    async def test_evaluate_with_event_bus(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        """Test that event_bus.emit is called during evaluation."""
        mock_event_bus = MagicMock()

        review_result = ReviewResult(
            reviewer_persona="General",
            approved=False,
            comments=["Issue 1"],
            severity="low",
        )
        state, profile = mock_execution_state_factory(
            goal="Fix bugs",
            last_review=review_result,
        )

        evaluation_output = EvaluationOutput(
            evaluated_items=[
                EvaluatedItem(
                    number=1,
                    title="Bug",
                    file_path="a.py",
                    line=1,
                    disposition=Disposition.IMPLEMENT,
                    reason="Valid",
                    original_issue="Bug",
                    suggested_fix="Fix",
                ),
            ],
            summary="Evaluation done",
        )
        mock_driver.generate = AsyncMock(return_value=(evaluation_output, None))

        config = AgentConfig(driver="cli", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config, event_bus=mock_event_bus)
        await evaluator.evaluate(state, profile, workflow_id="wf-123")

        # Verify event_bus.emit was called
        mock_event_bus.emit.assert_called_once()
        call_args = mock_event_bus.emit.call_args[0][0]
        assert call_args.agent == "evaluator"
        assert call_args.workflow_id == "wf-123"

    async def test_evaluate_builds_prompt_with_goal(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        """Test that prompt includes goal when available."""
        review_result = ReviewResult(
            reviewer_persona="General",
            approved=False,
            comments=["Check this"],
            severity="low",
        )
        state, profile = mock_execution_state_factory(
            goal="Implement feature X",
            last_review=review_result,
            code_changes_for_review="diff content",
        )

        evaluation_output = EvaluationOutput(
            evaluated_items=[],
            summary="Empty",
        )
        mock_driver.generate = AsyncMock(return_value=(evaluation_output, None))

        config = AgentConfig(driver="cli", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)
        await evaluator.evaluate(state, profile, workflow_id="wf-123")

        # Check that prompt contains the goal
        call_args = mock_driver.generate.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "Implement feature X" in prompt

    async def test_evaluate_builds_prompt_with_issue_fallback(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        """Test that prompt uses issue context when no goal available."""
        review_result = ReviewResult(
            reviewer_persona="General",
            approved=False,
            comments=["Check this"],
            severity="low",
        )
        state, profile = mock_execution_state_factory(
            goal=None,  # No goal
            last_review=review_result,
        )

        evaluation_output = EvaluationOutput(
            evaluated_items=[],
            summary="Empty",
        )
        mock_driver.generate = AsyncMock(return_value=(evaluation_output, None))

        config = AgentConfig(driver="cli", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)
        await evaluator.evaluate(state, profile, workflow_id="wf-123")

        # Check that prompt contains issue context
        call_args = mock_driver.generate.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "Issue Context" in prompt or "Test Issue" in prompt


