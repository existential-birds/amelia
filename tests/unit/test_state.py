# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for core state models."""

from datetime import UTC, datetime

from amelia.core.state import (
    BatchApproval,
    BatchResult,
    BlockerReport,
    ExecutionBatch,
    ExecutionPlan,
    ExecutionState,
    GitSnapshot,
    PlanStep,
    StepResult,
    TaskDAG,
    truncate_output,
)
from amelia.core.types import DeveloperStatus, Profile, TrustLevel


def test_execution_state_workflow_status_default():
    """ExecutionState workflow_status should default to 'running'."""
    profile = Profile(name="test", driver="cli:claude")
    state = ExecutionState(profile=profile)
    assert state.workflow_status == "running"


def test_execution_state_workflow_status_failed():
    """ExecutionState should accept workflow_status='failed'."""
    profile = Profile(name="test", driver="cli:claude")
    state = ExecutionState(profile=profile, workflow_status="failed")
    assert state.workflow_status == "failed"


class TestTaskDAGGetTask:
    """Tests for TaskDAG.get_task() method."""

    def test_get_task_returns_correct_task(self, mock_task_factory):
        """get_task should return the task with matching ID."""
        task1 = mock_task_factory(id="task-1", description="First task")
        task2 = mock_task_factory(id="task-2", description="Second task")
        dag = TaskDAG(tasks=[task1, task2], original_issue="Test issue")

        result = dag.get_task("task-2")

        assert result is not None
        assert result.id == "task-2"
        assert result.description == "Second task"

    def test_get_task_returns_none_for_missing_id(self, mock_task_factory):
        """get_task should return None when task ID doesn't exist."""
        task1 = mock_task_factory(id="task-1", description="First task")
        dag = TaskDAG(tasks=[task1], original_issue="Test issue")

        result = dag.get_task("nonexistent")

        assert result is None

    def test_get_task_on_empty_dag(self):
        """get_task should return None on empty TaskDAG."""
        dag = TaskDAG(tasks=[], original_issue="Empty")

        result = dag.get_task("any-id")

        assert result is None


def test_execution_state_accepts_design_field():
    """ExecutionState should accept optional design field."""
    from amelia.core.types import Design

    profile = Profile(name="test", driver="cli:claude")
    design = Design(
        title="Test Design",
        goal="Test goal",
        architecture="Test architecture",
        tech_stack=["Python"],
        components=["Component A"],
        raw_content="# Test Design\n\nRaw content here",
    )
    state = ExecutionState(profile=profile, design=design)

    assert state.design is not None
    assert state.design.title == "Test Design"


def test_execution_state_design_defaults_to_none():
    """ExecutionState design should default to None."""
    profile = Profile(name="test", driver="cli:claude")
    state = ExecutionState(profile=profile)

    assert state.design is None


def test_mock_execution_state_factory_accepts_design(
    mock_execution_state_factory, mock_design_factory
):
    """mock_execution_state_factory should accept design parameter."""
    design = mock_design_factory(title="Factory Design")
    state = mock_execution_state_factory(design=design)

    assert state.design is not None
    assert state.design.title == "Factory Design"


