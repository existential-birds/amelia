# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for Developer._execute_batch method."""
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, patch

from amelia.agents.developer import Developer, ValidationResult
from amelia.core.state import (
    BatchResult,
    ExecutionBatch,
    ExecutionState,
    GitSnapshot,
    PlanStep,
    StepResult,
)


class TestExecuteBatch:
    """Test Developer._execute_batch method."""

    async def test_successful_batch_execution(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that all steps in a batch complete successfully."""
        mock_driver, state = developer_test_context()
        developer = Developer(driver=mock_driver, execution_mode="structured")

        # Create a batch with two simple steps
        step1 = PlanStep(
            id="step1",
            description="Run tests",
            action_type="command",
            command="pytest",
            risk_level="low",
        )
        step2 = PlanStep(
            id="step2",
            description="Run linter",
            action_type="command",
            command="ruff check",
            risk_level="low",
        )

        batch = ExecutionBatch(
            batch_number=1,
            steps=(step1, step2),
            risk_summary="low",
        )

        # Mock dependencies
        mock_snapshot = GitSnapshot(head_commit="abc123", dirty_files=())

        # We need to return different StepResults for different steps
        def mock_execute_step(step: PlanStep, state: ExecutionState) -> StepResult:
            return StepResult(
                step_id=step.id,
                status="completed",
                output="Success",
                duration_seconds=1.0,
            )

        with (
            patch(
                "amelia.agents.developer.take_git_snapshot",
                AsyncMock(return_value=mock_snapshot),
            ),
            patch.object(
                developer,
                "_pre_validate_step",
                AsyncMock(return_value=ValidationResult(ok=True)),
            ),
            patch.object(
                developer,
                "_execute_step_with_fallbacks",
                AsyncMock(side_effect=mock_execute_step),
            ),
        ):
            result = await developer._execute_batch(batch, state)

        assert result.batch_number == 1
        assert result.status == "complete"
        assert len(result.completed_steps) == 2
        assert result.blocker is None
        assert result.completed_steps[0].step_id == "step1"
        assert result.completed_steps[1].step_id == "step2"

    async def test_blocked_on_pre_validation_failure(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that batch is blocked when pre-validation fails."""
        mock_driver, state = developer_test_context()
        developer = Developer(driver=mock_driver, execution_mode="structured")

        step1 = PlanStep(
            id="step1",
            description="Modify missing file",
            action_type="code",
            file_path="/nonexistent/file.py",
            code_change="# code",
            risk_level="low",
        )

        batch = ExecutionBatch(
            batch_number=1,
            steps=(step1,),
            risk_summary="low",
        )

        mock_snapshot = GitSnapshot(head_commit="abc123", dirty_files=())
        validation_failure = ValidationResult(
            ok=False,
            issue="File not found: /nonexistent/file.py",
            suggestions=("Create the file first",),
        )

        with (
            patch(
                "amelia.agents.developer.take_git_snapshot",
                AsyncMock(return_value=mock_snapshot),
            ),
            patch.object(
                developer,
                "_pre_validate_step",
                AsyncMock(return_value=validation_failure),
            ),
        ):
            result = await developer._execute_batch(batch, state)

        assert result.status == "blocked"
        assert result.blocker is not None
        assert result.blocker.step_id == "step1"
        assert result.blocker.blocker_type == "unexpected_state"
        assert "File not found" in result.blocker.error_message
        assert "Create the file first" in result.blocker.suggested_resolutions

    async def test_blocked_on_command_failure(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that batch is blocked when command execution fails."""
        mock_driver, state = developer_test_context()
        developer = Developer(driver=mock_driver, execution_mode="structured")

        step1 = PlanStep(
            id="step1",
            description="Run failing command",
            action_type="command",
            command="false",
            risk_level="low",
        )

        batch = ExecutionBatch(
            batch_number=1,
            steps=(step1,),
            risk_summary="low",
        )

        mock_snapshot = GitSnapshot(head_commit="abc123", dirty_files=())
        failed_step_result = StepResult(
            step_id="step1",
            status="failed",
            error="Command exited with code 1",
            executed_command="false",
        )

        with (
            patch(
                "amelia.agents.developer.take_git_snapshot",
                AsyncMock(return_value=mock_snapshot),
            ),
            patch.object(
                developer,
                "_pre_validate_step",
                AsyncMock(return_value=ValidationResult(ok=True)),
            ),
            patch.object(
                developer,
                "_execute_step_with_fallbacks",
                AsyncMock(return_value=failed_step_result),
            ),
        ):
            result = await developer._execute_batch(batch, state)

        assert result.status == "blocked"
        assert result.blocker is not None
        assert result.blocker.step_id == "step1"
        assert result.blocker.blocker_type == "command_failed"
        assert "Command exited with code 1" in result.blocker.error_message

    async def test_cascade_skips_handled(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that steps with skipped dependencies are auto-skipped."""
        mock_driver, state = developer_test_context()
        # Add a skipped step to state
        state = state.model_copy(update={"skipped_step_ids": {"step0"}})

        developer = Developer(driver=mock_driver, execution_mode="structured")

        step1 = PlanStep(
            id="step1",
            description="Step depending on skipped step",
            action_type="command",
            command="echo depends",
            depends_on=("step0",),
            risk_level="low",
        )
        step2 = PlanStep(
            id="step2",
            description="Independent step",
            action_type="command",
            command="echo independent",
            risk_level="low",
        )

        batch = ExecutionBatch(
            batch_number=1,
            steps=(step1, step2),
            risk_summary="low",
        )

        mock_snapshot = GitSnapshot(head_commit="abc123", dirty_files=())
        completed_result = StepResult(
            step_id="step2",
            status="completed",
            output="independent",
        )

        with (
            patch(
                "amelia.agents.developer.take_git_snapshot",
                AsyncMock(return_value=mock_snapshot),
            ),
            patch.object(
                developer,
                "_pre_validate_step",
                AsyncMock(return_value=ValidationResult(ok=True)),
            ),
            patch.object(
                developer,
                "_execute_step_with_fallbacks",
                AsyncMock(return_value=completed_result),
            ),
        ):
            result = await developer._execute_batch(batch, state)

        assert result.status == "complete"
        assert len(result.completed_steps) == 2

        # First step should be skipped
        skipped_step = result.completed_steps[0]
        assert skipped_step.step_id == "step1"
        assert skipped_step.status == "skipped"
        assert "step0" in (skipped_step.error or "")

        # Second step should be completed
        completed_step = result.completed_steps[1]
        assert completed_step.step_id == "step2"
        assert completed_step.status == "completed"

    async def test_git_snapshot_taken_before_execution(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that git snapshot is captured before batch execution."""
        mock_driver, state = developer_test_context()
        developer = Developer(driver=mock_driver, execution_mode="structured")

        step1 = PlanStep(
            id="step1",
            description="Run test",
            action_type="command",
            command="pytest",
            risk_level="low",
        )

        batch = ExecutionBatch(
            batch_number=1,
            steps=(step1,),
            risk_summary="low",
        )

        mock_snapshot = GitSnapshot(head_commit="abc123", dirty_files=("file.txt",))
        mock_take_snapshot = AsyncMock(return_value=mock_snapshot)
        completed_result = StepResult(step_id="step1", status="completed", output="ok")

        with (
            patch("amelia.agents.developer.take_git_snapshot", mock_take_snapshot),
            patch.object(
                developer,
                "_pre_validate_step",
                AsyncMock(return_value=ValidationResult(ok=True)),
            ),
            patch.object(
                developer,
                "_execute_step_with_fallbacks",
                AsyncMock(return_value=completed_result),
            ),
        ):
            result = await developer._execute_batch(batch, state)

        # Verify take_git_snapshot was called
        mock_take_snapshot.assert_called_once()
        assert result.status == "complete"

    async def test_partial_results_on_failure(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that completed steps before failure are included in result."""
        mock_driver, state = developer_test_context()
        developer = Developer(driver=mock_driver, execution_mode="structured")

        step1 = PlanStep(
            id="step1", description="First", action_type="command", command="echo 1"
        )
        step2 = PlanStep(
            id="step2", description="Second", action_type="command", command="echo 2"
        )
        step3 = PlanStep(
            id="step3",
            description="Third fails",
            action_type="command",
            command="false",
        )

        batch = ExecutionBatch(
            batch_number=1, steps=(step1, step2, step3), risk_summary="low"
        )

        mock_snapshot = GitSnapshot(head_commit="abc123", dirty_files=())

        # step1 and step2 succeed, step3 fails
        def mock_execute_step(step: PlanStep, state: Any) -> StepResult:
            if step.id == "step3":
                return StepResult(
                    step_id=step.id, status="failed", error="Command failed"
                )
            return StepResult(step_id=step.id, status="completed", output="ok")

        with (
            patch(
                "amelia.agents.developer.take_git_snapshot",
                AsyncMock(return_value=mock_snapshot),
            ),
            patch.object(
                developer,
                "_pre_validate_step",
                AsyncMock(return_value=ValidationResult(ok=True)),
            ),
            patch.object(
                developer,
                "_execute_step_with_fallbacks",
                AsyncMock(side_effect=mock_execute_step),
            ),
        ):
            result = await developer._execute_batch(batch, state)

        assert result.status == "blocked"
        # Should have 2 completed steps before the failure
        assert len(result.completed_steps) == 2
        assert result.completed_steps[0].step_id == "step1"
        assert result.completed_steps[1].step_id == "step2"
        assert result.blocker is not None
        assert result.blocker.step_id == "step3"

    async def test_validation_failure_blocker_type(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test blocker type is validation_failed for code action failures."""
        mock_driver, state = developer_test_context()
        developer = Developer(driver=mock_driver, execution_mode="structured")

        step1 = PlanStep(
            id="step1",
            description="Write code",
            action_type="code",
            file_path="test.py",
            code_change="# code",
            risk_level="low",
        )

        batch = ExecutionBatch(
            batch_number=1,
            steps=(step1,),
            risk_summary="low",
        )

        mock_snapshot = GitSnapshot(head_commit="abc123", dirty_files=())
        # Pre-validation passes, but execution fails
        failed_result = StepResult(
            step_id="step1",
            status="failed",
            error="Failed to write file",
        )

        with (
            patch(
                "amelia.agents.developer.take_git_snapshot",
                AsyncMock(return_value=mock_snapshot),
            ),
            patch.object(
                developer,
                "_pre_validate_step",
                AsyncMock(return_value=ValidationResult(ok=True)),
            ),
            patch.object(
                developer,
                "_execute_step_with_fallbacks",
                AsyncMock(return_value=failed_result),
            ),
        ):
            result = await developer._execute_batch(batch, state)

        assert result.status == "blocked"
        assert result.blocker is not None
        # Code action failure should be validation_failed, not command_failed
        assert result.blocker.blocker_type == "validation_failed"


class TestRecoverFromBlocker:
    """Test Developer._recover_from_blocker method."""

    async def test_recovery_with_fix_instruction(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test recovery when human provides fix instruction."""
        from amelia.core.state import BlockerReport, ExecutionPlan

        mock_driver, state = developer_test_context()
        developer = Developer(driver=mock_driver, execution_mode="structured")

        # Setup: execution plan with one batch, blocked on step1
        step1 = PlanStep(
            id="step1",
            description="Run command",
            action_type="command",
            command="pytest",
            risk_level="low",
        )
        step2 = PlanStep(
            id="step2",
            description="Run linter",
            action_type="command",
            command="ruff check",
            risk_level="low",
        )

        batch = ExecutionBatch(
            batch_number=1,
            steps=(step1, step2),
            risk_summary="low",
        )

        plan = ExecutionPlan(
            goal="Test recovery",
            batches=(batch,),
            total_estimated_minutes=5,
        )

        # State shows we were blocked on step1, human gave fix instruction
        blocker = BlockerReport(
            step_id="step1",
            step_description="Run command",
            blocker_type="command_failed",
            error_message="pytest not found",
            attempted_actions=("pytest",),
            suggested_resolutions=("Install pytest",),
        )

        state = state.model_copy(
            update={
                "execution_plan": plan,
                "current_batch_index": 0,
                "current_blocker": blocker,
                "blocker_resolution": "Try: pip install pytest && pytest",
            }
        )

        mock_snapshot = GitSnapshot(head_commit="abc123", dirty_files=())
        completed_result = StepResult(
            step_id="step1",
            status="completed",
            output="Success",
        )

        with (
            patch(
                "amelia.agents.developer.take_git_snapshot",
                AsyncMock(return_value=mock_snapshot),
            ),
            patch.object(
                developer,
                "_pre_validate_step",
                AsyncMock(return_value=ValidationResult(ok=True)),
            ),
            patch.object(
                developer,
                "_execute_step_with_fallbacks",
                AsyncMock(return_value=completed_result),
            ),
        ):
            result = await developer._recover_from_blocker(state)

        # Should complete successfully (recovery retries from blocked step)
        assert result.status == "complete"
        assert len(result.completed_steps) == 2
        assert result.blocker is None

    async def test_recovery_continues_from_blocked_step(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test recovery starts from the blocked step, not the beginning."""
        from amelia.core.state import (
            BlockerReport,
            ExecutionPlan,
        )

        mock_driver, state = developer_test_context()
        developer = Developer(driver=mock_driver, execution_mode="structured")

        # Setup: batch with 3 steps, step1 completed, step2 blocked
        step1 = PlanStep(
            id="step1",
            description="First step",
            action_type="command",
            command="echo 1",
            risk_level="low",
        )
        step2 = PlanStep(
            id="step2",
            description="Second step (blocked)",
            action_type="command",
            command="failing_cmd",
            risk_level="low",
        )
        step3 = PlanStep(
            id="step3",
            description="Third step",
            action_type="command",
            command="echo 3",
            risk_level="low",
        )

        batch = ExecutionBatch(
            batch_number=1,
            steps=(step1, step2, step3),
            risk_summary="low",
        )

        plan = ExecutionPlan(
            goal="Test recovery from middle",
            batches=(batch,),
            total_estimated_minutes=5,
        )

        # State: blocked on step2, with step1 already completed in batch_results
        blocker = BlockerReport(
            step_id="step2",
            step_description="Second step (blocked)",
            blocker_type="command_failed",
            error_message="Command failed",
            attempted_actions=("failing_cmd",),
            suggested_resolutions=(),
        )

        # Previous partial result with step1 completed
        partial_result = BatchResult(
            batch_number=1,
            status="blocked",
            completed_steps=(
                StepResult(step_id="step1", status="completed", output="1"),
            ),
            blocker=blocker,
        )

        state = state.model_copy(
            update={
                "execution_plan": plan,
                "current_batch_index": 0,
                "current_blocker": blocker,
                "blocker_resolution": "Fixed the command",
                "batch_results": [partial_result],
            }
        )

        mock_snapshot = GitSnapshot(head_commit="abc123", dirty_files=())

        # Track which steps get executed
        executed_steps: list[str] = []

        def mock_execute_step(step: PlanStep, st: Any) -> StepResult:
            executed_steps.append(step.id)
            return StepResult(step_id=step.id, status="completed", output="ok")

        with (
            patch(
                "amelia.agents.developer.take_git_snapshot",
                AsyncMock(return_value=mock_snapshot),
            ),
            patch.object(
                developer,
                "_pre_validate_step",
                AsyncMock(return_value=ValidationResult(ok=True)),
            ),
            patch.object(
                developer,
                "_execute_step_with_fallbacks",
                AsyncMock(side_effect=mock_execute_step),
            ),
        ):
            result = await developer._recover_from_blocker(state)

        # Should only execute step2 and step3, not step1 (already completed)
        assert executed_steps == ["step2", "step3"]
        assert result.status == "complete"
        # Result should have all 3 steps: step1 from previous + step2, step3 from recovery
        assert len(result.completed_steps) == 3
        assert result.completed_steps[0].step_id == "step1"
        assert result.completed_steps[1].step_id == "step2"
        assert result.completed_steps[2].step_id == "step3"


class TestDeveloperRun:
    """Test Developer.run method for intelligent execution."""

    async def test_all_batches_complete_returns_all_done(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that completing all batches returns ALL_DONE status."""
        from amelia.core.state import ExecutionPlan
        from amelia.core.types import DeveloperStatus as DS

        mock_driver, state = developer_test_context()
        developer = Developer(driver=mock_driver, execution_mode="structured")

        # Setup: plan with 2 batches, both already complete
        step1 = PlanStep(
            id="step1",
            description="Step 1",
            action_type="command",
            command="echo 1",
        )
        step2 = PlanStep(
            id="step2",
            description="Step 2",
            action_type="command",
            command="echo 2",
        )

        batch1 = ExecutionBatch(
            batch_number=1, steps=(step1,), risk_summary="low"
        )
        batch2 = ExecutionBatch(
            batch_number=2, steps=(step2,), risk_summary="low"
        )

        plan = ExecutionPlan(
            goal="Test completion",
            batches=(batch1, batch2),
            total_estimated_minutes=5,
        )

        # State: already past all batches
        state = state.model_copy(
            update={
                "execution_plan": plan,
                "current_batch_index": 2,  # Both batches done
            }
        )

        result = await developer.run(state)

        assert result["developer_status"] == DS.ALL_DONE

    async def test_batch_complete_returns_batch_complete(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that completing a batch returns BATCH_COMPLETE status."""
        from amelia.core.state import ExecutionPlan
        from amelia.core.types import DeveloperStatus as DS

        mock_driver, state = developer_test_context()
        developer = Developer(driver=mock_driver, execution_mode="structured")

        step1 = PlanStep(
            id="step1",
            description="Step 1",
            action_type="command",
            command="echo 1",
        )

        batch1 = ExecutionBatch(
            batch_number=1, steps=(step1,), risk_summary="low"
        )

        plan = ExecutionPlan(
            goal="Test batch complete",
            batches=(batch1,),
            total_estimated_minutes=5,
        )

        state = state.model_copy(
            update={
                "execution_plan": plan,
                "current_batch_index": 0,
            }
        )

        mock_snapshot = GitSnapshot(head_commit="abc123", dirty_files=())
        completed_result = StepResult(
            step_id="step1", status="completed", output="ok"
        )

        with (
            patch(
                "amelia.agents.developer.take_git_snapshot",
                AsyncMock(return_value=mock_snapshot),
            ),
            patch.object(
                developer,
                "_pre_validate_step",
                AsyncMock(return_value=ValidationResult(ok=True)),
            ),
            patch.object(
                developer,
                "_execute_step_with_fallbacks",
                AsyncMock(return_value=completed_result),
            ),
        ):
            result = await developer.run(state)

        assert result["developer_status"] == DS.BATCH_COMPLETE
        assert result["current_batch_index"] == 1
        assert len(result["batch_results"]) == 1
        assert result["batch_results"][0].status == "complete"

    async def test_blocked_returns_blocked_with_blocker(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that blocked execution returns BLOCKED status with blocker."""
        from amelia.core.state import ExecutionPlan
        from amelia.core.types import DeveloperStatus as DS

        mock_driver, state = developer_test_context()
        developer = Developer(driver=mock_driver, execution_mode="structured")

        step1 = PlanStep(
            id="step1",
            description="Failing step",
            action_type="command",
            command="failing_cmd",
        )

        batch1 = ExecutionBatch(
            batch_number=1, steps=(step1,), risk_summary="low"
        )

        plan = ExecutionPlan(
            goal="Test blocked",
            batches=(batch1,),
            total_estimated_minutes=5,
        )

        state = state.model_copy(
            update={
                "execution_plan": plan,
                "current_batch_index": 0,
            }
        )

        mock_snapshot = GitSnapshot(head_commit="abc123", dirty_files=())
        failed_result = StepResult(
            step_id="step1", status="failed", error="Command failed"
        )

        with (
            patch(
                "amelia.agents.developer.take_git_snapshot",
                AsyncMock(return_value=mock_snapshot),
            ),
            patch.object(
                developer,
                "_pre_validate_step",
                AsyncMock(return_value=ValidationResult(ok=True)),
            ),
            patch.object(
                developer,
                "_execute_step_with_fallbacks",
                AsyncMock(return_value=failed_result),
            ),
        ):
            result = await developer.run(state)

        assert result["developer_status"] == DS.BLOCKED
        assert result["current_blocker"] is not None
        assert result["current_blocker"].step_id == "step1"
        assert len(result["batch_results"]) == 1
        assert result["batch_results"][0].status == "blocked"

    async def test_blocker_resolution_path(
        self,
        developer_test_context: Callable[..., tuple[AsyncMock, ExecutionState]],
    ) -> None:
        """Test that providing blocker_resolution triggers recovery."""
        from amelia.core.state import BlockerReport, ExecutionPlan
        from amelia.core.types import DeveloperStatus as DS

        mock_driver, state = developer_test_context()
        developer = Developer(driver=mock_driver, execution_mode="structured")

        step1 = PlanStep(
            id="step1",
            description="Step 1",
            action_type="command",
            command="echo 1",
        )

        batch1 = ExecutionBatch(
            batch_number=1, steps=(step1,), risk_summary="low"
        )

        plan = ExecutionPlan(
            goal="Test recovery path",
            batches=(batch1,),
            total_estimated_minutes=5,
        )

        blocker = BlockerReport(
            step_id="step1",
            step_description="Step 1",
            blocker_type="command_failed",
            error_message="Command failed",
            attempted_actions=(),
            suggested_resolutions=(),
        )

        # State shows blocker_resolution (human provided fix)
        state = state.model_copy(
            update={
                "execution_plan": plan,
                "current_batch_index": 0,
                "current_blocker": blocker,
                "blocker_resolution": "Fixed the issue",  # Not skip or abort
            }
        )

        mock_snapshot = GitSnapshot(head_commit="abc123", dirty_files=())
        completed_result = StepResult(
            step_id="step1", status="completed", output="ok"
        )

        with (
            patch(
                "amelia.agents.developer.take_git_snapshot",
                AsyncMock(return_value=mock_snapshot),
            ),
            patch.object(
                developer,
                "_pre_validate_step",
                AsyncMock(return_value=ValidationResult(ok=True)),
            ),
            patch.object(
                developer,
                "_execute_step_with_fallbacks",
                AsyncMock(return_value=completed_result),
            ),
        ):
            result = await developer.run(state)

        # Should complete via recovery path
        assert result["developer_status"] == DS.BATCH_COMPLETE
        assert result["blocker_resolution"] is None  # Cleared
