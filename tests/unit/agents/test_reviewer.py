"""Tests for the Reviewer agent."""
import inspect
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.agents.reviewer import (
    Reviewer,
    ReviewItem,
    StructuredReviewResult,
    normalize_severity,
)
from amelia.core.state import ExecutionState
from amelia.core.types import Profile
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.server.models.events import EventType
from tests.conftest import AsyncIteratorMock


class TestNormalizeSeverity:
    """Tests for normalize_severity helper function."""

    @pytest.mark.parametrize("input_val,expected", [
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
        ("critical", "critical"),
        ("none", "medium"),
        ("invalid", "medium"),
        ("", "medium"),
        ("CRITICAL", "medium"),  # Case sensitive
    ])
    def test_normalize_severity(self, input_val: str, expected: str) -> None:
        """Test severity normalization with various inputs."""
        assert normalize_severity(input_val) == expected

    def test_none_value_returns_default(self) -> None:
        """Test that None returns the default."""
        assert normalize_severity(None) == "medium"

    def test_custom_default(self) -> None:
        """Test that custom default is used for invalid values."""
        assert normalize_severity("none", default="high") == "high"
        assert normalize_severity(None, default="critical") == "critical"


class TestReviewItem:
    """Tests for ReviewItem model."""

    def test_review_item_severity_values(self) -> None:
        """Test that severity accepts only valid values."""
        for severity in ["critical", "major", "minor"]:
            item = ReviewItem(
                number=1,
                title="Test",
                file_path="test.py",
                line=1,
                severity=severity,  # type: ignore[arg-type]
                issue="Issue",
                why="Why",
                fix="Fix",
            )
            assert item.severity == severity


class TestStructuredReviewResult:
    """Tests for StructuredReviewResult model."""

    def test_structured_review_result_verdict_values(self) -> None:
        """Test that verdict accepts only valid values."""
        for verdict in ["approved", "needs_fixes", "blocked"]:
            result = StructuredReviewResult(
                summary="Review",
                items=[],
                verdict=verdict,  # type: ignore[arg-type]
            )
            assert result.verdict == verdict

    def test_structured_review_result_default_good_patterns(self) -> None:
        """Test that good_patterns defaults to empty list."""
        result = StructuredReviewResult(
            summary="Review",
            items=[],
            verdict="approved",
        )
        assert result.good_patterns == []