class TestPlanStep:
    """Tests for PlanStep model."""

    def test_minimal_creation(self):
        """PlanStep can be created with minimal fields."""
        step = PlanStep(
            id="step-1",
            description="Test step",
            action_type="command",
        )
        assert step.id == "step-1"
        assert step.description == "Test step"
        assert step.action_type == "command"
        # Check defaults
        assert step.risk_level == "medium"
        assert step.estimated_minutes == 2
        assert step.depends_on == ()
        assert step.fallback_commands == ()

    def test_full_creation(self):
        """PlanStep can be created with all fields."""
        step = PlanStep(
            id="step-2",
            description="Full step",
            action_type="code",
            file_path="src/main.py",
            code_change="def hello(): pass",
            command=None,
            cwd="src",
            fallback_commands=("npm test", "yarn test"),
            expect_exit_code=0,
            expected_output_pattern=r"passed",
            validation_command="pytest",
            success_criteria="all tests pass",
            risk_level="high",
            estimated_minutes=5,
            requires_human_judgment=True,
            depends_on=("step-1",),
            is_test_step=True,
            validates_step="step-0",
        )
        assert step.file_path == "src/main.py"
        assert step.code_change == "def hello(): pass"
        assert step.cwd == "src"
        assert step.fallback_commands == ("npm test", "yarn test")
        assert step.expect_exit_code == 0
        assert step.expected_output_pattern == r"passed"
        assert step.risk_level == "high"
        assert step.requires_human_judgment is True
        assert step.depends_on == ("step-1",)
        assert step.is_test_step is True
        assert step.validates_step == "step-0"

    def test_action_type_values(self):
        """PlanStep action_type accepts valid values."""
        for action_type in ["code", "command", "validation", "manual"]:
            step = PlanStep(
                id=f"step-{action_type}",
                description=f"Test {action_type}",
                action_type=action_type,
            )
            assert step.action_type == action_type

    def test_risk_level_values(self):
        """PlanStep risk_level accepts valid values."""
        for risk in ["low", "medium", "high"]:
            step = PlanStep(
                id=f"step-{risk}",
                description=f"Test {risk}",
                action_type="command",
                risk_level=risk,
            )
            assert step.risk_level == risk


class TestExecutionBatch:
    """Tests for ExecutionBatch model."""

    def test_batch_creation_with_steps(self):
        """ExecutionBatch can be created with steps."""
        step1 = PlanStep(id="s1", description="Step 1", action_type="command")
        step2 = PlanStep(id="s2", description="Step 2", action_type="code")
        batch = ExecutionBatch(
            batch_number=1,
            steps=(step1, step2),
            risk_summary="medium",
            description="Test batch",
        )
        assert batch.batch_number == 1
        assert len(batch.steps) == 2
        assert batch.risk_summary == "medium"
        assert batch.description == "Test batch"

    def test_batch_default_description(self):
        """ExecutionBatch description defaults to empty string."""
        step = PlanStep(id="s1", description="Step 1", action_type="command")
        batch = ExecutionBatch(batch_number=1, steps=(step,), risk_summary="low")
        assert batch.description == ""

    def test_batch_risk_summary_values(self):
        """ExecutionBatch risk_summary accepts valid values."""
        step = PlanStep(id="s1", description="Step 1", action_type="command")
        for risk in ["low", "medium", "high"]:
            batch = ExecutionBatch(
                batch_number=1,
                steps=(step,),
                risk_summary=risk,
            )
            assert batch.risk_summary == risk


class TestExecutionPlan:
    """Tests for ExecutionPlan model."""

    def test_plan_creation_with_batches(self):
        """ExecutionPlan can be created with batches."""
        step1 = PlanStep(id="s1", description="Step 1", action_type="command")
        step2 = PlanStep(id="s2", description="Step 2", action_type="code")
        batch1 = ExecutionBatch(batch_number=1, steps=(step1,), risk_summary="low")
        batch2 = ExecutionBatch(batch_number=2, steps=(step2,), risk_summary="medium")
        plan = ExecutionPlan(
            goal="Test goal",
            batches=(batch1, batch2),
            total_estimated_minutes=10,
            tdd_approach=True,
        )
        assert plan.goal == "Test goal"
        assert len(plan.batches) == 2
        assert plan.total_estimated_minutes == 10
        assert plan.tdd_approach is True

    def test_plan_default_tdd_approach(self):
        """ExecutionPlan tdd_approach defaults to True."""
        step = PlanStep(id="s1", description="Step 1", action_type="command")
        batch = ExecutionBatch(batch_number=1, steps=(step,), risk_summary="low")
        plan = ExecutionPlan(
            goal="Test",
            batches=(batch,),
            total_estimated_minutes=5,
        )
        assert plan.tdd_approach is True

    def test_empty_plan(self):
        """ExecutionPlan can be created with no batches."""
        plan = ExecutionPlan(
            goal="Empty plan",
            batches=(),
            total_estimated_minutes=0,
        )
        assert len(plan.batches) == 0
        assert plan.goal == "Empty plan"

