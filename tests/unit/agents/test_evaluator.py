"""Tests for the Evaluator agent."""
from collections.abc import Callable
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from amelia.agents.evaluator import Evaluator
from amelia.agents.schemas.evaluator import (
    Disposition,
    EvaluatedItem,
    EvaluationOutput,
    EvaluationResult,
)
from amelia.core.types import AgentConfig, Profile, ReviewResult, SandboxConfig, Severity
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.pipelines.implementation.state import ImplementationState
from tests.conftest import AsyncIteratorMock


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


class TestParseChangedFiles:
    """Tests for Evaluator._parse_changed_files helper."""

    def test_parses_simple_diff_headers(self) -> None:
        diff = (
            "diff --git a/x/y.py b/x/y.py\n"
            "index abc..def 100644\n"
            "--- a/x/y.py\n"
            "+++ b/x/y.py\n"
            "@@ -1 +1 @@\n"
            "-old\n+new\n"
            "diff --git a/a.md b/a.md\n"
            "--- a/a.md\n"
            "+++ b/a.md\n"
        )
        assert Evaluator._parse_changed_files(diff) == ["x/y.py", "a.md"]

    def test_parses_rename(self) -> None:
        diff = "diff --git a/old.py b/new.py\n"
        assert Evaluator._parse_changed_files(diff) == ["new.py"]

    def test_parses_deleted_file_hunk(self) -> None:
        diff = (
            "diff --git a/deleted.py b/deleted.py\n"
            "--- a/deleted.py\n"
            "+++ /dev/null\n"
        )
        assert Evaluator._parse_changed_files(diff) == ["deleted.py"]

    def test_deduplicates_preserving_order(self) -> None:
        diff = (
            "diff --git a/a.py b/a.py\n"
            "diff --git a/b.py b/b.py\n"
            "diff --git a/a.py b/a.py\n"
        )
        assert Evaluator._parse_changed_files(diff) == ["a.py", "b.py"]

    def test_empty_or_none(self) -> None:
        assert Evaluator._parse_changed_files(None) == []
        assert Evaluator._parse_changed_files("") == []
        assert Evaluator._parse_changed_files("no headers here\njust text\n") == []


