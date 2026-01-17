"""Tests for the Reviewer agent."""
import inspect
from collections.abc import Callable
from unittest.mock import MagicMock

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

        # Create mock AgenticMessage stream with beagle markdown format
        beagle_review_output = """## Review Summary

Code looks good overall.

## Issues

### Critical (Blocking)

### Major (Should Fix)

### Minor (Nice to Have)

## Good Patterns

- [file.py:10] Good use of type hints

## Verdict

Ready: Yes
Rationale: No issues found, code is ready to merge.
"""
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
                content=beagle_review_output,
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
        assert len(result.comments) == 0  # No issues found
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

    async def test_agentic_review_parses_beagle_markdown_result(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that agentic_review correctly parses beagle markdown result from agent."""
        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        # Create mock AgenticMessage stream with beagle markdown format
        beagle_review_output = """## Review Summary

Found 2 issues that should be addressed.

## Issues

### Critical (Blocking)

### Major (Should Fix)

1. [file.py:42] Fix bug in error handling
   - Issue: Missing null check
   - Why: Could cause crash
   - Fix: Add null check before access

2. [file.py:100] Add tests for new functionality
   - Issue: No test coverage
   - Why: Risk of regressions
   - Fix: Add unit tests

### Minor (Nice to Have)

## Good Patterns

- [file.py:10] Good use of type hints

## Verdict

Ready: No
Rationale: Two major issues need to be fixed first.
"""
        messages = [
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content=beagle_review_output,
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
        assert "[major]" in result.comments[0].lower()
        assert "file.py:42" in result.comments[0]
        assert result.severity == "high"  # major maps to high

    async def test_agentic_review_determines_severity_from_highest_issue(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that agentic_review determines overall severity from highest issue severity.

        The parser should map issue severities to ReviewResult severity:
        - critical → critical
        - major → high
        - minor → medium
        """
        state, profile = mock_execution_state_factory(
            goal="Implement feature",
        )

        # Create mock AgenticMessage with critical issue
        beagle_review_output = """## Review Summary

Found a critical security issue.

## Issues

### Critical (Blocking)

1. [auth.py:10] SQL Injection vulnerability
   - Issue: User input not sanitized
   - Why: Security vulnerability
   - Fix: Use parameterized queries

### Major (Should Fix)

### Minor (Nice to Have)

2. [utils.py:5] Typo in comment
   - Issue: Minor typo
   - Why: Code clarity
   - Fix: Fix typo

## Good Patterns

## Verdict

Ready: No
Rationale: Critical security issue must be fixed.
"""
        messages = [
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content=beagle_review_output,
                session_id="session-critical",
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

        # Overall severity should be critical (highest)
        assert result.severity == "critical"
        assert result.approved is False
        assert len(result.comments) == 2
        assert session_id == "session-critical"

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


class TestParseReviewResult:
    """Tests for Reviewer._parse_review_result method."""

    def test_markdown_bold_ready_yes_with_needs_fixes_in_rationale(
        self,
        mock_driver: MagicMock,
    ) -> None:
        """Test that **Ready:** Yes is correctly parsed even when 'needs fixes' in rationale.

        Regression test for bug where:
        1. Regex r"Ready:\\s*(Yes|No|With fixes[^\\n]*)" doesn't match **Ready:** Yes
        2. Fallback finds "needs fixes" in rationale and incorrectly sets approved=False
        """
        # Beagle markdown with bold formatting and "needs fixes" in rationale
        beagle_output = """## Review Summary

Code looks good overall with no issues found.

## Issues

### Critical (Blocking)

### Major (Should Fix)

### Minor (Nice to Have)

## Good Patterns

- [file.py:10] Good use of type hints

## Verdict

**Ready:** Yes
Rationale: Code needs fixes for edge cases but they are out of scope.
"""
        reviewer = Reviewer(driver=mock_driver)
        result = reviewer._parse_review_result(beagle_output, workflow_id="wf-test")

        # Should be approved because verdict says "Ready: Yes"
        assert result.approved is True, (
            "Review should be approved when **Ready:** Yes is present, "
            "even if 'needs fixes' appears elsewhere in the output"
        )

    def test_markdown_bold_only_on_ready_word(
        self,
        mock_driver: MagicMock,
    ) -> None:
        """Test that **Ready**: Yes is correctly parsed (bold only on 'Ready', not 'Ready:').

        Regression test for bug where regex r"[*_]{0,2}Ready:[*_]{0,2}..." failed
        when bold markers appear between 'Ready' and ':' like **Ready**: Yes.
        The fix changes the pattern to allow markers between Ready and colon.
        """
        beagle_output = """## Review Summary

Code looks good overall.

## Issues

### Critical (Blocking)

### Major (Should Fix)

### Minor (Nice to Have)

## Good Patterns

- [file.py:10] Good use of type hints

## Verdict

**Ready**: Yes
Rationale: All checks pass.
"""
        reviewer = Reviewer(driver=mock_driver)
        result = reviewer._parse_review_result(beagle_output, workflow_id="wf-test")

        assert result.approved is True, (
            "Review should be approved when **Ready**: Yes is present "
            "(bold only on 'Ready' word, colon outside bold)"
        )


class TestExtractTaskContext:
    """Tests for Reviewer._extract_task_context task extraction."""

    @pytest.fixture
    def multi_task_plan(self) -> str:
        """A plan with 3 tasks."""
        return """# Plan

## Goal
Multi-task feature.

---

### Task 1: Create module
First task content.

### Task 2: Add validation
Second task content.

### Task 3: Write tests
Third task content.
"""

    def test_single_task_returns_full_plan(self) -> None:
        """When total_tasks is None or 1, return full plan."""
        state = ExecutionState(
            profile_id="test",
            goal="Implement feature",
            plan_markdown="# Simple Plan\n\nJust do it.",
            total_tasks=None,
            current_task_index=0,
        )
        reviewer = Reviewer(driver=None)  # type: ignore[arg-type]
        context = reviewer._extract_task_context(state)

        assert context is not None
        assert "**Task:**" in context
        assert "Simple Plan" in context

    def test_multi_task_extracts_current_section(
        self, multi_task_plan: str
    ) -> None:
        """For multi-task, extract current task with index label."""
        state = ExecutionState(
            profile_id="test",
            goal="Implement feature",
            plan_markdown=multi_task_plan,
            total_tasks=3,
            current_task_index=1,  # Task 2
        )
        reviewer = Reviewer(driver=None)  # type: ignore[arg-type]
        context = reviewer._extract_task_context(state)

        assert context is not None
        assert "Current Task (2/3)" in context
        assert "Add validation" in context

    def test_no_plan_returns_goal_fallback(self) -> None:
        """Without plan, fall back to goal."""
        state = ExecutionState(
            profile_id="test",
            goal="Just do the thing",
            plan_markdown=None,
        )
        reviewer = Reviewer(driver=None)  # type: ignore[arg-type]
        context = reviewer._extract_task_context(state)

        assert context is not None
        assert "Just do the thing" in context
