# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for Architect agent."""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.agents.architect import Architect, ArchitectContextStrategy, TaskListResponse
from amelia.core.state import ExecutionState, Task
from amelia.core.types import Design, Issue


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
    ) -> None:
        """Test plan() reads design from state, not from parameter."""
        issue = mock_issue_factory(title="Build feature", description="Feature desc")
        design = mock_design_factory(title="Feature Design", goal="Build it well")
        state = mock_execution_state_factory(issue=issue, design=design)

        # Mock driver to return a valid TaskListResponse
        mock_driver.generate.return_value = mock_task_response

        architect = Architect(driver=mock_driver)
        result = await architect.plan(state, workflow_id="test-workflow-123")

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
        from datetime import datetime
        from unittest.mock import AsyncMock

        from amelia.core.types import StreamEvent, StreamEventType

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
        from unittest.mock import AsyncMock

        from amelia.core.state import Task

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
        from unittest.mock import AsyncMock
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

class TestArchitectWorkflowIdRequired:
    """Test that workflow_id is required for Architect.plan()."""

    async def test_plan_requires_workflow_id(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory,
        mock_issue_factory,
        mock_task_response,
    ) -> None:
        """Test that plan() requires workflow_id parameter."""
        from unittest.mock import AsyncMock

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