class TestBlockerReport:
    """Tests for BlockerReport model."""

    def test_all_blocker_types(self):
        """BlockerReport accepts all valid blocker types."""
        blocker_types = [
            "command_failed",
            "validation_failed",
            "needs_judgment",
            "unexpected_state",
            "dependency_skipped",
            "user_cancelled",
        ]
        for blocker_type in blocker_types:
            report = BlockerReport(
                step_id="step-1",
                step_description="Test step",
                blocker_type=blocker_type,
                error_message="Test error",
                attempted_actions=(),
                suggested_resolutions=(),
            )
            assert report.blocker_type == blocker_type

    def test_creation_with_attempted_actions(self):
        """BlockerReport can include attempted actions."""
        report = BlockerReport(
            step_id="step-1",
            step_description="Run tests",
            blocker_type="command_failed",
            error_message="npm test failed",
            attempted_actions=("npm test", "yarn test", "pnpm test"),
            suggested_resolutions=("Install npm", "Check package.json"),
        )
        assert report.step_id == "step-1"
        assert report.step_description == "Run tests"
        assert len(report.attempted_actions) == 3
        assert len(report.suggested_resolutions) == 2

class TestTruncateOutput:
    """Tests for truncate_output helper function."""

    def test_none_input(self):
        """truncate_output returns None for None input."""
        assert truncate_output(None) is None

    def test_short_output_unchanged(self):
        """truncate_output returns short output unchanged."""
        output = "Short output\nLine 2\nLine 3"
        assert truncate_output(output) == output

    def test_truncate_by_lines(self):
        """truncate_output truncates output exceeding line limit."""
        # Create output with 150 lines
        lines = [f"Line {i}" for i in range(150)]
        output = "\n".join(lines)
        result = truncate_output(output)
        # Should have first 50 + truncation message + last 50
        assert "truncated" in result
        assert "Line 0" in result  # First line
        assert "Line 149" in result  # Last line

    def test_truncate_by_chars(self):
        """truncate_output truncates output exceeding char limit."""
        # Create output with 5000 chars
        output = "x" * 5000
        result = truncate_output(output)
        assert len(result) < 5000
        assert "truncated" in result


class TestStepResult:
    """Tests for StepResult model."""

    def test_all_status_values(self):
        """StepResult accepts all valid status values."""
        for status in ["completed", "skipped", "failed", "cancelled"]:
            result = StepResult(step_id="s1", status=status)
            assert result.status == status

    def test_step_result_with_output(self):
        """StepResult can include output."""
        result = StepResult(
            step_id="s1",
            status="completed",
            output="Test output",
            executed_command="echo test",
            duration_seconds=1.5,
        )
        assert result.output == "Test output"
        assert result.executed_command == "echo test"
        assert result.duration_seconds == 1.5

    def test_step_result_with_error(self):
        """StepResult can include error."""
        result = StepResult(
            step_id="s1",
            status="failed",
            error="Command not found",
        )
        assert result.error == "Command not found"

    def test_step_result_cancelled_by_user(self):
        """StepResult tracks user cancellation."""
        result = StepResult(
            step_id="s1",
            status="cancelled",
            cancelled_by_user=True,
        )
        assert result.cancelled_by_user is True

class TestBatchResult:
    """Tests for BatchResult model."""

    def test_batch_result_complete(self):
        """BatchResult can represent complete batch."""
        step_result = StepResult(step_id="s1", status="completed")
        result = BatchResult(
            batch_number=1,
            status="complete",
            completed_steps=(step_result,),
            blocker=None,
        )
        assert result.status == "complete"
        assert len(result.completed_steps) == 1
        assert result.blocker is None

    def test_batch_result_with_blocker(self):
        """BatchResult can include blocker."""
        step_result = StepResult(step_id="s1", status="completed")
        blocker = BlockerReport(
            step_id="s2",
            step_description="Failed step",
            blocker_type="command_failed",
            error_message="Error",
            attempted_actions=(),
            suggested_resolutions=(),
        )
        result = BatchResult(
            batch_number=1,
            status="blocked",
            completed_steps=(step_result,),
            blocker=blocker,
        )
        assert result.status == "blocked"
        assert result.blocker is not None
        assert result.blocker.step_id == "s2"

    def test_batch_result_status_values(self):
        """BatchResult accepts all valid status values."""
        for status in ["complete", "blocked", "partial"]:
            result = BatchResult(
                batch_number=1,
                status=status,
                completed_steps=(),
            )
            assert result.status == status