class TestStructuredReview:
    """Tests for Reviewer.structured_review method."""

    @pytest.fixture
    def reviewer(self, mock_driver: MagicMock) -> Reviewer:
        """Create a Reviewer instance with mocked driver."""
        return Reviewer(driver=mock_driver)

    @pytest.fixture
    def structured_review_output(self) -> StructuredReviewResult:
        """Create a sample structured review output."""
        return StructuredReviewResult(
            summary="Code review completed with minor issues",
            items=[
                ReviewItem(
                    number=1,
                    title="Missing type hint",
                    file_path="src/main.py",
                    line=15,
                    severity="minor",
                    issue="Function lacks return type annotation",
                    why="Type hints improve code maintainability",
                    fix="Add -> None return type",
                ),
                ReviewItem(
                    number=2,
                    title="Potential null reference",
                    file_path="src/utils.py",
                    line=42,
                    severity="major",
                    issue="Variable may be None before use",
                    why="Could cause runtime exception",
                    fix="Add null check before accessing",
                ),
            ],
            good_patterns=["Consistent naming", "Good error handling"],
            verdict="needs_fixes",
        )

    async def test_structured_review_returns_structured_result(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
        structured_review_output: StructuredReviewResult,
    ) -> None:
        """Test structured_review returns StructuredReviewResult."""
        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        mock_driver.generate = AsyncMock(
            return_value=(structured_review_output, "session-456")
        )

        reviewer = Reviewer(driver=mock_driver)
        result, session_id = await reviewer.structured_review(
            state,
            code_changes="diff content",
            profile=profile,
            workflow_id="wf-123",
        )

        assert isinstance(result, StructuredReviewResult)
        assert session_id == "session-456"
        assert result.summary == "Code review completed with minor issues"
        assert len(result.items) == 2
        assert result.verdict == "needs_fixes"
        assert len(result.good_patterns) == 2

        # Verify driver was called with correct schema
        mock_driver.generate.assert_called_once()
        call_kwargs = mock_driver.generate.call_args.kwargs
        assert call_kwargs["schema"] == StructuredReviewResult

    async def test_structured_review_empty_changes_auto_approves(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test empty code changes result in auto-approval."""
        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        reviewer = Reviewer(driver=mock_driver)

        # Test with empty string
        result, session_id = await reviewer.structured_review(
            state,
            code_changes="",
            profile=profile,
            workflow_id="wf-123",
        )

        assert result.verdict == "approved"
        assert result.items == []
        assert "No code changes" in result.summary

        # Driver should NOT be called for empty changes
        mock_driver.generate.assert_not_called()

    async def test_structured_review_whitespace_only_auto_approves(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test whitespace-only code changes result in auto-approval."""
        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        reviewer = Reviewer(driver=mock_driver)

        result, _ = await reviewer.structured_review(
            state,
            code_changes="   \n\t  ",
            profile=profile,
            workflow_id="wf-123",
        )

        assert result.verdict == "approved"
        assert result.items == []
        mock_driver.generate.assert_not_called()

    async def test_structured_review_with_stream_emitter(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
        structured_review_output: StructuredReviewResult,
    ) -> None:
        """Test that event_bus.emit is called during structured review."""
        mock_event_bus = MagicMock()

        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        mock_driver.generate = AsyncMock(
            return_value=(structured_review_output, None)
        )

        reviewer = Reviewer(driver=mock_driver, event_bus=mock_event_bus)
        await reviewer.structured_review(
            state,
            code_changes="diff content",
            profile=profile,
            workflow_id="wf-123",
        )

        # Verify event_bus.emit was called
        mock_event_bus.emit.assert_called_once()
        call_args = mock_event_bus.emit.call_args[0][0]
        assert call_args.agent == "reviewer"
        assert call_args.workflow_id == "wf-123"

    async def test_structured_review_builds_prompt_with_goal(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that prompt includes goal when available."""
        state, profile = mock_execution_state_factory(
            goal="Implement authentication",
        )

        review_output = StructuredReviewResult(
            summary="Review",
            items=[],
            verdict="approved",
        )
        mock_driver.generate = AsyncMock(return_value=(review_output, None))

        reviewer = Reviewer(driver=mock_driver)
        await reviewer.structured_review(
            state,
            code_changes="diff content",
            profile=profile,
            workflow_id="wf-123",
        )

        # Check that prompt contains the goal
        call_args = mock_driver.generate.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "Implement authentication" in prompt

    async def test_structured_review_builds_prompt_with_issue_fallback(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that prompt uses issue context when no goal available."""
        state, profile = mock_execution_state_factory(
            goal=None,  # No goal
        )

        review_output = StructuredReviewResult(
            summary="Review",
            items=[],
            verdict="approved",
        )
        mock_driver.generate = AsyncMock(return_value=(review_output, None))

        reviewer = Reviewer(driver=mock_driver)
        await reviewer.structured_review(
            state,
            code_changes="diff content",
            profile=profile,
            workflow_id="wf-123",
        )

        # Check that prompt contains issue context
        call_args = mock_driver.generate.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "Test Issue" in prompt or "Issue" in prompt

    async def test_structured_review_uses_structured_system_prompt(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that structured_review uses STRUCTURED_SYSTEM_PROMPT."""
        state, profile = mock_execution_state_factory(
            goal="Test goal",
        )

        review_output = StructuredReviewResult(
            summary="Review",
            items=[],
            verdict="approved",
        )
        mock_driver.generate = AsyncMock(return_value=(review_output, None))

        reviewer = Reviewer(driver=mock_driver)
        await reviewer.structured_review(
            state,
            code_changes="diff content",
            profile=profile,
            workflow_id="wf-123",
        )

        # Verify system prompt is the structured one
        call_args = mock_driver.generate.call_args
        system_prompt = call_args.kwargs.get("system_prompt")
        assert "OUTPUT FORMAT" in system_prompt
        assert "SEVERITY LEVELS" in system_prompt


class TestReviewer:
    """Tests for Reviewer agent review method."""

    async def test_review_requires_context(
        self,
        mock_driver: MagicMock,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Test that review raises error when no task or issue context."""
        # Create state manually without issue or goal (factory defaults issue)
        profile = mock_profile_factory()
        state = ExecutionState(
            profile_id=profile.name,
            issue=None,
            goal=None,
        )

        reviewer = Reviewer(driver=mock_driver)
        with pytest.raises(ValueError, match="No task or issue context"):
            await reviewer.review(
                state,
                code_changes="diff content",
                profile=profile,
                workflow_id="wf-123",
            )

    async def test_review_empty_changes_auto_approves(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that empty code changes result in auto-approval."""
        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        reviewer = Reviewer(driver=mock_driver)
        result, _ = await reviewer.review(
            state,
            code_changes="",
            profile=profile,
            workflow_id="wf-123",
        )

        assert result.approved is True
        assert "No code changes" in result.comments[0]
        mock_driver.generate.assert_not_called()


class TestAgenticReview:
    """Tests for Reviewer.agentic_review with unified AgenticMessage processing."""

    def test_no_isinstance_checks_on_driver_types(self) -> None:
        """Verify agentic_review does not use isinstance checks on driver types.

        The unified execution path should use AgenticMessage exclusively,
        without checking for specific driver types like ClaudeCliDriver or ApiDriver.
        """
        source = inspect.getsource(Reviewer.agentic_review)

        # Driver types that should NOT be checked via isinstance
        # Check for common isinstance patterns with these driver types
        forbidden_patterns = [
            "isinstance(self.driver, ClaudeCliDriver)",
            "isinstance(self.driver, ApiDriver)",
            "isinstance(driver, ClaudeCliDriver)",
            "isinstance(driver, ApiDriver)",
        ]

        for pattern in forbidden_patterns:
            assert pattern not in source, (
                f"agentic_review uses isinstance check: '{pattern}'. "
                "Should use unified AgenticMessage processing instead."
            )

    async def test_processes_agentic_message_stream(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that agentic_review processes AgenticMessage stream from driver."""
        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        # Create mock AgenticMessage stream
        messages = [
            AgenticMessage(
                type=AgenticMessageType.THINKING,
                content="Analyzing the code changes...",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="Bash",
                tool_input={"command": "git diff abc123"},
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="Bash",
                tool_output="diff --git a/file.py...",
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content='```json\n{"approved": true, "comments": ["LGTM"], "severity": "low"}\n```',
                session_id="session-789",
            ),
        ]
        mock_driver.execute_agentic = MagicMock(return_value=AsyncIteratorMock(messages))

        reviewer = Reviewer(driver=mock_driver)
        result, session_id = await reviewer.agentic_review(
            state,
            base_commit="abc123",
            profile=profile,
            workflow_id="wf-123",
        )

        assert result.approved is True
        assert "LGTM" in result.comments
        assert result.severity == "low"
        assert session_id == "session-789"

        # Verify execute_agentic was called
        mock_driver.execute_agentic.assert_called_once()

    async def test_agentic_review_emits_workflow_events(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that workflow events are emitted for AgenticMessage stream."""
        mock_event_bus = MagicMock()
        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        # Create mock AgenticMessage stream with various message types
        messages = [
            AgenticMessage(
                type=AgenticMessageType.THINKING,
                content="Reviewing code...",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="Bash",
                tool_input={"command": "git diff abc123"},
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="Bash",
                tool_output="file diff output",
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content='{"approved": true, "comments": [], "severity": "low"}',
                session_id="session-789",
            ),
        ]
        mock_driver.execute_agentic = MagicMock(return_value=AsyncIteratorMock(messages))

        reviewer = Reviewer(driver=mock_driver, event_bus=mock_event_bus)
        await reviewer.agentic_review(
            state,
            base_commit="abc123",
            profile=profile,
            workflow_id="wf-123",
        )

        # Should emit events for THINKING, TOOL_CALL, TOOL_RESULT + final output
        # At minimum 3 events during stream + 1 final output event
        assert mock_event_bus.emit.call_count >= 3

        # Verify event types were properly mapped
        event_types = [call.args[0].event_type for call in mock_event_bus.emit.call_args_list]
        assert EventType.CLAUDE_THINKING in event_types
        assert EventType.CLAUDE_TOOL_CALL in event_types

    async def test_agentic_review_handles_error_result(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that agentic_review handles error results correctly."""
        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        # Create mock AgenticMessage stream with error result
        messages = [
            AgenticMessage(
                type=AgenticMessageType.THINKING,
                content="Starting review...",
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Failed to execute review",
                session_id="session-error",
                is_error=True,
            ),
        ]
        mock_driver.execute_agentic = MagicMock(return_value=AsyncIteratorMock(messages))

        reviewer = Reviewer(driver=mock_driver)
        result, session_id = await reviewer.agentic_review(
            state,
            base_commit="abc123",
            profile=profile,
            workflow_id="wf-123",
        )

        # Should still return a result, but not approved
        assert result.approved is False
        assert session_id == "session-error"

    async def test_agentic_review_uses_to_workflow_event(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that agentic_review uses AgenticMessage.to_workflow_event() for conversion."""
        mock_event_bus = MagicMock()
        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        # Create mock AgenticMessage stream
        messages = [
            AgenticMessage(
                type=AgenticMessageType.THINKING,
                content="Reviewing changes...",
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content='{"approved": true, "comments": [], "severity": "low"}',
                session_id="session-123",
            ),
        ]
        mock_driver.execute_agentic = MagicMock(return_value=AsyncIteratorMock(messages))

        reviewer = Reviewer(driver=mock_driver, event_bus=mock_event_bus)
        await reviewer.agentic_review(
            state,
            base_commit="abc123",
            profile=profile,
            workflow_id="wf-123",
        )

        # Verify workflow events have correct agent and workflow_id (set by to_workflow_event)
        for call in mock_event_bus.emit.call_args_list:
            event = call.args[0]
            assert event.agent == "reviewer"
            assert event.workflow_id == "wf-123"

    async def test_agentic_review_parses_json_result(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that agentic_review correctly parses JSON result from agent."""
        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        # Create mock AgenticMessage stream with JSON result in markdown fence
        messages = [
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content='Some analysis text\n\n```json\n{"approved": false, "comments": ["Fix bug in line 42", "Add tests"], "severity": "high"}\n```\n\nEnd of review.',
                session_id="session-123",
            ),
        ]
        mock_driver.execute_agentic = MagicMock(return_value=AsyncIteratorMock(messages))

        reviewer = Reviewer(driver=mock_driver)
        result, session_id = await reviewer.agentic_review(
            state,
            base_commit="abc123",
            profile=profile,
            workflow_id="wf-123",
        )

        assert result.approved is False
        assert len(result.comments) == 2
        assert "Fix bug in line 42" in result.comments
        assert "Add tests" in result.comments
        assert result.severity == "high"

    async def test_agentic_review_handles_invalid_severity_from_llm(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that agentic_review handles invalid severity values from LLM.

        LLMs may return severity values like "none" that are not in the
        Severity literal type. The parser should normalize these to valid values.
        """
        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        # Create mock AgenticMessage with invalid severity "none"
        messages = [
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content='```json\n{"approved": true, "comments": ["LGTM"], "severity": "none"}\n```',
                session_id="session-invalid",
            ),
        ]
        mock_driver.execute_agentic = MagicMock(return_value=AsyncIteratorMock(messages))

        reviewer = Reviewer(driver=mock_driver)
        # This should NOT raise ValidationError
        result, session_id = await reviewer.agentic_review(
            state,
            base_commit="abc123",
            profile=profile,
            workflow_id="wf-123",
        )

        # Invalid "none" should be normalized to "medium"
        assert result.severity == "medium"
        assert result.approved is True
        assert session_id == "session-invalid"

    async def test_agentic_review_no_sdk_type_imports(self) -> None:
        """Verify agentic_review doesn't import SDK-specific types for message handling.

        The unified execution path should only use AgenticMessage types,
        not claude_agent_sdk.types or langchain_core.messages.
        """
        source = inspect.getsource(Reviewer.agentic_review)

        # SDK-specific types that should NOT be imported/used for message handling
        forbidden_patterns = [
            "AssistantMessage",
            "ResultMessage",
            "TextBlock",
            "ToolUseBlock",
            "ToolResultBlock",
            "AIMessage",
            "ToolMessage",
        ]

        for pattern in forbidden_patterns:
            assert pattern not in source, (
                f"agentic_review references SDK-specific type '{pattern}'. "
                "Should use unified AgenticMessage types instead."
            )
