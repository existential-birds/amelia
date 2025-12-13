# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for Architect agent."""

import pytest

from amelia.agents.architect import Architect, ArchitectContextStrategy, TaskListResponse
from amelia.core.state import Task


class TestArchitectContextStrategy:
    """Test ArchitectContextStrategy methods for task generation."""

    @pytest.fixture
    def strategy(self):
        """Create an ArchitectContextStrategy instance for testing."""
        return ArchitectContextStrategy()

    def test_has_task_generation_system_prompt_method(self, strategy):
        """Test that strategy has get_task_generation_system_prompt method."""
        assert hasattr(strategy, "get_task_generation_system_prompt")
        assert callable(strategy.get_task_generation_system_prompt)

    def test_task_generation_system_prompt_is_detailed(self, strategy):
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

    def test_task_generation_system_prompt_mentions_required_fields(self, strategy):
        """Test that task generation prompt specifies required task fields."""
        prompt = strategy.get_task_generation_system_prompt()

        # Should mention key task fields
        assert "id" in prompt.lower()
        assert "description" in prompt.lower()
        assert "steps" in prompt.lower()

    def test_task_generation_system_prompt_is_stable(self, strategy):
        """Test that task generation system prompt is stable across calls."""
        prompt1 = strategy.get_task_generation_system_prompt()
        prompt2 = strategy.get_task_generation_system_prompt()

        assert prompt1 == prompt2

    def test_get_task_generation_user_prompt_method_exists(self, strategy):
        """Test that strategy has get_task_generation_user_prompt method."""
        assert hasattr(strategy, "get_task_generation_user_prompt")
        assert callable(strategy.get_task_generation_user_prompt)

    def test_task_generation_user_prompt_is_concise(self, strategy):
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
    def architect(self, mock_driver):
        """Create an Architect instance for testing."""
        return Architect(driver=mock_driver)

    async def test_generate_task_dag_uses_strategy_system_prompt(
        self, architect, mock_execution_state_factory, mock_issue_factory, mock_driver
    ):
        """Test that _generate_task_dag uses strategy's task generation system prompt."""
        issue = mock_issue_factory(
            id="ARCH-100",
            title="Implement auth",
            description="Build authentication system"
        )
        state = mock_execution_state_factory(issue=issue)

        # Mock driver to return a valid TaskListResponse
        mock_task = Task(
            id="1",
            description="Create auth module",
            dependencies=[],
            files=[],
            steps=[],
            commit_message="feat: add auth module"
        )
        mock_response = TaskListResponse(tasks=[mock_task])
        mock_driver.generate.return_value = mock_response

        # Compile context
        strategy = ArchitectContextStrategy()
        compiled_context = strategy.compile(state)

        # Generate task DAG
        await architect._generate_task_dag(compiled_context, issue, strategy)

        # Verify driver.generate was called
        assert mock_driver.generate.called

        # Get the messages passed to driver
        call_args = mock_driver.generate.call_args
        # Handle both positional and keyword arguments
        if call_args.kwargs.get("messages"):
            messages = call_args.kwargs["messages"]
        elif len(call_args.args) > 0:
            messages = call_args.args[0]
        else:
            # Check if first keyword arg is messages
            messages = list(call_args.kwargs.values())[0] if call_args.kwargs else []

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
        self, architect, mock_execution_state_factory, mock_issue_factory, mock_driver
    ):
        """Test that _generate_task_dag uses strategy's task generation user prompt."""
        issue = mock_issue_factory(
            id="ARCH-100",
            title="Implement auth",
            description="Build authentication system"
        )
        state = mock_execution_state_factory(issue=issue)

        # Mock driver to return a valid TaskListResponse
        mock_task = Task(
            id="1",
            description="Create auth module",
            dependencies=[],
            files=[],
            steps=[],
            commit_message="feat: add auth module"
        )
        mock_response = TaskListResponse(tasks=[mock_task])
        mock_driver.generate.return_value = mock_response

        # Compile context
        strategy = ArchitectContextStrategy()
        compiled_context = strategy.compile(state)

        # Generate task DAG
        await architect._generate_task_dag(compiled_context, issue, strategy)

        # Get the messages passed to driver
        call_args = mock_driver.generate.call_args
        # Handle both positional and keyword arguments
        if call_args.kwargs.get("messages"):
            messages = call_args.kwargs["messages"]
        elif len(call_args.args) > 0:
            messages = call_args.args[0]
        else:
            messages = list(call_args.kwargs.values())[0] if call_args.kwargs else []

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
        self, architect, mock_execution_state_factory, mock_issue_factory, mock_driver, monkeypatch
    ):
        """Test that _generate_task_dag uses strategy's system prompt, not hardcoded text.

        Uses a sentinel value to ensure the prompt genuinely comes from the strategy
        method rather than coincidentally identical hardcoded text.
        """
        issue = mock_issue_factory()
        state = mock_execution_state_factory(issue=issue)

        # Mock driver
        mock_task = Task(
            id="1",
            description="Task 1",
            dependencies=[],
            files=[],
            steps=[],
            commit_message="feat: task 1"
        )
        mock_response = TaskListResponse(tasks=[mock_task])
        mock_driver.generate.return_value = mock_response

        # Create strategy and patch its method to return a unique sentinel
        strategy = ArchitectContextStrategy()
        sentinel_prompt = "SENTINEL_SYSTEM_PROMPT_12345_FOR_TEST_VERIFICATION"
        monkeypatch.setattr(strategy, "get_task_generation_system_prompt", lambda: sentinel_prompt)

        compiled_context = strategy.compile(state)

        # Generate task DAG
        await architect._generate_task_dag(compiled_context, issue, strategy)

        # Verify driver.generate was called
        assert mock_driver.generate.called

        # Get the messages passed to driver (handle both positional and keyword arguments)
        call_args = mock_driver.generate.call_args
        if call_args.kwargs.get("messages"):
            messages = call_args.kwargs["messages"]
        elif len(call_args.args) > 0:
            messages = call_args.args[0]
        else:
            messages = list(call_args.kwargs.values())[0] if call_args.kwargs else []

        system_messages = [msg for msg in messages if msg.role == "system"]
        assert len(system_messages) > 0, f"Should have at least one system message. Got: {messages}"

        # The system message must be our sentinel, proving it came from the strategy
        assert system_messages[0].content == sentinel_prompt, (
            "System prompt must come from strategy.get_task_generation_system_prompt(), "
            "not be hardcoded in _generate_task_dag"
        )

    async def test_plan_reads_design_from_state(
        self, mock_driver, mock_execution_state_factory, mock_issue_factory, mock_design_factory
    ):
        """Test plan() reads design from state, not from parameter."""
        issue = mock_issue_factory(title="Build feature", description="Feature desc")
        design = mock_design_factory(title="Feature Design", goal="Build it well")
        state = mock_execution_state_factory(issue=issue, design=design)

        # Mock driver to return a valid TaskListResponse
        mock_task = Task(
            id="1",
            description="Create feature",
            dependencies=[],
            files=[],
            steps=[],
            commit_message="feat: add feature"
        )
        mock_response = TaskListResponse(tasks=[mock_task])
        mock_driver.generate.return_value = mock_response

        architect = Architect(driver=mock_driver)
        result = await architect.plan(state)

        # Verify plan was generated (driver was called)
        assert result.task_dag is not None
        assert len(result.task_dag.tasks) == 1
        assert result.markdown_path is not None

        # Verify design from state was actually used in driver call
        mock_driver.generate.assert_called_once()
        call_args = mock_driver.generate.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]

        # Concatenate all message content to check for design fields
        all_content = " ".join(msg.content for msg in messages if msg.content)
        assert "Build it well" in all_content, (
            "Design goal from state.design must appear in messages passed to driver"
        )
