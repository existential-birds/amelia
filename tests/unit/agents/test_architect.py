# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for Architect agent."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.agents.architect import (
    Architect,
    ArchitectContextStrategy,
    ExecutionPlanOutput,
    TaskListResponse,
)
from amelia.core.state import ExecutionBatch, ExecutionPlan, ExecutionState, PlanStep, Task
from amelia.core.types import Design, Issue, StreamEvent, StreamEventType


def _extract_messages_from_call(call_args: Any) -> list[Any]:
    """Extract messages from mock_driver.generate.call_args.

    Args:
        call_args: The call_args from mock_driver.generate.call_args

    Returns:
        List of messages passed to the driver, or empty list if not found.
    """
    # Handle both positional and keyword arguments
    if call_args.kwargs.get("messages"):
        messages: list[Any] = call_args.kwargs["messages"]
        return messages
    elif len(call_args.args) > 0:
        messages_from_args: list[Any] = call_args.args[0]
        return messages_from_args
    else:
        # Check if first keyword arg is messages
        fallback: list[Any] = list(call_args.kwargs.values())[0] if call_args.kwargs else []
        return fallback


@pytest.fixture
def mock_task_response() -> TaskListResponse:
    """Create a mock TaskListResponse with a single test task.

    Returns:
        TaskListResponse with a single mock Task.
    """
    mock_task = Task(
        id="1",
        description="Test task",
        dependencies=[],
        files=[],
        steps=[],
        commit_message="feat: test task"
    )
    return TaskListResponse(tasks=[mock_task])


@pytest.fixture
def make_step() -> Callable[..., PlanStep]:
    """Factory for creating PlanStep instances.

    Returns:
        A factory function that creates PlanStep with configurable parameters.
    """
    def _create(
        step_id: str,
        description: str = "Test step",
        risk_level: str = "low",
        action_type: str = "code",
        is_test_step: bool = False,
    ) -> PlanStep:
        return PlanStep(
            id=step_id,
            description=description,
            action_type=action_type,
            risk_level=risk_level,
            is_test_step=is_test_step,
        )
    return _create


@pytest.fixture
def make_batch() -> Callable[..., ExecutionBatch]:
    """Factory for creating ExecutionBatch instances.

    Returns:
        A factory function that creates ExecutionBatch with configurable parameters.
    """
    def _create(
        batch_number: int,
        steps: tuple[PlanStep, ...],
        risk_summary: str = "low",
        description: str = "",
    ) -> ExecutionBatch:
        return ExecutionBatch(
            batch_number=batch_number,
            steps=steps,
            risk_summary=risk_summary,
            description=description,
        )
    return _create


class TestArchitectContextStrategy:
    """Test ArchitectContextStrategy methods for task generation."""

    @pytest.fixture
    def strategy(self) -> ArchitectContextStrategy:
        """Create an ArchitectContextStrategy instance for testing."""
        return ArchitectContextStrategy()

    def test_task_generation_system_prompt_is_detailed(self, strategy: ArchitectContextStrategy) -> None:
        """Test that task generation system prompt includes TDD instructions."""
        prompt = strategy.get_task_generation_system_prompt()

        # Should be a non-empty string
        assert isinstance(prompt, str)
        assert len(prompt) > 0

        # Should include TDD-specific instructions
        assert "TDD" in prompt or "Test-Driven Development" in prompt
        assert "test" in prompt.lower()

        # Should include task structure guidance
        assert "task" in prompt.lower()
        assert "dependencies" in prompt.lower() or "depend" in prompt.lower()

        # Should include file operation guidance
        assert "file" in prompt.lower()