class TestGitSnapshot:
    """Tests for GitSnapshot model."""

    def test_git_snapshot_creation(self):
        """GitSnapshot can be created."""
        snapshot = GitSnapshot(
            head_commit="abc123def456",
            dirty_files=("file1.py", "file2.py"),
            stash_ref=None,
        )
        assert snapshot.head_commit == "abc123def456"
        assert len(snapshot.dirty_files) == 2
        assert snapshot.stash_ref is None

    def test_git_snapshot_with_stash(self):
        """GitSnapshot can include stash ref."""
        snapshot = GitSnapshot(
            head_commit="abc123",
            dirty_files=(),
            stash_ref="stash@{0}",
        )
        assert snapshot.stash_ref == "stash@{0}"

class TestBatchApproval:
    """Tests for BatchApproval model."""

    def test_batch_approval_approved(self):
        """BatchApproval can represent approval."""
        approval = BatchApproval(
            batch_number=1,
            approved=True,
            feedback=None,
            approved_at=datetime.now(UTC),
        )
        assert approval.approved is True
        assert approval.feedback is None

    def test_batch_approval_with_feedback(self):
        """BatchApproval can include feedback."""
        approval = BatchApproval(
            batch_number=1,
            approved=False,
            feedback="Please fix the imports",
            approved_at=datetime.now(UTC),
        )
        assert approval.approved is False
        assert approval.feedback == "Please fix the imports"

class TestExecutionStateNewFields:
    """Tests for ExecutionState extensions for intelligent execution model."""

    def test_state_with_execution_plan(self):
        """ExecutionState accepts execution_plan field."""
        profile = Profile(name="test", driver="cli:claude")
        step = PlanStep(id="s1", description="Test", action_type="command")
        batch = ExecutionBatch(batch_number=1, steps=(step,), risk_summary="low")
        plan = ExecutionPlan(goal="Test", batches=(batch,), total_estimated_minutes=5)

        state = ExecutionState(profile=profile, execution_plan=plan)

        assert state.execution_plan is not None
        assert state.execution_plan.goal == "Test"

    def test_state_execution_plan_defaults_to_none(self):
        """ExecutionState execution_plan defaults to None."""
        profile = Profile(name="test", driver="cli:claude")
        state = ExecutionState(profile=profile)
        assert state.execution_plan is None

    def test_state_current_batch_index_default(self):
        """ExecutionState current_batch_index defaults to 0."""
        profile = Profile(name="test", driver="cli:claude")
        state = ExecutionState(profile=profile)
        assert state.current_batch_index == 0

    def test_state_batch_results_default(self):
        """ExecutionState batch_results defaults to empty list."""
        profile = Profile(name="test", driver="cli:claude")
        state = ExecutionState(profile=profile)
        assert state.batch_results == []

    def test_state_developer_status_default(self):
        """ExecutionState developer_status defaults to EXECUTING."""
        profile = Profile(name="test", driver="cli:claude")
        state = ExecutionState(profile=profile)
        assert state.developer_status == DeveloperStatus.EXECUTING

    def test_state_developer_status_custom(self):
        """ExecutionState accepts custom developer_status."""
        profile = Profile(name="test", driver="cli:claude")
        state = ExecutionState(
            profile=profile,
            developer_status=DeveloperStatus.BLOCKED,
        )
        assert state.developer_status == DeveloperStatus.BLOCKED

    def test_state_current_blocker(self):
        """ExecutionState accepts current_blocker."""
        profile = Profile(name="test", driver="cli:claude")
        blocker = BlockerReport(
            step_id="s1",
            step_description="Test",
            blocker_type="command_failed",
            error_message="Error",
            attempted_actions=(),
            suggested_resolutions=(),
        )
        state = ExecutionState(profile=profile, current_blocker=blocker)
        assert state.current_blocker is not None
        assert state.current_blocker.step_id == "s1"

    def test_state_blocker_resolution(self):
        """ExecutionState accepts blocker_resolution."""
        profile = Profile(name="test", driver="cli:claude")
        state = ExecutionState(profile=profile, blocker_resolution="skip")
        assert state.blocker_resolution == "skip"

    def test_state_batch_approvals_default(self):
        """ExecutionState batch_approvals defaults to empty list."""
        profile = Profile(name="test", driver="cli:claude")
        state = ExecutionState(profile=profile)
        assert state.batch_approvals == []

    def test_state_skipped_step_ids_default(self):
        """ExecutionState skipped_step_ids defaults to empty set."""
        profile = Profile(name="test", driver="cli:claude")
        state = ExecutionState(profile=profile)
        assert state.skipped_step_ids == set()

    def test_state_skipped_step_ids_custom(self):
        """ExecutionState accepts custom skipped_step_ids."""
        profile = Profile(name="test", driver="cli:claude")
        state = ExecutionState(profile=profile, skipped_step_ids={"s1", "s2"})
        assert state.skipped_step_ids == {"s1", "s2"}

    def test_state_git_snapshot_before_batch(self):
        """ExecutionState accepts git_snapshot_before_batch."""
        profile = Profile(name="test", driver="cli:claude")
        snapshot = GitSnapshot(head_commit="abc123", dirty_files=())
        state = ExecutionState(profile=profile, git_snapshot_before_batch=snapshot)
        assert state.git_snapshot_before_batch is not None
        assert state.git_snapshot_before_batch.head_commit == "abc123"

    def test_state_backwards_compatible(self):
        """ExecutionState remains backwards compatible with existing fields."""
        profile = Profile(name="test", driver="cli:claude")
        state = ExecutionState(
            profile=profile,
            workflow_status="running",
            human_approved=True,
        )
        # Old fields still work
        assert state.workflow_status == "running"
        assert state.human_approved is True
        # New fields have defaults
        assert state.execution_plan is None
        assert state.developer_status == DeveloperStatus.EXECUTING


