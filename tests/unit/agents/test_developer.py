# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for Developer agent streaming."""

from collections.abc import Callable
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from amelia.agents.developer import Developer, ValidationResult
from amelia.core.state import ExecutionState
from amelia.core.types import StreamEvent, StreamEventType
from amelia.drivers.cli.claude import ClaudeStreamEvent


@pytest.fixture
def mock_stream_emitter() -> AsyncMock:
    """Create a mock stream emitter."""
    return AsyncMock()


class TestDeveloperStreamEmitter:
    """Test Developer agent stream emitter functionality."""

    async def test_developer_emits_stream_events_during_agentic_execution(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
        mock_issue_factory: Callable[..., Any],
        mock_stream_emitter: AsyncMock,
        async_iterator_mock_factory: Callable[[list[Any]], Any],
    ) -> None:
        """Test that Developer emits stream events during agentic execution."""
        # Create issue for workflow_id fallback
        issue = mock_issue_factory(id="TEST-123", title="Test", description="Test")

        # Create driver and state with task and TaskDAG
        mock_driver, state = developer_test_context(task_desc="Test task")
        state.issue = issue
        state.plan.original_issue = "TEST-123"

        # Mock driver to return streaming events
        mock_events = [
            ClaudeStreamEvent(type="assistant", content="Thinking about the task..."),
            ClaudeStreamEvent(type="tool_use", tool_name="bash", tool_input={"command": "echo test"}),
            ClaudeStreamEvent(type="result"),
        ]

        mock_driver.execute_agentic.return_value = async_iterator_mock_factory(mock_events)

        # Create developer with emitter
        developer = Developer(
            driver=mock_driver,
            execution_mode="agentic",
            stream_emitter=mock_stream_emitter,
        )

        # Execute task
        await developer.execute_current_task(state, workflow_id="TEST-123")

        # Verify emitter was called
        assert mock_stream_emitter.called
        assert mock_stream_emitter.call_count >= 2  # At least assistant and tool_use events

        # Verify the emitted events have correct structure
        for call in mock_stream_emitter.call_args_list:
            event = call.args[0]
            assert isinstance(event, StreamEvent)
            assert event.agent == "developer"
            assert event.workflow_id == "TEST-123"  # Uses provided workflow_id
            assert isinstance(event.timestamp, datetime)
            assert event.type in [
                StreamEventType.CLAUDE_THINKING,
                StreamEventType.CLAUDE_TOOL_CALL,
                StreamEventType.CLAUDE_TOOL_RESULT,
            ]

    async def test_developer_does_not_emit_when_no_emitter_configured(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
        mock_issue_factory: Callable[..., Any],
        async_iterator_mock_factory: Callable[[list[Any]], Any],
    ) -> None:
        """Test that Developer does not crash when no emitter is configured."""
        issue = mock_issue_factory(id="TEST-456", title="Test", description="Test")

        # Create driver and state with task and TaskDAG
        mock_driver, state = developer_test_context(task_desc="Test task")
        state.issue = issue
        state.plan.original_issue = "TEST-456"

        mock_events = [
            ClaudeStreamEvent(type="assistant", content="Working..."),
            ClaudeStreamEvent(type="result"),
        ]

        mock_driver.execute_agentic.return_value = async_iterator_mock_factory(mock_events)

        # Create developer WITHOUT emitter
        developer = Developer(
            driver=mock_driver,
            execution_mode="agentic",
        )

        # Should not raise even without emitter
        result = await developer.execute_current_task(state, workflow_id="TEST-456")
        assert result["status"] == "completed"

    async def test_developer_converts_claude_events_to_stream_events(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
        mock_issue_factory: Callable[..., Any],
        mock_stream_emitter: AsyncMock,
        async_iterator_mock_factory: Callable[[list[Any]], Any],
    ) -> None:
        """Test that Developer converts ClaudeStreamEvents to StreamEvents correctly."""
        issue = mock_issue_factory(id="TEST-789", title="Test", description="Test")

        # Create driver and state with task and TaskDAG
        mock_driver, state = developer_test_context(task_desc="Test task")
        state.issue = issue
        state.plan.original_issue = "TEST-789"

        # Test each event type conversion
        mock_events = [
            ClaudeStreamEvent(type="assistant", content="Analyzing code..."),
            ClaudeStreamEvent(
                type="tool_use",
                tool_name="bash",
                tool_input={"command": "pytest"}
            ),
            ClaudeStreamEvent(type="result"),
        ]

        mock_driver.execute_agentic.return_value = async_iterator_mock_factory(mock_events)

        developer = Developer(
            driver=mock_driver,
            execution_mode="agentic",
            stream_emitter=mock_stream_emitter,
        )

        await developer.execute_current_task(state, workflow_id="TEST-789")

        # Verify conversions
        emitted_events = [call.args[0] for call in mock_stream_emitter.call_args_list]

        # Find assistant event
        thinking_events = [e for e in emitted_events if e.type == StreamEventType.CLAUDE_THINKING]
        assert len(thinking_events) == 1
        assert thinking_events[0].content == "Analyzing code..."

        # Find tool_use event
        tool_events = [e for e in emitted_events if e.type == StreamEventType.CLAUDE_TOOL_CALL]
        assert len(tool_events) == 1
        assert tool_events[0].tool_name == "bash"
        assert tool_events[0].tool_input == {"command": "pytest"}

        # Find result event
        result_events = [e for e in emitted_events if e.type == StreamEventType.CLAUDE_TOOL_RESULT]
        assert len(result_events) == 1