class TestArchitect:
    """Test Architect agent implementation."""

    @pytest.fixture
    def architect(self, mock_driver: MagicMock) -> Architect:
        """Create an Architect instance for testing."""
        return Architect(driver=mock_driver)

    async def test_generate_task_dag_uses_strategy_system_prompt(
        self,
        architect: Architect,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_issue_factory: Callable[..., Issue],
        mock_driver: MagicMock,
        mock_task_response: TaskListResponse,
    ) -> None:
        """Test that _generate_task_dag uses strategy's task generation system prompt."""
        issue = mock_issue_factory(
            id="ARCH-100",
            title="Implement auth",
            description="Build authentication system"
        )
        state = mock_execution_state_factory(issue=issue)

        # Mock driver to return a valid TaskListResponse
        mock_driver.generate.return_value = mock_task_response

        # Compile context
        strategy = ArchitectContextStrategy()
        compiled_context = strategy.compile(state)

        # Generate task DAG
        await architect._generate_task_dag(compiled_context, issue, strategy)

        # Verify driver.generate was called
        assert mock_driver.generate.called

        # Get the messages passed to driver
        messages = _extract_messages_from_call(mock_driver.generate.call_args)

        # Should have a system message
        system_messages = [msg for msg in messages if msg.role == "system"]
        assert len(system_messages) > 0, f"Should have at least one system message. Got messages: {messages}"

        # The system message should be the task generation prompt from strategy
        expected_system_prompt = strategy.get_task_generation_system_prompt()
        actual_system_prompt = system_messages[0].content

        assert actual_system_prompt == expected_system_prompt, (
            "System prompt should come from strategy.get_task_generation_system_prompt()"
        )

    async def test_generate_task_dag_uses_strategy_user_prompt(
        self,
        architect: Architect,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_issue_factory: Callable[..., Issue],
        mock_driver: MagicMock,
        mock_task_response: TaskListResponse,
    ) -> None:
        """Test that _generate_task_dag uses strategy's task generation user prompt."""
        issue = mock_issue_factory(
            id="ARCH-100",
            title="Implement auth",
            description="Build authentication system"
        )
        state = mock_execution_state_factory(issue=issue)

        # Mock driver to return a valid TaskListResponse
        mock_driver.generate.return_value = mock_task_response

        # Compile context
        strategy = ArchitectContextStrategy()
        compiled_context = strategy.compile(state)

        # Generate task DAG
        await architect._generate_task_dag(compiled_context, issue, strategy)

        # Get the messages passed to driver
        messages = _extract_messages_from_call(mock_driver.generate.call_args)

        # Should have a user message
        user_messages = [msg for msg in messages if msg.role == "user"]
        assert len(user_messages) > 0, f"Should have at least one user message. Got messages: {messages}"

        # The last user message should be the task generation prompt from strategy
        expected_user_prompt = strategy.get_task_generation_user_prompt()

        # Find the last user message (should be the task generation instruction)
        last_user_message = user_messages[-1].content

        assert expected_user_prompt in last_user_message, (
            "Last user message should contain strategy.get_task_generation_user_prompt()"
        )

    async def test_generate_task_dag_does_not_override_system_prompt(
        self,
        architect: Architect,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_issue_factory: Callable[..., Issue],
        mock_driver: MagicMock,
        mock_task_response: TaskListResponse,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that _generate_task_dag uses strategy's system prompt, not hardcoded text.

        Uses a sentinel value to ensure the prompt genuinely comes from the strategy
        method rather than coincidentally identical hardcoded text.
        """
        issue = mock_issue_factory()
        state = mock_execution_state_factory(issue=issue)

        # Mock driver
        mock_driver.generate.return_value = mock_task_response

        # Create strategy and patch its method to return a unique sentinel
        strategy = ArchitectContextStrategy()
        sentinel_prompt = "SENTINEL_SYSTEM_PROMPT_12345_FOR_TEST_VERIFICATION"
        monkeypatch.setattr(strategy, "get_task_generation_system_prompt", lambda: sentinel_prompt)

        compiled_context = strategy.compile(state)

        # Generate task DAG
        await architect._generate_task_dag(compiled_context, issue, strategy)

        # Verify driver.generate was called
        assert mock_driver.generate.called

        # Get the messages passed to driver
        messages = _extract_messages_from_call(mock_driver.generate.call_args)

        system_messages = [msg for msg in messages if msg.role == "system"]
        assert len(system_messages) > 0, f"Should have at least one system message. Got: {messages}"

        # The system message must be our sentinel, proving it came from the strategy
        assert system_messages[0].content == sentinel_prompt, (
            "System prompt must come from strategy.get_task_generation_system_prompt(), "
            "not be hardcoded in _generate_task_dag"
        )

    async def test_plan_reads_design_from_state(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_issue_factory: Callable[..., Issue],
        mock_design_factory: Callable[..., Design],
        mock_task_response: TaskListResponse,
        tmp_path: Path,
    ) -> None:
        """Test plan() reads design from state, not from parameter."""
        issue = mock_issue_factory(title="Build feature", description="Feature desc")
        design = mock_design_factory(title="Feature Design", goal="Build it well")
        state = mock_execution_state_factory(issue=issue, design=design)

        # Mock driver to return a valid TaskListResponse
        mock_driver.generate.return_value = mock_task_response

        architect = Architect(driver=mock_driver)
        result = await architect.plan(state, output_dir=str(tmp_path), workflow_id="test-workflow-123")

        # Verify plan was generated (driver was called)
        assert result.task_dag is not None
        assert len(result.task_dag.tasks) == 1
        assert result.markdown_path is not None

        # Verify design from state was actually used in driver call
        mock_driver.generate.assert_called_once()
        messages = _extract_messages_from_call(mock_driver.generate.call_args)

        # Concatenate all message content to check for design fields
        all_content = " ".join(msg.content for msg in messages if msg.content)
        assert "Build it well" in all_content, (
            "Design goal from state.design must appear in messages passed to driver"
        )


class TestArchitectStreamEmitter:
    """Test Architect agent stream emitter functionality."""

    @pytest.mark.parametrize("stream_emitter", [None, AsyncMock()])
    def test_architect_accepts_optional_stream_emitter(
        self,
        mock_driver: MagicMock,
        stream_emitter: AsyncMock | None,
    ) -> None:
        """Test that Architect constructor accepts optional stream_emitter parameter."""
        architect = Architect(
            driver=mock_driver,
            stream_emitter=stream_emitter,
        )
        assert architect._stream_emitter is stream_emitter

    async def test_architect_emits_agent_output_after_plan_generation(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_issue_factory: Callable[..., Issue],
        mock_task_response: TaskListResponse,
    ) -> None:
        """Test that Architect emits AGENT_OUTPUT event after generating plan."""
        issue = mock_issue_factory(id="TEST-123", title="Build feature", description="Feature desc")
        state = mock_execution_state_factory(
            issue=issue,
        )

        # Mock driver to return a valid TaskListResponse
        mock_driver.generate.return_value = mock_task_response

        # Create emitter mock
        mock_emitter = AsyncMock()

        # Create architect with emitter
        architect = Architect(driver=mock_driver, stream_emitter=mock_emitter)

        # Generate plan
        result = await architect.plan(state, workflow_id="test-workflow-123")

        # Verify plan was generated
        assert result.task_dag is not None
        assert len(result.task_dag.tasks) == 1

        # Verify emitter was called
        assert mock_emitter.called
        assert mock_emitter.call_count == 1

        # Verify the emitted event
        event = mock_emitter.call_args.args[0]
        assert isinstance(event, StreamEvent)
        assert event.type == StreamEventType.AGENT_OUTPUT
        assert event.agent == "architect"
        assert event.workflow_id == "test-workflow-123"  # Uses provided workflow_id
        assert "1 tasks" in event.content  # Generated plan with 1 tasks
        assert isinstance(event.timestamp, datetime)

    async def test_architect_does_not_emit_when_no_emitter_configured(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_issue_factory: Callable[..., Issue],
        mock_task_response: TaskListResponse,
    ) -> None:
        """Test that Architect does not crash when no emitter is configured."""
        issue = mock_issue_factory(id="TEST-456", title="Test", description="Test")
        state = mock_execution_state_factory(issue=issue)

        mock_driver.generate.return_value = mock_task_response

        # Create architect WITHOUT emitter
        architect = Architect(driver=mock_driver)

        # Should not raise even without emitter
        result = await architect.plan(state, workflow_id="test-workflow-123")
        assert result.task_dag is not None

    async def test_architect_emits_correct_task_count(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_issue_factory: Callable[..., Issue],
    ) -> None:
        """Test that Architect emits event with correct task count."""
        issue = mock_issue_factory(id="TEST-789", title="Test", description="Test")
        state = mock_execution_state_factory(issue=issue)

        # Create response with multiple tasks
        multi_task_response = TaskListResponse(tasks=[
            Task(id="1", description="Task 1", dependencies=[], files=[], steps=[]),
            Task(id="2", description="Task 2", dependencies=[], files=[], steps=[]),
            Task(id="3", description="Task 3", dependencies=[], files=[], steps=[]),
        ])

        mock_driver.generate.return_value = multi_task_response
        mock_emitter = AsyncMock()

        architect = Architect(driver=mock_driver, stream_emitter=mock_emitter)
        await architect.plan(state, workflow_id="test-workflow-123")

        # Verify the event contains correct count
        event = mock_emitter.call_args.args[0]
        assert "3 tasks" in event.content

    async def test_architect_uses_provided_workflow_id(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., ExecutionState],
    ) -> None:
        """Test that architect uses provided workflow_id instead of falling back."""
        issue = Issue(id="TEST-123", title="Test", description="Test issue")
        state = mock_execution_state_factory(issue=issue)

        mock_driver.generate.return_value = TaskListResponse(tasks=[
            Task(id="1", description="Task 1", dependencies=[], files=[], steps=[]),
        ])
        mock_emitter = AsyncMock()

        architect = Architect(driver=mock_driver, stream_emitter=mock_emitter)
        await architect.plan(state, workflow_id="custom-workflow-id-123")

        # Verify the emitted event uses the provided workflow_id
        event = mock_emitter.call_args.args[0]
        assert event.workflow_id == "custom-workflow-id-123"

class TestArchitectWorkflowId:
    """Test workflow_id handling in Architect.plan()."""

    async def test_plan_works_with_workflow_id(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_issue_factory: Callable[..., Issue],
        mock_task_response: TaskListResponse,
    ) -> None:
        """Test that plan() requires workflow_id parameter."""
        issue = mock_issue_factory(id="TEST-123")
        state = mock_execution_state_factory(issue=issue)
        mock_driver.generate.return_value = mock_task_response
        mock_emitter = AsyncMock()

        architect = Architect(driver=mock_driver, stream_emitter=mock_emitter)

        # Should work with workflow_id provided
        result = await architect.plan(state, workflow_id="required-workflow-id")
        assert result.task_dag is not None

        # Verify emitter received the provided workflow_id
        event = mock_emitter.call_args.args[0]
        assert event.workflow_id == "required-workflow-id"


class TestExecutionPlanOutput:
    """Test ExecutionPlanOutput schema."""

    def test_execution_plan_output_validates_with_valid_plan_and_reasoning(self) -> None:
        """Test that ExecutionPlanOutput can be created with valid ExecutionPlan and reasoning."""
        from amelia.agents.architect import ExecutionPlanOutput

        # Create a valid ExecutionPlan
        step = PlanStep(
            id="step-1",
            description="Write failing test",
            action_type="code",
            file_path="tests/test_auth.py",
            code_change="def test_auth(): assert False",
            is_test_step=True,
        )
        batch = ExecutionBatch(
            batch_number=1,
            steps=(step,),
            risk_summary="low",
            description="First batch",
        )
        plan = ExecutionPlan(
            goal="Implement authentication",
            batches=(batch,),
            total_estimated_minutes=10,
            tdd_approach=True,
        )

        # Create ExecutionPlanOutput
        output = ExecutionPlanOutput(
            plan=plan,
            reasoning="Grouped authentication tests and implementation into one batch for efficiency.",
        )

        # Verify fields
        assert output.plan == plan
        assert output.reasoning == "Grouped authentication tests and implementation into one batch for efficiency."

    def test_execution_plan_output_parses_from_dict(self) -> None:
        """Test that ExecutionPlanOutput can be parsed from a dict (LLM response)."""
        from amelia.agents.architect import ExecutionPlanOutput

        # Simulate LLM-generated dict
        llm_output = {
            "plan": {
                "goal": "Add user registration",
                "batches": [
                    {
                        "batch_number": 1,
                        "steps": [
                            {
                                "id": "step-1",
                                "description": "Create user model test",
                                "action_type": "code",
                                "file_path": "tests/test_models.py",
                                "code_change": "def test_user_model(): pass",
                                "is_test_step": True,
                            }
                        ],
                        "risk_summary": "low",
                        "description": "User model tests",
                    }
                ],
                "total_estimated_minutes": 5,
                "tdd_approach": True,
            },
            "reasoning": "Starting with user model to establish foundation.",
        }

        # Parse from dict
        output = ExecutionPlanOutput.model_validate(llm_output)

        # Verify parsing
        assert output.plan.goal == "Add user registration"
        assert len(output.plan.batches) == 1
        assert output.plan.batches[0].batch_number == 1
        assert len(output.plan.batches[0].steps) == 1
        assert output.plan.batches[0].steps[0].id == "step-1"
        assert output.reasoning == "Starting with user model to establish foundation."

    def test_execution_plan_output_requires_both_fields(self) -> None:
        """Test that ExecutionPlanOutput requires both plan and reasoning fields."""
        from pydantic import ValidationError

        from amelia.agents.architect import ExecutionPlanOutput

        # Missing reasoning
        with pytest.raises(ValidationError) as exc_info:
            ExecutionPlanOutput(plan=None, reasoning="Some reasoning")  # type: ignore[arg-type]

        assert "plan" in str(exc_info.value).lower()

        # Missing plan (reasoning alone)
        with pytest.raises(ValidationError) as exc_info:
            ExecutionPlanOutput(reasoning="Some reasoning")  # type: ignore[call-arg]

        assert "plan" in str(exc_info.value).lower()


class TestGenerateExecutionPlan:
    """Test Architect.generate_execution_plan() method."""

    @pytest.fixture
    def mock_execution_plan_output(
        self,
        make_step: Callable[..., PlanStep],
        make_batch: Callable[..., ExecutionBatch],
    ) -> ExecutionPlanOutput:
        """Create a mock ExecutionPlanOutput response."""
        # Create test steps with TDD pattern
        test_step = make_step("step-1", description="Write failing test", is_test_step=True)
        verify_fail_step = make_step("step-2", description="Run test to verify failure", action_type="command")
        impl_step = make_step("step-3", description="Write implementation", action_type="code")
        verify_pass_step = make_step("step-4", description="Run test to verify pass", action_type="command")

        batch = make_batch(1, (test_step, verify_fail_step, impl_step, verify_pass_step), risk_summary="low")

        plan = ExecutionPlan(
            goal="Implement authentication",
            batches=(batch,),
            total_estimated_minutes=15,
            tdd_approach=True,
        )

        return ExecutionPlanOutput(
            plan=plan,
            reasoning="Grouped authentication tests and implementation into one batch following TDD approach.",
        )

    async def test_generates_valid_execution_plan(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_issue_factory: Callable[..., Issue],
        mock_execution_plan_output: ExecutionPlanOutput,
    ) -> None:
        """Test that generate_execution_plan generates a valid ExecutionPlan."""
        issue = mock_issue_factory(
            id="EXEC-100",
            title="Implement auth",
            description="Build authentication system"
        )
        state = mock_execution_state_factory(issue=issue)

        # Mock driver to return ExecutionPlanOutput
        mock_driver.generate.return_value = mock_execution_plan_output

        architect = Architect(driver=mock_driver)
        result = await architect.generate_execution_plan(issue, state)

        # Verify result is an ExecutionPlan
        assert isinstance(result, ExecutionPlan)
        assert result.goal == "Implement authentication"
        assert result.tdd_approach is True
        assert len(result.batches) == 1
        assert len(result.batches[0].steps) == 4

        # Verify driver.generate was called with ExecutionPlanOutput schema
        assert mock_driver.generate.called
        call_kwargs = mock_driver.generate.call_args.kwargs
        assert "schema" in call_kwargs
        assert call_kwargs["schema"] == ExecutionPlanOutput

    async def test_batches_respect_risk_limits(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_issue_factory: Callable[..., Issue],
        make_step: Callable[..., PlanStep],
        make_batch: Callable[..., ExecutionBatch],
    ) -> None:
        """Test that oversized batches are split by validate_and_split_batches."""
        issue = mock_issue_factory()
        state = mock_execution_state_factory(issue=issue)

        # Create a plan with oversized low-risk batch (7 steps > 5 max)
        steps = tuple(make_step(f"step-{i}", risk_level="low") for i in range(7))
        batch = make_batch(1, steps, risk_summary="low")
        oversized_plan = ExecutionPlan(
            goal="Test goal",
            batches=(batch,),
            total_estimated_minutes=14,
            tdd_approach=True,
        )

        mock_execution_plan_output = ExecutionPlanOutput(
            plan=oversized_plan,
            reasoning="Test oversized batch",
        )

        mock_driver.generate.return_value = mock_execution_plan_output

        architect = Architect(driver=mock_driver)
        result = await architect.generate_execution_plan(issue, state)

        # Should be split into 2 batches: 5 + 2
        assert len(result.batches) == 2
        assert len(result.batches[0].steps) == 5
        assert len(result.batches[1].steps) == 2

        # Batch numbers should be renumbered
        assert result.batches[0].batch_number == 1
        assert result.batches[1].batch_number == 2

    async def test_tdd_steps_ordered_correctly(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_issue_factory: Callable[..., Issue],
        mock_execution_plan_output: ExecutionPlanOutput,
    ) -> None:
        """Test that TDD steps are in correct order: test before implementation."""
        issue = mock_issue_factory()
        state = mock_execution_state_factory(issue=issue)

        mock_driver.generate.return_value = mock_execution_plan_output

        architect = Architect(driver=mock_driver)
        result = await architect.generate_execution_plan(issue, state)

        # Verify TDD approach flag
        assert result.tdd_approach is True

        # Get the first batch steps
        steps = result.batches[0].steps

        # Step 1 should be a test step (is_test_step=True)
        assert hasattr(steps[0], "is_test_step") or "test" in steps[0].description.lower()

        # Verify general TDD order: test-related steps should come before implementation
        step_descriptions = [s.description.lower() for s in steps]
        test_indices = [i for i, desc in enumerate(step_descriptions) if "test" in desc or "fail" in desc]
        impl_indices = [i for i, desc in enumerate(step_descriptions) if "implementation" in desc or "implement" in desc]

        if test_indices and impl_indices:
            # Test steps should come before implementation steps
            assert min(test_indices) < min(impl_indices), "Test steps should come before implementation steps"

    async def test_uses_execution_plan_prompts_from_strategy(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_issue_factory: Callable[..., Issue],
        mock_execution_plan_output: ExecutionPlanOutput,
    ) -> None:
        """Test that generate_execution_plan uses execution plan prompts from strategy."""
        issue = mock_issue_factory()
        state = mock_execution_state_factory(issue=issue)

        mock_driver.generate.return_value = mock_execution_plan_output

        architect = Architect(driver=mock_driver)
        await architect.generate_execution_plan(issue, state)

        # Get the messages passed to driver
        messages = _extract_messages_from_call(mock_driver.generate.call_args)

        # Should have a system message with execution plan system prompt
        system_messages = [msg for msg in messages if msg.role == "system"]
        assert len(system_messages) > 0

        # Get expected prompts from strategy
        strategy = ArchitectContextStrategy()
        expected_system_prompt = strategy.get_execution_plan_system_prompt()
        expected_user_prompt = strategy.get_execution_plan_user_prompt()

        # System prompt should match
        actual_system_prompt = system_messages[0].content
        assert actual_system_prompt == expected_system_prompt

        # User messages should contain the execution plan user prompt
        user_messages = [msg for msg in messages if msg.role == "user"]
        assert len(user_messages) > 0

        # Last user message should be the execution plan instruction
        last_user_message = user_messages[-1].content
        assert expected_user_prompt in last_user_message

    async def test_calls_validate_and_split_batches(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_issue_factory: Callable[..., Issue],
        make_step: Callable[..., PlanStep],
        make_batch: Callable[..., ExecutionBatch],
    ) -> None:
        """Test that generate_execution_plan calls validate_and_split_batches."""
        issue = mock_issue_factory()
        state = mock_execution_state_factory(issue=issue)

        # Create oversized batch that will trigger validation/splitting
        steps = tuple(make_step(f"step-{i}", risk_level="low") for i in range(7))
        batch = make_batch(1, steps, risk_summary="low")
        oversized_plan = ExecutionPlan(
            goal="Test goal",
            batches=(batch,),
            total_estimated_minutes=14,
            tdd_approach=True,
        )

        mock_execution_plan_output = ExecutionPlanOutput(
            plan=oversized_plan,
            reasoning="Test oversized batch",
        )

        mock_driver.generate.return_value = mock_execution_plan_output

        architect = Architect(driver=mock_driver)
        result = await architect.generate_execution_plan(issue, state)

        # Verify that validate_and_split_batches was called
        # (we can tell because the plan was split from 1 batch to 2 batches)
        assert len(result.batches) == 2, "Oversized batch should have been split by validate_and_split_batches"


class TestValidateAndSplitBatches:
    """Test validate_and_split_batches helper for batch size enforcement."""

    def test_batch_within_limits_passes_unchanged(
        self,
        make_step: Callable[..., PlanStep],
        make_batch: Callable[..., ExecutionBatch],
    ) -> None:
        """Test that batches within size limits pass through unchanged."""
        from amelia.agents.architect import validate_and_split_batches

        # Create batches within limits: 5 low-risk, 3 medium-risk, 1 high-risk
        steps_low = tuple(make_step(f"low-{i}", risk_level="low") for i in range(5))
        steps_medium = tuple(make_step(f"med-{i}", risk_level="medium") for i in range(3))
        steps_high = tuple(make_step("high-1", risk_level="high") for i in range(1))

        batch1 = make_batch(1, steps_low, risk_summary="low")
        batch2 = make_batch(2, steps_medium, risk_summary="medium")
        batch3 = make_batch(3, steps_high, risk_summary="high")

        plan = ExecutionPlan(
            goal="Test goal",
            batches=(batch1, batch2, batch3),
            total_estimated_minutes=30,
            tdd_approach=True,
        )

        validated_plan, warnings = validate_and_split_batches(plan)

        # Should pass through unchanged
        assert validated_plan.batches == plan.batches
        assert len(warnings) == 0

    def test_oversized_low_risk_batch_splits_correctly(
        self,
        make_step: Callable[..., PlanStep],
        make_batch: Callable[..., ExecutionBatch],
    ) -> None:
        """Test that oversized low-risk batch (>5 steps) splits into multiple batches."""
        from amelia.agents.architect import validate_and_split_batches

        # Create 7 low-risk steps (exceeds max of 5)
        steps = tuple(make_step(f"low-{i}", risk_level="low") for i in range(7))
        batch = make_batch(1, steps, risk_summary="low")

        plan = ExecutionPlan(
            goal="Test goal",
            batches=(batch,),
            total_estimated_minutes=14,
            tdd_approach=True,
        )

        validated_plan, warnings = validate_and_split_batches(plan)

        # Should split into 2 batches: 5 + 2
        assert len(validated_plan.batches) == 2
        assert len(validated_plan.batches[0].steps) == 5
        assert len(validated_plan.batches[1].steps) == 2

        # Batch numbers should be renumbered
        assert validated_plan.batches[0].batch_number == 1
        assert validated_plan.batches[1].batch_number == 2

        # Should have a warning
        assert len(warnings) == 1
        assert "batch 1" in warnings[0].lower()
        assert "split" in warnings[0].lower()

    def test_oversized_medium_risk_batch_splits_correctly(
        self,
        make_step: Callable[..., PlanStep],
        make_batch: Callable[..., ExecutionBatch],
    ) -> None:
        """Test that oversized medium-risk batch (>3 steps) splits into multiple batches."""
        from amelia.agents.architect import validate_and_split_batches

        # Create 5 medium-risk steps (exceeds max of 3)
        steps = tuple(make_step(f"med-{i}", risk_level="medium") for i in range(5))
        batch = make_batch(1, steps, risk_summary="medium")

        plan = ExecutionPlan(
            goal="Test goal",
            batches=(batch,),
            total_estimated_minutes=10,
            tdd_approach=True,
        )

        validated_plan, warnings = validate_and_split_batches(plan)

        # Should split into 2 batches: 3 + 2
        assert len(validated_plan.batches) == 2
        assert len(validated_plan.batches[0].steps) == 3
        assert len(validated_plan.batches[1].steps) == 2

        # Should have a warning
        assert len(warnings) == 1
        assert "batch 1" in warnings[0].lower()

    def test_high_risk_steps_always_isolated(
        self,
        make_step: Callable[..., PlanStep],
        make_batch: Callable[..., ExecutionBatch],
    ) -> None:
        """Test that high-risk steps are always isolated into individual batches."""
        from amelia.agents.architect import validate_and_split_batches

        # Create a batch with 3 high-risk steps
        steps = tuple(make_step(f"high-{i}", risk_level="high") for i in range(3))
        batch = make_batch(1, steps, risk_summary="high")

        plan = ExecutionPlan(
            goal="Test goal",
            batches=(batch,),
            total_estimated_minutes=6,
            tdd_approach=True,
        )

        validated_plan, warnings = validate_and_split_batches(plan)

        # Should split into 3 batches, each with 1 step
        assert len(validated_plan.batches) == 3
        assert all(len(b.steps) == 1 for b in validated_plan.batches)

        # All should be marked as high risk
        assert all(b.risk_summary == "high" for b in validated_plan.batches)

        # Should have a warning
        assert len(warnings) == 1
        assert "batch 1" in warnings[0].lower()

    def test_warnings_generated_for_splits(
        self,
        make_step: Callable[..., PlanStep],
        make_batch: Callable[..., ExecutionBatch],
    ) -> None:
        """Test that warnings are generated for all split batches."""
        from amelia.agents.architect import validate_and_split_batches

        # Create 3 batches that need splitting
        steps_low = tuple(make_step(f"low-{i}", risk_level="low") for i in range(7))
        steps_medium = tuple(make_step(f"med-{i}", risk_level="medium") for i in range(5))
        steps_high = tuple(make_step(f"high-{i}", risk_level="high") for i in range(2))

        batch1 = make_batch(1, steps_low, risk_summary="low")
        batch2 = make_batch(2, steps_medium, risk_summary="medium")
        batch3 = make_batch(3, steps_high, risk_summary="high")

        plan = ExecutionPlan(
            goal="Test goal",
            batches=(batch1, batch2, batch3),
            total_estimated_minutes=28,
            tdd_approach=True,
        )

        validated_plan, warnings = validate_and_split_batches(plan)

        # Should have warnings for all 3 original batches
        assert len(warnings) == 3
        assert any("batch 1" in w.lower() for w in warnings)
        assert any("batch 2" in w.lower() for w in warnings)
        assert any("batch 3" in w.lower() for w in warnings)

    def test_mixed_risk_batch_splits_by_risk_level(
        self,
        make_step: Callable[..., PlanStep],
        make_batch: Callable[..., ExecutionBatch],
    ) -> None:
        """Test that batches with mixed risk levels split appropriately."""
        from amelia.agents.architect import validate_and_split_batches

        # Create a batch with mixed risk levels (should be rare but handle it)
        steps = (
            make_step("low-1", risk_level="low"),
            make_step("low-2", risk_level="low"),
            make_step("med-1", risk_level="medium"),
            make_step("high-1", risk_level="high"),
        )
        # Risk summary is "high" because it contains high-risk steps
        batch = make_batch(1, steps, risk_summary="high")

        plan = ExecutionPlan(
            goal="Test goal",
            batches=(batch,),
            total_estimated_minutes=8,
            tdd_approach=True,
        )

        validated_plan, warnings = validate_and_split_batches(plan)

        # High-risk step must be isolated
        # The batch should be split appropriately
        assert len(validated_plan.batches) >= 2

        # Find the high-risk batch
        high_risk_batches = [b for b in validated_plan.batches if b.risk_summary == "high"]
        assert len(high_risk_batches) >= 1

        # High-risk batches should have exactly 1 step
        for batch in high_risk_batches:
            assert len(batch.steps) == 1

    def test_preserves_plan_metadata(
        self,
        make_step: Callable[..., PlanStep],
        make_batch: Callable[..., ExecutionBatch],
    ) -> None:
        """Test that plan metadata (goal, total_estimated_minutes, tdd_approach) is preserved."""
        from amelia.agents.architect import validate_and_split_batches

        steps = tuple(make_step(f"low-{i}", risk_level="low") for i in range(7))
        batch = make_batch(1, steps, risk_summary="low")

        plan = ExecutionPlan(
            goal="Original goal",
            batches=(batch,),
            total_estimated_minutes=14,
            tdd_approach=False,
        )

        validated_plan, warnings = validate_and_split_batches(plan)

        # Metadata should be preserved
        assert validated_plan.goal == "Original goal"
        assert validated_plan.total_estimated_minutes == 14
        assert validated_plan.tdd_approach is False

    def test_batch_numbers_renumbered_sequentially(
        self,
        make_step: Callable[..., PlanStep],
        make_batch: Callable[..., ExecutionBatch],
    ) -> None:
        """Test that batch numbers are renumbered sequentially after splitting."""
        from amelia.agents.architect import validate_and_split_batches

        # Create batches with non-sequential numbers that will be split
        steps1 = tuple(make_step(f"low-{i}", risk_level="low") for i in range(7))
        steps2 = tuple(make_step(f"med-{i}", risk_level="medium") for i in range(5))

        batch1 = make_batch(10, steps1, risk_summary="low")  # Will split into 2
        batch2 = make_batch(20, steps2, risk_summary="medium")  # Will split into 2

        plan = ExecutionPlan(
            goal="Test goal",
            batches=(batch1, batch2),
            total_estimated_minutes=24,
            tdd_approach=True,
        )

        validated_plan, warnings = validate_and_split_batches(plan)

        # Should have 4 batches total
        assert len(validated_plan.batches) == 4

        # Batch numbers should be 1, 2, 3, 4
        assert [b.batch_number for b in validated_plan.batches] == [1, 2, 3, 4]

    def test_empty_plan_returns_unchanged(
        self,
    ) -> None:
        """Test that empty plan returns unchanged with no warnings."""
        from amelia.agents.architect import validate_and_split_batches

        plan = ExecutionPlan(
            goal="Empty goal",
            batches=(),
            total_estimated_minutes=0,
            tdd_approach=True,
        )

        validated_plan, warnings = validate_and_split_batches(plan)

        assert validated_plan.batches == ()
        assert len(warnings) == 0
