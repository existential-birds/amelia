# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for Architect agent."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

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

    def test_has_task_generation_system_prompt_method(self, strategy: ArchitectContextStrategy) -> None:
        """Test that strategy has get_task_generation_system_prompt method."""
        assert hasattr(strategy, "get_task_generation_system_prompt")
        assert callable(strategy.get_task_generation_system_prompt)

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

    def test_task_generation_system_prompt_mentions_required_fields(self, strategy: ArchitectContextStrategy) -> None:
        """Test that task generation prompt specifies required task fields."""
        prompt = strategy.get_task_generation_system_prompt()

        # Should mention key task fields
        assert "id" in prompt.lower()
        assert "description" in prompt.lower()
        assert "steps" in prompt.lower()

    def test_task_generation_system_prompt_is_stable(self, strategy: ArchitectContextStrategy) -> None:
        """Test that task generation system prompt is stable across calls."""
        prompt1 = strategy.get_task_generation_system_prompt()
        prompt2 = strategy.get_task_generation_system_prompt()

        assert prompt1 == prompt2

    def test_get_task_generation_user_prompt_method_exists(self, strategy: ArchitectContextStrategy) -> None:
        """Test that strategy has get_task_generation_user_prompt method."""
        assert hasattr(strategy, "get_task_generation_user_prompt")
        assert callable(strategy.get_task_generation_user_prompt)

    def test_task_generation_user_prompt_is_concise(self, strategy: ArchitectContextStrategy) -> None:
        """Test that task generation user prompt is concise and actionable."""
        prompt = strategy.get_task_generation_user_prompt()

        # Should be a non-empty string
        assert isinstance(prompt, str)
        assert len(prompt) > 0

        # Should be relatively concise (not a wall of text)
        # User prompt should be shorter than system prompt
        system_prompt = strategy.get_task_generation_system_prompt()
        assert len(prompt) < len(system_prompt)

        # Should mention creating a plan
        assert "plan" in prompt.lower() or "task" in prompt.lower()


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
        result = await architect.plan(state)

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