class TestFilesystemChecks:
    """Test Developer._filesystem_checks method."""

    async def test_code_action_file_exists(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
        tmp_path: Any,
    ) -> None:
        """Test filesystem check passes when modifying an existing file."""
        from amelia.core.state import PlanStep

        # Create a test file
        test_file = tmp_path / "existing_file.py"
        test_file.write_text("# existing code")

        mock_driver, _ = developer_test_context()
        developer = Developer(driver=mock_driver)

        step = PlanStep(
            id="step1",
            description="Modify existing file",
            action_type="code",
            file_path=str(test_file),
            code_change="# new code",
        )

        result = await developer._filesystem_checks(step)

        assert result.ok is True
        assert result.issue is None

    async def test_code_action_file_not_exists_parent_exists(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
        tmp_path: Any,
    ) -> None:
        """Test filesystem check passes when creating a new file in existing directory."""
        from amelia.core.state import PlanStep

        # Parent directory exists, but file doesn't
        test_file = tmp_path / "new_file.py"

        mock_driver, _ = developer_test_context()
        developer = Developer(driver=mock_driver)

        step = PlanStep(
            id="step2",
            description="Create new file",
            action_type="code",
            file_path=str(test_file),
            code_change="# new code",
        )

        result = await developer._filesystem_checks(step)

        assert result.ok is True
        assert result.issue is None

    async def test_code_action_parent_dir_not_exists(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
        tmp_path: Any,
    ) -> None:
        """Test filesystem check fails when parent directory doesn't exist."""
        from amelia.core.state import PlanStep

        # Parent directory doesn't exist
        test_file = tmp_path / "nonexistent_dir" / "new_file.py"

        mock_driver, _ = developer_test_context()
        developer = Developer(driver=mock_driver)

        step = PlanStep(
            id="step3",
            description="Create file in nonexistent directory",
            action_type="code",
            file_path=str(test_file),
            code_change="# new code",
        )

        result = await developer._filesystem_checks(step)

        assert result.ok is False
        assert result.issue is not None
        assert "parent directory" in result.issue.lower()

    async def test_command_action_executable_exists(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test filesystem check passes when command executable is available."""
        from amelia.core.state import PlanStep

        mock_driver, _ = developer_test_context()
        developer = Developer(driver=mock_driver)

        # Use 'echo' which should be available on all systems
        step = PlanStep(
            id="step4",
            description="Run echo command",
            action_type="command",
            command="echo 'hello world'",
        )

        result = await developer._filesystem_checks(step)

        assert result.ok is True
        assert result.issue is None

    async def test_command_action_executable_not_found(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test filesystem check fails when command executable is not found."""
        from amelia.core.state import PlanStep

        mock_driver, _ = developer_test_context()
        developer = Developer(driver=mock_driver)

        # Use a command that definitely doesn't exist
        step = PlanStep(
            id="step5",
            description="Run nonexistent command",
            action_type="command",
            command="this_command_definitely_does_not_exist_12345 arg1 arg2",
        )

        result = await developer._filesystem_checks(step)

        assert result.ok is False
        assert result.issue is not None
        assert "command not found" in result.issue.lower()

    async def test_cwd_check_exists(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
        tmp_path: Any,
    ) -> None:
        """Test filesystem check passes when cwd exists."""
        from amelia.core.state import PlanStep

        mock_driver, _ = developer_test_context()
        developer = Developer(driver=mock_driver)

        step = PlanStep(
            id="step6",
            description="Run command in specific directory",
            action_type="command",
            command="echo test",
            cwd=str(tmp_path),
        )

        result = await developer._filesystem_checks(step)

        assert result.ok is True
        assert result.issue is None

    async def test_cwd_check_not_exists(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
        tmp_path: Any,
    ) -> None:
        """Test filesystem check fails when cwd doesn't exist."""
        from amelia.core.state import PlanStep

        mock_driver, _ = developer_test_context()
        developer = Developer(driver=mock_driver)

        nonexistent_dir = tmp_path / "nonexistent_cwd"

        step = PlanStep(
            id="step7",
            description="Run command in nonexistent directory",
            action_type="command",
            command="echo test",
            cwd=str(nonexistent_dir),
        )

        result = await developer._filesystem_checks(step)

        assert result.ok is False
        assert result.issue is not None
        assert "working directory" in result.issue.lower()

    async def test_validation_action_no_filesystem_checks(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test filesystem check passes for validation actions without specific checks."""
        from amelia.core.state import PlanStep

        mock_driver, _ = developer_test_context()
        developer = Developer(driver=mock_driver)

        step = PlanStep(
            id="step8",
            description="Validate implementation",
            action_type="validation",
            validation_command="pytest tests/",
        )

        result = await developer._filesystem_checks(step)

        # For validation actions, we just check cwd if specified
        # Since no cwd is specified, it should pass
        assert result.ok is True
        assert result.issue is None


class TestValidateCommandResult:
    """Test validate_command_result function."""

    def test_exit_code_validation_success(self) -> None:
        """Test that validation passes when exit code matches expected."""
        from amelia.agents.developer import validate_command_result
        from amelia.core.state import PlanStep

        step = PlanStep(
            id="step1",
            description="Run test",
            action_type="command",
            command="pytest",
            expect_exit_code=0,
        )

        result = validate_command_result(exit_code=0, stdout="All tests passed", step=step)
        assert result is True

    def test_exit_code_validation_failure(self) -> None:
        """Test that validation fails when exit code doesn't match expected."""
        from amelia.agents.developer import validate_command_result
        from amelia.core.state import PlanStep

        step = PlanStep(
            id="step2",
            description="Run test expecting failure",
            action_type="command",
            command="pytest",
            expect_exit_code=0,
        )

        result = validate_command_result(exit_code=1, stdout="Tests failed", step=step)
        assert result is False

    def test_regex_pattern_matching_on_stripped_output(self) -> None:
        """Test that ANSI codes are stripped before regex matching."""
        from amelia.agents.developer import validate_command_result
        from amelia.core.state import PlanStep

        step = PlanStep(
            id="step3",
            description="Check for success message",
            action_type="command",
            command="pytest",
            expect_exit_code=0,
            expected_output_pattern=r"All tests passed",
        )

        # stdout with ANSI color codes
        stdout_with_ansi = "\x1b[32mAll tests passed\x1b[0m"

        result = validate_command_result(exit_code=0, stdout=stdout_with_ansi, step=step)
        assert result is True

    def test_passes_when_pattern_is_none(self) -> None:
        """Test that validation passes when no pattern is specified."""
        from amelia.agents.developer import validate_command_result
        from amelia.core.state import PlanStep

        step = PlanStep(
            id="step4",
            description="Run command without pattern",
            action_type="command",
            command="echo test",
            expect_exit_code=0,
            expected_output_pattern=None,
        )

        result = validate_command_result(exit_code=0, stdout="any output here", step=step)
        assert result is True

    def test_exit_code_default_zero(self) -> None:
        """Test that expect_exit_code defaults to 0 if not specified."""
        from amelia.agents.developer import validate_command_result
        from amelia.core.state import PlanStep

        # PlanStep has default expect_exit_code=0
        step = PlanStep(
            id="step5",
            description="Run command with default exit code",
            action_type="command",
            command="echo test",
        )

        # Should pass with exit code 0 (matches default)
        result = validate_command_result(exit_code=0, stdout="test", step=step)
        assert result is True

        # Should fail with non-zero exit code
        result = validate_command_result(exit_code=1, stdout="test", step=step)
        assert result is False

    def test_pattern_fails_when_not_found(self) -> None:
        """Test that validation fails when pattern is not found in output."""
        from amelia.agents.developer import validate_command_result
        from amelia.core.state import PlanStep

        step = PlanStep(
            id="step6",
            description="Check for pattern",
            action_type="command",
            command="pytest",
            expect_exit_code=0,
            expected_output_pattern=r"SUCCESS",
        )

        result = validate_command_result(exit_code=0, stdout="FAILURE occurred", step=step)
        assert result is False

    def test_pattern_uses_search_not_match(self) -> None:
        """Test that pattern uses re.search (finds pattern anywhere) not re.match (start only)."""
        from amelia.agents.developer import validate_command_result
        from amelia.core.state import PlanStep

        step = PlanStep(
            id="step7",
            description="Find pattern in middle of output",
            action_type="command",
            command="pytest",
            expect_exit_code=0,
            expected_output_pattern=r"PASSED",
        )

        # Pattern is in the middle, not at start
        stdout = "Running tests...\nTest suite PASSED\nComplete"

        result = validate_command_result(exit_code=0, stdout=stdout, step=step)
        assert result is True

    def test_exit_code_checked_before_pattern(self) -> None:
        """Test that exit code is checked first, even if pattern would match."""
        from amelia.agents.developer import validate_command_result
        from amelia.core.state import PlanStep

        step = PlanStep(
            id="step8",
            description="Exit code takes precedence",
            action_type="command",
            command="pytest",
            expect_exit_code=0,
            expected_output_pattern=r"PASSED",
        )

        # Pattern matches but exit code is wrong
        result = validate_command_result(exit_code=1, stdout="All tests PASSED", step=step)
        assert result is False


class TestPreValidateStep:
    """Test Developer._pre_validate_step method."""

    async def test_low_risk_step_skips_llm_validation(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that low-risk steps skip LLM validation and only run filesystem checks."""
        from unittest.mock import patch

        from amelia.core.state import PlanStep

        mock_driver, state = developer_test_context(task_desc="Test task")
        developer = Developer(driver=mock_driver, execution_mode="structured")

        # Create a low-risk step
        step = PlanStep(
            id="step1",
            description="Run simple test",
            action_type="command",
            command="pytest",
            risk_level="low",
        )

        # Mock _filesystem_checks to return success
        with patch.object(developer, "_filesystem_checks", return_value=ValidationResult(ok=True)) as mock_fs:
            result = await developer._pre_validate_step(step, state)

        # Should call filesystem checks
        mock_fs.assert_called_once_with(step)

        # Should return filesystem result
        assert result.ok is True

    async def test_medium_risk_step_skips_llm_validation(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that medium-risk steps skip LLM validation (LLM is at batch level)."""
        from unittest.mock import patch

        from amelia.core.state import PlanStep

        mock_driver, state = developer_test_context(task_desc="Test task")
        developer = Developer(driver=mock_driver, execution_mode="structured")

        # Create a medium-risk step
        step = PlanStep(
            id="step2",
            description="Modify configuration",
            action_type="code",
            file_path="config.py",
            code_change="# Update config",
            risk_level="medium",
        )

        # Mock _filesystem_checks to return success
        with patch.object(developer, "_filesystem_checks", return_value=ValidationResult(ok=True)) as mock_fs:
            result = await developer._pre_validate_step(step, state)

        # Should call filesystem checks
        mock_fs.assert_called_once_with(step)

        # Should return filesystem result without LLM validation
        assert result.ok is True

    async def test_high_risk_step_runs_filesystem_checks(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that high-risk steps run filesystem checks (LLM is TODO)."""
        from unittest.mock import patch

        from amelia.core.state import PlanStep

        mock_driver, state = developer_test_context(task_desc="Test task")
        developer = Developer(driver=mock_driver, execution_mode="structured")

        # Create a high-risk step
        step = PlanStep(
            id="step3",
            description="Delete production database",
            action_type="command",
            command="rm -rf /var/lib/data",
            risk_level="high",
        )

        # Mock _filesystem_checks to return success
        with patch.object(developer, "_filesystem_checks", return_value=ValidationResult(ok=True)) as mock_fs:
            result = await developer._pre_validate_step(step, state)

        # Should call filesystem checks
        mock_fs.assert_called_once_with(step)

        # For now, should return filesystem result (LLM is TODO)
        assert result.ok is True

    async def test_returns_early_on_filesystem_failure(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that validation returns early if filesystem checks fail."""
        from unittest.mock import patch

        from amelia.core.state import PlanStep

        mock_driver, state = developer_test_context(task_desc="Test task")
        developer = Developer(driver=mock_driver, execution_mode="structured")

        # Create a high-risk step
        step = PlanStep(
            id="step4",
            description="Modify missing file",
            action_type="code",
            file_path="nonexistent.py",
            code_change="# Code",
            risk_level="high",
        )

        # Mock _filesystem_checks to return failure
        fs_failure = ValidationResult(
            ok=False,
            issue="File not found: nonexistent.py",
            suggestions=("Create the file first",),
        )
        with patch.object(developer, "_filesystem_checks", return_value=fs_failure) as mock_fs:
            result = await developer._pre_validate_step(step, state)

        # Should call filesystem checks
        mock_fs.assert_called_once_with(step)

        # Should return filesystem failure immediately (not proceed to LLM)
        assert result.ok is False
        assert result.issue == "File not found: nonexistent.py"
        assert "Create the file first" in result.suggestions


class TestGetCascadeSkips:
    """Test get_cascade_skips function."""

    def test_simple_dependency_skip(self) -> None:
        """Test one step depends on failed step."""
        from amelia.agents.developer import get_cascade_skips
        from amelia.core.state import ExecutionBatch, ExecutionPlan, PlanStep

        # Create steps: step1 (failed), step2 (depends on step1)
        step1 = PlanStep(
            id="step1",
            description="Install dependencies",
            action_type="command",
            command="npm install",
        )
        step2 = PlanStep(
            id="step2",
            description="Run tests",
            action_type="command",
            command="npm test",
            depends_on=("step1",),
        )

        batch = ExecutionBatch(
            batch_number=1,
            steps=(step1, step2),
            risk_summary="low",
        )

        plan = ExecutionPlan(
            goal="Run tests",
            batches=(batch,),
            total_estimated_minutes=5,
        )

        # step1 failed
        skip_reasons = {"step1": "Command failed with exit code 1"}

        result = get_cascade_skips("step1", plan, skip_reasons)

        # step2 should be skipped
        assert "step2" in result
        assert "depends on" in result["step2"].lower()
        assert "step1" in result["step2"]
        # Original step should not be in result
        assert "step1" not in result

    def test_transitive_dependency_skip(self) -> None:
        """Test A->B->C chain, C fails."""
        from amelia.agents.developer import get_cascade_skips
        from amelia.core.state import ExecutionBatch, ExecutionPlan, PlanStep

        # Create steps: C (failed), B (depends on C), A (depends on B)
        step_c = PlanStep(
            id="step_c",
            description="Install base packages",
            action_type="command",
            command="apt install base",
        )
        step_b = PlanStep(
            id="step_b",
            description="Install dev packages",
            action_type="command",
            command="apt install dev",
            depends_on=("step_c",),
        )
        step_a = PlanStep(
            id="step_a",
            description="Build project",
            action_type="command",
            command="make build",
            depends_on=("step_b",),
        )

        batch = ExecutionBatch(
            batch_number=1,
            steps=(step_c, step_b, step_a),
            risk_summary="medium",
        )

        plan = ExecutionPlan(
            goal="Build project",
            batches=(batch,),
            total_estimated_minutes=10,
        )

        # step_c failed
        skip_reasons = {"step_c": "Command failed"}

        result = get_cascade_skips("step_c", plan, skip_reasons)

        # Both step_b and step_a should be skipped
        assert "step_b" in result
        assert "step_a" in result
        assert "depends on" in result["step_b"].lower()
        assert "depends on" in result["step_a"].lower()
        # Original step should not be in result
        assert "step_c" not in result

    def test_no_cascade_when_no_dependencies(self) -> None:
        """Test step with no depends_on is not skipped."""
        from amelia.agents.developer import get_cascade_skips
        from amelia.core.state import ExecutionBatch, ExecutionPlan, PlanStep

        # Create independent steps
        step1 = PlanStep(
            id="step1",
            description="Install dependencies",
            action_type="command",
            command="npm install",
        )
        step2 = PlanStep(
            id="step2",
            description="Run linter",
            action_type="command",
            command="npm run lint",
        )

        batch = ExecutionBatch(
            batch_number=1,
            steps=(step1, step2),
            risk_summary="low",
        )

        plan = ExecutionPlan(
            goal="Run checks",
            batches=(batch,),
            total_estimated_minutes=5,
        )

        # step1 failed
        skip_reasons = {"step1": "Command failed"}

        result = get_cascade_skips("step1", plan, skip_reasons)

        # step2 should NOT be skipped (no dependencies)
        assert "step2" not in result
        # Only original step1 was in skip_reasons, nothing cascaded
        assert len(result) == 0

    def test_multiple_batches_cascade(self) -> None:
        """Test cascade works across multiple batches."""
        from amelia.agents.developer import get_cascade_skips
        from amelia.core.state import ExecutionBatch, ExecutionPlan, PlanStep

        # Batch 1: step1 (failed), step2 (depends on step1)
        step1 = PlanStep(
            id="step1",
            description="Setup environment",
            action_type="command",
            command="setup.sh",
        )
        step2 = PlanStep(
            id="step2",
            description="Install deps",
            action_type="command",
            command="npm install",
            depends_on=("step1",),
        )

        batch1 = ExecutionBatch(
            batch_number=1,
            steps=(step1, step2),
            risk_summary="low",
        )

        # Batch 2: step3 (depends on step2)
        step3 = PlanStep(
            id="step3",
            description="Build project",
            action_type="command",
            command="npm build",
            depends_on=("step2",),
        )

        batch2 = ExecutionBatch(
            batch_number=2,
            steps=(step3,),
            risk_summary="low",
        )

        plan = ExecutionPlan(
            goal="Build project",
            batches=(batch1, batch2),
            total_estimated_minutes=10,
        )

        # step1 failed
        skip_reasons = {"step1": "Command failed"}

        result = get_cascade_skips("step1", plan, skip_reasons)

        # Both step2 and step3 should be skipped (transitive)
        assert "step2" in result
        assert "step3" in result

    def test_empty_skip_reasons(self) -> None:
        """Test function handles empty skip_reasons dict."""
        from amelia.agents.developer import get_cascade_skips
        from amelia.core.state import ExecutionBatch, ExecutionPlan, PlanStep

        step1 = PlanStep(
            id="step1",
            description="Run test",
            action_type="command",
            command="pytest",
        )

        batch = ExecutionBatch(
            batch_number=1,
            steps=(step1,),
            risk_summary="low",
        )

        plan = ExecutionPlan(
            goal="Run tests",
            batches=(batch,),
            total_estimated_minutes=5,
        )

        # No steps failed
        skip_reasons: dict[str, str] = {}

        result = get_cascade_skips("step1", plan, skip_reasons)

        # Nothing should be skipped
        assert len(result) == 0

    def test_multiple_dependencies_all_skipped(self) -> None:
        """Test step with multiple dependencies all being skipped."""
        from amelia.agents.developer import get_cascade_skips
        from amelia.core.state import ExecutionBatch, ExecutionPlan, PlanStep

        # step1 and step2 are independent, step3 depends on both
        step1 = PlanStep(
            id="step1",
            description="Install tool A",
            action_type="command",
            command="install A",
        )
        step2 = PlanStep(
            id="step2",
            description="Install tool B",
            action_type="command",
            command="install B",
        )
        step3 = PlanStep(
            id="step3",
            description="Build with both tools",
            action_type="command",
            command="build",
            depends_on=("step1", "step2"),
        )

        batch = ExecutionBatch(
            batch_number=1,
            steps=(step1, step2, step3),
            risk_summary="medium",
        )

        plan = ExecutionPlan(
            goal="Build project",
            batches=(batch,),
            total_estimated_minutes=10,
        )

        # step1 failed
        skip_reasons = {"step1": "Command failed"}

        result = get_cascade_skips("step1", plan, skip_reasons)

        # step3 should be skipped (depends on failed step1)
        assert "step3" in result
        # step2 should NOT be skipped (independent)
        assert "step2" not in result


class TestExecuteStepWithFallbacks:
    """Test Developer._execute_step_with_fallbacks method."""

    async def test_primary_command_succeeds(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that primary command works first time."""
        from unittest.mock import AsyncMock, patch

        from amelia.core.state import PlanStep

        mock_driver, state = developer_test_context()
        developer = Developer(driver=mock_driver, execution_mode="structured")

        step = PlanStep(
            id="step1",
            description="Run tests",
            action_type="command",
            command="pytest tests/",
            expect_exit_code=0,
        )

        # Mock run_shell_command to return success
        mock_shell = AsyncMock(return_value="All tests passed")
        with patch("amelia.agents.developer.run_shell_command", mock_shell):
            result = await developer._execute_step_with_fallbacks(step, state)

        # Verify command was called
        mock_shell.assert_called_once()

        # Verify result
        assert result.step_id == "step1"
        assert result.status == "completed"
        assert result.output == "All tests passed"
        assert result.error is None
        assert result.executed_command == "pytest tests/"
        assert result.duration_seconds > 0

    async def test_fallback_used_when_primary_fails(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that fallback command is used when primary fails."""
        from unittest.mock import patch

        from amelia.core.state import PlanStep

        mock_driver, state = developer_test_context()
        developer = Developer(driver=mock_driver, execution_mode="structured")

        step = PlanStep(
            id="step2",
            description="Install dependencies",
            action_type="command",
            command="npm install",
            fallback_commands=("yarn install", "pnpm install"),
            expect_exit_code=0,
        )

        # Mock run_shell_command to fail first, succeed on second
        async def mock_command(cmd: str, **kwargs: Any) -> str:
            if cmd == "npm install":
                # Simulate command failure
                raise RuntimeError("npm install failed")
            return "Dependencies installed"

        with patch("amelia.agents.developer.run_shell_command", side_effect=mock_command):
            result = await developer._execute_step_with_fallbacks(step, state)

        # Verify fallback was used
        assert result.step_id == "step2"
        assert result.status == "completed"
        assert result.executed_command == "yarn install"
        assert result.error is None

    async def test_all_fallbacks_fail_returns_failed_result(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that all commands fail returns failed result."""
        from unittest.mock import patch

        from amelia.core.state import PlanStep

        mock_driver, state = developer_test_context()
        developer = Developer(driver=mock_driver, execution_mode="structured")

        step = PlanStep(
            id="step3",
            description="Install dependencies",
            action_type="command",
            command="npm install",
            fallback_commands=("yarn install", "pnpm install"),
            expect_exit_code=0,
        )

        # Mock run_shell_command to always fail
        async def mock_command_fail(cmd: str, **kwargs: Any) -> str:
            raise RuntimeError(f"{cmd} failed")

        with patch("amelia.agents.developer.run_shell_command", side_effect=mock_command_fail):
            result = await developer._execute_step_with_fallbacks(step, state)

        # Verify all failed
        assert result.step_id == "step3"
        assert result.status == "failed"
        assert result.error is not None
        # Error message will be from the last command that failed
        assert result.error is not None

    async def test_code_action_with_validation_command(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
        tmp_path: Any,
    ) -> None:
        """Test that code action runs validation command after write."""
        from unittest.mock import patch

        from amelia.core.state import PlanStep

        mock_driver, state = developer_test_context()
        developer = Developer(driver=mock_driver, execution_mode="structured")

        test_file = tmp_path / "test.py"
        step = PlanStep(
            id="step4",
            description="Write test file",
            action_type="code",
            file_path=str(test_file),
            code_change="def test_func():\n    pass",
            validation_command="python -m py_compile test.py",
            expect_exit_code=0,
        )

        # Mock write_file and run_shell_command
        from unittest.mock import AsyncMock

        mock_write = AsyncMock(return_value="File written")
        mock_shell = AsyncMock(return_value="Syntax OK")
        with patch("amelia.agents.developer.write_file", mock_write), \
             patch("amelia.agents.developer.run_shell_command", mock_shell):
            result = await developer._execute_step_with_fallbacks(step, state)

        # Verify file was written
        mock_write.assert_called_once_with(str(test_file), "def test_func():\n    pass")

        # Verify validation command was run
        mock_shell.assert_called_once()

        # Verify result
        assert result.step_id == "step4"
        assert result.status == "completed"
        assert result.error is None