class TestBuildPromptShape:
    """Tests for Evaluator._build_prompt manifest shape."""

    @pytest.fixture
    def evaluator_instance(self, mock_driver: MagicMock) -> Evaluator:
        config = AgentConfig(driver="claude", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            return Evaluator(config)

    def test_no_inlined_diff_block(
        self,
        evaluator_instance: Evaluator,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        review_result = ReviewResult(
            reviewer_persona="General",
            approved=False,
            comments=["Issue 1"],
            severity=Severity.MINOR,
        )
        diff_body = (
            "diff --git a/foo.py b/foo.py\n"
            "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old line\n+new line\n"
        )
        state, _ = mock_execution_state_factory(
            goal="g",
            last_reviews=[review_result],
            code_changes_for_review=diff_body,
        )
        prompt = evaluator_instance._build_prompt(state)
        assert "```diff" not in prompt
        assert "-old line" not in prompt
        assert "+new line" not in prompt
        assert "## Changed Files" in prompt
        assert "- foo.py" in prompt

    def test_base_commit_hint_present_when_set(
        self,
        evaluator_instance: Evaluator,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        review_result = ReviewResult(
            reviewer_persona="General",
            approved=False,
            comments=["Issue 1"],
            severity=Severity.MINOR,
        )
        state, _ = mock_execution_state_factory(
            goal="g",
            last_reviews=[review_result],
            code_changes_for_review="diff --git a/foo.py b/foo.py\n",
            base_commit="deadbeef",
        )
        prompt = evaluator_instance._build_prompt(state)
        assert "git diff deadbeef HEAD -- <path>" in prompt

    def test_no_base_commit_hint_when_unset(
        self,
        evaluator_instance: Evaluator,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        review_result = ReviewResult(
            reviewer_persona="General",
            approved=False,
            comments=["Issue 1"],
            severity=Severity.MINOR,
        )
        state, _ = mock_execution_state_factory(
            goal="g",
            last_reviews=[review_result],
            code_changes_for_review="diff --git a/foo.py b/foo.py\n",
        )
        prompt = evaluator_instance._build_prompt(state)
        assert "git diff" not in prompt

    def test_no_changed_files_section_when_empty(
        self,
        evaluator_instance: Evaluator,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        review_result = ReviewResult(
            reviewer_persona="General",
            approved=False,
            comments=["Issue 1"],
            severity=Severity.MINOR,
        )
        state, _ = mock_execution_state_factory(
            goal="g",
            last_reviews=[review_result],
        )
        prompt = evaluator_instance._build_prompt(state)
        assert "## Changed Files" not in prompt


class TestSystemPromptFetchOnDemand:
    """SYSTEM_PROMPT must guide the agent to fetch on demand."""

    def test_system_prompt_mentions_fetch_on_demand_tools(self) -> None:
        sp = Evaluator.SYSTEM_PROMPT
        # Driver-agnostic phrasing: don't hardcode Claude CLI tool names
        assert "file-reading" in sp.lower()
        assert "shell tools" in sp.lower()
        assert "on demand" in sp.lower() or "as needed" in sp.lower()
        # Must not instruct the agent to rely on an inlined diff
        assert "do not expect an inlined diff" in sp.lower()


class TestEvaluator:
    """Tests for Evaluator agent."""

    def test_evaluator_init_with_agent_config(self) -> None:
        """Evaluator should accept AgentConfig and create its own driver."""
        config = AgentConfig(driver="claude", model="sonnet")

        with patch("amelia.agents.evaluator.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_get_driver.return_value = mock_driver

            evaluator = Evaluator(config)

            mock_get_driver.assert_called_once_with(
                "claude",
                model="sonnet",
                sandbox_config=SandboxConfig(),
                sandbox_provider=None,
                profile_name="default",
                options={},
            )
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
        config = AgentConfig(driver="claude", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            return Evaluator(config)

    def test_system_prompt_returns_default_when_no_custom_prompt(
        self, mock_driver: MagicMock
    ) -> None:
        """Test that system_prompt returns default SYSTEM_PROMPT when no custom prompt."""
        config = AgentConfig(driver="claude", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)
        assert evaluator.system_prompt == Evaluator.SYSTEM_PROMPT
        assert "expert code evaluation agent" in evaluator.system_prompt

    def test_system_prompt_returns_default_when_empty_prompts_dict(
        self, mock_driver: MagicMock
    ) -> None:
        """Test that system_prompt returns default when prompts dict is empty."""
        config = AgentConfig(driver="claude", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config, prompts={})
        assert evaluator.system_prompt == Evaluator.SYSTEM_PROMPT

    def test_system_prompt_returns_default_when_key_not_present(
        self, mock_driver: MagicMock
    ) -> None:
        """Test that system_prompt returns default when evaluator.system key is absent."""
        config = AgentConfig(driver="claude", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config, prompts={"other.key": "other value"})
        assert evaluator.system_prompt == Evaluator.SYSTEM_PROMPT

    def test_system_prompt_returns_custom_prompt_when_configured(
        self, mock_driver: MagicMock
    ) -> None:
        """Test that system_prompt returns custom prompt when evaluator.system is set."""
        custom_prompt = "You are a custom code evaluator..."
        prompts = {"evaluator.system": custom_prompt}
        config = AgentConfig(driver="claude", model="sonnet")
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

    def _make_agentic_mock(
        self, mock_driver: MagicMock, evaluation_output: EvaluationOutput, session_id: str = "session-123"
    ) -> None:
        """Helper to wire mock_driver.execute_agentic for a standard submit_evaluation flow."""
        tool_call_msg = AgenticMessage(
            type=AgenticMessageType.TOOL_CALL,
            tool_name="submit_evaluation",
            tool_input=evaluation_output.model_dump(),
        )
        result_msg = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="Evaluation complete",
            session_id=session_id,
        )
        mock_driver.execute_agentic = MagicMock(
            return_value=AsyncIteratorMock([tool_call_msg, result_msg])
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
            severity=Severity.MINOR,
        )
        state, profile = mock_execution_state_factory(
            goal="Fix bugs",
            last_reviews=[review_result],
            code_changes_for_review="diff content",
        )

        # Mock driver to return evaluation output via execute_agentic
        self._make_agentic_mock(mock_driver, evaluation_output_with_items, "session-123")

        config = AgentConfig(driver="claude", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)
        result, session_id = await evaluator.evaluate(
            state, profile, workflow_id=uuid4()
        )

        assert session_id == "session-123"
        assert len(result.items_to_implement) == 1
        assert len(result.items_rejected) == 1
        assert len(result.items_deferred) == 1
        assert len(result.items_needing_clarification) == 1
        assert result.summary == "Mixed evaluation results"

        # Verify driver was called with execute_agentic (not generate)
        mock_driver.execute_agentic.assert_called_once()
        call_kwargs = mock_driver.execute_agentic.call_args.kwargs
        submit_tools = call_kwargs["submit_tools"]
        assert len(submit_tools) == 1
        assert submit_tools[0].name == "submit_evaluation"

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
            severity=Severity.NONE,
        )
        state, profile = mock_execution_state_factory(
            goal="Fix bugs",
            last_reviews=[review_result],
        )

        config = AgentConfig(driver="claude", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)
        result, session_id = await evaluator.evaluate(
            state, profile, workflow_id=uuid4()
        )

        # Should return empty result without calling driver
        assert result.items_to_implement == []
        assert result.items_rejected == []
        assert result.items_deferred == []
        assert result.items_needing_clarification == []
        assert "No review comments" in result.summary

        # Driver should NOT be called for empty comments
        mock_driver.execute_agentic.assert_not_called()

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
            severity=Severity.MINOR,
        )
        state, profile = mock_execution_state_factory(
            goal="Fix bugs",
            last_reviews=[review_result],
        )

        self._make_agentic_mock(mock_driver, evaluation_output, session_id="session-1")

        config = AgentConfig(driver="claude", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)
        result, _ = await evaluator.evaluate(state, profile, workflow_id=uuid4())

        # Verify correct partitioning
        assert len(result.items_to_implement) == 2
        assert len(result.items_rejected) == 1
        assert len(result.items_deferred) == 0
        assert len(result.items_needing_clarification) == 0

        # Verify item numbers are preserved
        implement_numbers = [item.number for item in result.items_to_implement]
        assert 1 in implement_numbers
        assert 2 in implement_numbers

    async def test_evaluate_requires_last_reviews(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        """Test that evaluation raises error when no last_reviews in state."""
        state, profile = mock_execution_state_factory(
            goal="Fix bugs",
        )
        # Ensure last_reviews is empty
        state = state.model_copy(update={"last_reviews": []})

        config = AgentConfig(driver="claude", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)
        with pytest.raises(ValueError, match="must have last_reviews"):
            await evaluator.evaluate(state, profile, workflow_id=uuid4())

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
            severity=Severity.NONE,
        )
        state, profile = mock_execution_state_factory(
            goal="Fix bugs",
            last_reviews=[review_result],
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
        self._make_agentic_mock(mock_driver, evaluation_output, session_id="session-1")

        config = AgentConfig(driver="claude", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config, event_bus=mock_event_bus)
        await evaluator.evaluate(state, profile, workflow_id=uuid4())

        # Verify event_bus.emit was called
        mock_event_bus.emit.assert_called_once()
        call_args = mock_event_bus.emit.call_args[0][0]
        assert call_args.agent == "evaluator"
        assert call_args.workflow_id is not None  # UUID propagated

    async def test_evaluate_submit_evaluation_first_call_wins(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        """Test that when submit_evaluation is called twice, only the first call's data is used."""
        review_result = ReviewResult(
            reviewer_persona="General",
            approved=False,
            comments=["Issue 1"],
            severity=Severity.MINOR,
        )
        state, profile = mock_execution_state_factory(
            goal="Fix bugs",
            last_reviews=[review_result],
        )

        first_output = EvaluationOutput(
            evaluated_items=[
                EvaluatedItem(
                    number=1,
                    title="First bug",
                    file_path="first.py",
                    line=1,
                    disposition=Disposition.IMPLEMENT,
                    reason="Valid first",
                    original_issue="First issue",
                    suggested_fix="First fix",
                ),
            ],
            summary="First call summary",
        )
        second_output = EvaluationOutput(
            evaluated_items=[
                EvaluatedItem(
                    number=1,
                    title="Second bug",
                    file_path="second.py",
                    line=2,
                    disposition=Disposition.REJECT,
                    reason="Invalid second",
                    original_issue="Second issue",
                    suggested_fix="Second fix",
                ),
            ],
            summary="Second call summary",
        )

        # Two tool calls followed by result
        first_tool_call = AgenticMessage(
            type=AgenticMessageType.TOOL_CALL,
            tool_name="submit_evaluation",
            tool_input=first_output.model_dump(),
        )
        second_tool_call = AgenticMessage(
            type=AgenticMessageType.TOOL_CALL,
            tool_name="submit_evaluation",
            tool_input=second_output.model_dump(),
        )
        result_msg = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="Evaluation complete",
            session_id="session-1",
        )
        mock_driver.execute_agentic = MagicMock(
            return_value=AsyncIteratorMock([first_tool_call, second_tool_call, result_msg])
        )

        config = AgentConfig(driver="claude", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)
        result, _ = await evaluator.evaluate(state, profile, workflow_id=uuid4())

        # First call wins — should have IMPLEMENT item from first output
        assert result.summary == "First call summary"
        assert len(result.items_to_implement) == 1
        assert result.items_to_implement[0].title == "First bug"
        assert len(result.items_rejected) == 0  # second call ignored

    async def test_evaluate_no_submit_evaluation_raises(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        """Test that RuntimeError is raised when submit_evaluation is never called."""
        review_result = ReviewResult(
            reviewer_persona="General",
            approved=False,
            comments=["Issue 1"],
            severity=Severity.MINOR,
        )
        state, profile = mock_execution_state_factory(
            goal="Fix bugs",
            last_reviews=[review_result],
        )

        # Only a RESULT message, no TOOL_CALL with submit_evaluation
        result_msg = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="Evaluation complete",
            session_id="session-1",
        )
        mock_driver.execute_agentic = MagicMock(
            return_value=AsyncIteratorMock([result_msg])
        )

        config = AgentConfig(driver="claude", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)

        with pytest.raises(RuntimeError, match="Evaluator did not call submit_evaluation"):
            await evaluator.evaluate(state, profile, workflow_id=uuid4())

    async def test_evaluate_propagates_driver_error_with_content(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        """Driver RESULT with is_error=True must surface the driver content verbatim."""
        review_result = ReviewResult(
            reviewer_persona="General",
            approved=False,
            comments=["Issue 1"],
            severity=Severity.MINOR,
        )
        state, profile = mock_execution_state_factory(
            goal="Fix bugs",
            last_reviews=[review_result],
        )

        result_msg = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="Prompt is too long",
            session_id="s-err",
            is_error=True,
        )
        mock_driver.execute_agentic = MagicMock(
            return_value=AsyncIteratorMock([result_msg])
        )

        config = AgentConfig(driver="claude", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)

        with pytest.raises(RuntimeError, match="Prompt is too long") as exc_info:
            await evaluator.evaluate(state, profile, workflow_id=uuid4())

        msg = str(exc_info.value)
        assert "Evaluator" in msg or "driver" in msg.lower()
        assert "did not call submit_evaluation" not in msg

    async def test_evaluate_no_tool_call_without_driver_error_still_raises_missing(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        """Non-error RESULT without submit_evaluation still raises the missing-tool error."""
        review_result = ReviewResult(
            reviewer_persona="General",
            approved=False,
            comments=["Issue 1"],
            severity=Severity.MINOR,
        )
        state, profile = mock_execution_state_factory(
            goal="Fix bugs",
            last_reviews=[review_result],
        )

        result_msg = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="ok",
            session_id="s-ok",
            is_error=False,
        )
        mock_driver.execute_agentic = MagicMock(
            return_value=AsyncIteratorMock([result_msg])
        )

        config = AgentConfig(driver="claude", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)

        with pytest.raises(RuntimeError, match="did not call submit_evaluation"):
            await evaluator.evaluate(state, profile, workflow_id=uuid4())

    async def test_evaluate_driver_error_without_content(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    ) -> None:
        """is_error=True with empty content still identifies as a driver-side failure."""
        review_result = ReviewResult(
            reviewer_persona="General",
            approved=False,
            comments=["Issue 1"],
            severity=Severity.MINOR,
        )
        state, profile = mock_execution_state_factory(
            goal="Fix bugs",
            last_reviews=[review_result],
        )

        result_msg = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content=None,
            session_id="s-err",
            is_error=True,
        )
        mock_driver.execute_agentic = MagicMock(
            return_value=AsyncIteratorMock([result_msg])
        )

        config = AgentConfig(driver="claude", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)

        with pytest.raises(RuntimeError) as exc_info:
            await evaluator.evaluate(state, profile, workflow_id=uuid4())

        msg = str(exc_info.value).lower()
        assert "driver" in msg or "claude cli" in msg
        assert "did not call submit_evaluation" not in str(exc_info.value)

    async def test_evaluate_uses_execute_agentic_with_allowed_tools(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
        evaluation_output_with_items: EvaluationOutput,
    ) -> None:
        """Test that execute_agentic is called with allowed_tools=['submit_evaluation']."""
        review_result = ReviewResult(
            reviewer_persona="General",
            approved=False,
            comments=["Issue 1", "Issue 2", "Issue 3", "Issue 4"],
            severity=Severity.MINOR,
        )
        state, profile = mock_execution_state_factory(
            goal="Fix bugs",
            last_reviews=[review_result],
        )

        self._make_agentic_mock(mock_driver, evaluation_output_with_items)

        config = AgentConfig(driver="claude", model="sonnet")
        with patch("amelia.agents.evaluator.get_driver", return_value=mock_driver):
            evaluator = Evaluator(config)
        await evaluator.evaluate(state, profile, workflow_id=uuid4())

        # execute_agentic should be called with submit_tools containing submit_evaluation
        mock_driver.execute_agentic.assert_called_once()
        call_kwargs = mock_driver.execute_agentic.call_args.kwargs
        submit_tools = call_kwargs["submit_tools"]
        assert len(submit_tools) == 1
        assert submit_tools[0].name == "submit_evaluation"

        # generate should NOT have been called
        mock_driver.generate.assert_not_called()