class TestProfileTrustLevel:
    """Tests for Profile trust_level field."""

    def test_profile_default_trust_level(self):
        """Profile trust_level defaults to STANDARD."""
        profile = Profile(name="test", driver="cli:claude")
        assert profile.trust_level == TrustLevel.STANDARD

    def test_profile_paranoid_trust_level(self):
        """Profile accepts PARANOID trust_level."""
        profile = Profile(
            name="test",
            driver="cli:claude",
            trust_level=TrustLevel.PARANOID,
        )
        assert profile.trust_level == TrustLevel.PARANOID

    def test_profile_autonomous_trust_level(self):
        """Profile accepts AUTONOMOUS trust_level."""
        profile = Profile(
            name="test",
            driver="cli:claude",
            trust_level=TrustLevel.AUTONOMOUS,
        )
        assert profile.trust_level == TrustLevel.AUTONOMOUS

    def test_profile_batch_checkpoint_enabled_default(self):
        """Profile batch_checkpoint_enabled defaults to True."""
        profile = Profile(name="test", driver="cli:claude")
        assert profile.batch_checkpoint_enabled is True

    def test_profile_batch_checkpoint_disabled(self):
        """Profile accepts batch_checkpoint_enabled=False."""
        profile = Profile(
            name="test",
            driver="cli:claude",
            batch_checkpoint_enabled=False,
        )
        assert profile.batch_checkpoint_enabled is False

    def test_profile_yaml_serialization(self):
        """Profile with trust_level serializes correctly."""
        profile = Profile(
            name="test",
            driver="cli:claude",
            trust_level=TrustLevel.AUTONOMOUS,
            batch_checkpoint_enabled=False,
        )
        data = profile.model_dump()
        assert data["trust_level"] == "autonomous"
        assert data["batch_checkpoint_enabled"] is False

        restored = Profile.model_validate(data)
        assert restored.trust_level == TrustLevel.AUTONOMOUS
        assert restored.batch_checkpoint_enabled is False
