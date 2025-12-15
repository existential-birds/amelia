# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for Developer agent execution and error handling."""

from unittest.mock import AsyncMock

import pytest

from amelia.agents.developer import Developer
from amelia.core.exceptions import AgenticExecutionError
from amelia.core.state import TaskDAG
from amelia.drivers.base import DriverInterface
from amelia.drivers.cli.claude import ClaudeStreamEvent


class TestDeveloperExecution:
    """Tests for Developer.execute_current_task() structured mode behavior."""

    async def test_execute_shell_command_calls_driver(self, developer_test_context):
        """Developer should call execute_tool for shell commands."""
        mock_driver, state = developer_test_context(
            task_desc="Run shell command: echo hello",
            driver_return="Command output"
        )
        developer = Developer(driver=mock_driver)

        result = await developer.execute_current_task(state, workflow_id="test-workflow")

        assert result["status"] == "completed"
        mock_driver.execute_tool.assert_called_once_with("run_shell_command", command="echo hello")

    async def test_execute_write_file_calls_driver(self, developer_test_context):
        """Developer should call execute_tool for write file tasks."""
        mock_driver, state = developer_test_context(
            task_desc="write file: test.py with print('hi')",
            driver_return="File created"
        )
        developer = Developer(driver=mock_driver)

        await developer.execute_current_task(state, workflow_id="test-workflow")

        mock_driver.execute_tool.assert_called_once()

    async def test_exception_returns_failed_status(self, developer_test_context):
        """Developer should return failed status on exception."""
        mock_driver, state = developer_test_context(
            task_desc="Run shell command: /bin/false",
            driver_side_effect=RuntimeError(
                "Mocked command failed: /bin/false returned non-zero exit code."
            )
        )
        developer = Developer(driver=mock_driver)

        result = await developer.execute_current_task(state, workflow_id="test-workflow")

        assert result["status"] == "failed"
        assert "Mocked command failed" in result["output"]

    async def test_propagates_error_output(self, developer_test_context):
        """Developer should propagate error messages in output."""
        mock_driver, state = developer_test_context(
            task_desc="Run shell command: python broken.py",
            driver_return="Command failed with exit code 1. Stderr: syntax error near line 5"
        )
        developer = Developer(driver=mock_driver)

        result = await developer.execute_current_task(state, workflow_id="test-workflow")

        assert "failed" in result["output"].lower() or "error" in result["output"].lower()

    async def test_fallback_uses_generate(self, developer_test_context):
        """Developer should use generate() for unstructured tasks."""
        mock_driver, state = developer_test_context(
            task_desc="Implement the foo feature"
        )
        mock_driver.generate.return_value = "Generated response"
        developer = Developer(driver=mock_driver)

        result = await developer.execute_current_task(state, workflow_id="test-workflow")

        assert result["status"] == "completed"
        mock_driver.generate.assert_called_once()

    async def test_fallback_uses_context_strategy(self, developer_test_context):
        """Developer should use DeveloperContextStrategy for structured fallback."""
        from amelia.agents.developer import DeveloperContextStrategy

        mock_driver, state = developer_test_context(
            task_desc="Implement the foo feature"
        )
        mock_driver.generate.return_value = "Generated response"
        developer = Developer(driver=mock_driver)

        result = await developer.execute_current_task(state, workflow_id="test-workflow")

        assert result["status"] == "completed"
        # Verify generate was called with messages from the strategy
        mock_driver.generate.assert_called_once()
        call_args = mock_driver.generate.call_args
        messages = call_args.kwargs["messages"]

        # Should have system message from DeveloperContextStrategy
        assert len(messages) >= 1
        assert messages[0].role == "system"
        assert messages[0].content == DeveloperContextStrategy.SYSTEM_PROMPT

        # Should have user message with task content
        task_desc = "Implement the foo feature"
        assert any(msg.role == "user" and task_desc in msg.content for msg in messages)


class TestDeveloperAgenticExecution:
    """Tests for Developer agentic execution mode."""

    async def test_execute_current_task_agentic_calls_execute_agentic(
        self, mock_task_factory, mock_execution_state_factory, mock_profile_factory
    ):
        """Developer in agentic mode should call driver.execute_agentic with messages."""
        mock_driver = AsyncMock(spec=DriverInterface)

        async def mock_execute_agentic(messages, cwd, session_id=None, system_prompt=None):
            # Verify that messages is a list of AgentMessage
            assert isinstance(messages, list)
            assert all(hasattr(msg, 'role') and hasattr(msg, 'content') for msg in messages)
            yield ClaudeStreamEvent(type="assistant", content="Working...")
            yield ClaudeStreamEvent(type="result", session_id="sess_001")

        mock_driver.execute_agentic = mock_execute_agentic

        task = mock_task_factory(id="1", description="Implement feature")
        # Use api:openai profile for agentic mode
        profile = mock_profile_factory(preset="api_single")
        profile = profile.model_copy(update={"working_dir": "/tmp"})
        state = mock_execution_state_factory(
            profile=profile,
            plan=TaskDAG(tasks=[task], original_issue="Test"),
            current_task_id=task.id,
        )
        developer = Developer(driver=mock_driver, execution_mode="agentic")

        result = await developer.execute_current_task(state, workflow_id="test-workflow")

        assert result["status"] == "completed"

    async def test_execute_current_task_agentic_passes_system_prompt(
        self, mock_task_factory, mock_execution_state_factory, mock_profile_factory
    ):
        """Developer in agentic mode should pass system_prompt to driver.execute_agentic."""
        from amelia.agents.developer import DeveloperContextStrategy

        mock_driver = AsyncMock(spec=DriverInterface)
        captured_system_prompt = None
        captured_messages = None

        async def mock_execute_agentic(messages, cwd, session_id=None, system_prompt=None):
            nonlocal captured_system_prompt, captured_messages
            captured_system_prompt = system_prompt
            captured_messages = messages
            yield ClaudeStreamEvent(type="assistant", content="Working...")
            yield ClaudeStreamEvent(type="result", session_id="sess_001")

        mock_driver.execute_agentic = mock_execute_agentic

        task = mock_task_factory(id="1", description="Implement feature")
        profile = mock_profile_factory(preset="api_single")
        profile = profile.model_copy(update={"working_dir": "/tmp"})
        state = mock_execution_state_factory(
            profile=profile,
            plan=TaskDAG(tasks=[task], original_issue="Test"),
            current_task_id=task.id,
        )
        developer = Developer(driver=mock_driver, execution_mode="agentic")

        result = await developer.execute_current_task(state, workflow_id="test-workflow")

        # Verify the system prompt was passed to execute_agentic
        assert result["status"] == "completed"
        assert captured_system_prompt is not None
        assert captured_system_prompt == DeveloperContextStrategy.SYSTEM_PROMPT
        assert "TDD principles" in captured_system_prompt
        assert "senior developer" in captured_system_prompt
        # Verify messages were passed as list
        assert isinstance(captured_messages, list)

    async def test_execute_current_task_agentic_raises_on_error(
        self, mock_task_factory, mock_execution_state_factory, mock_profile_factory
    ):
        """Developer in agentic mode should raise AgenticExecutionError on error event."""
        mock_driver = AsyncMock(spec=DriverInterface)

        async def mock_execute_agentic(messages, cwd, session_id=None, system_prompt=None):
            yield ClaudeStreamEvent(type="error", content="Something went wrong")

        mock_driver.execute_agentic = mock_execute_agentic

        task = mock_task_factory(id="1", description="Implement feature")
        profile = mock_profile_factory(preset="api_single")
        profile = profile.model_copy(update={"working_dir": "/tmp"})
        state = mock_execution_state_factory(
            profile=profile,
            plan=TaskDAG(tasks=[task], original_issue="Test"),
            current_task_id=task.id,
        )
        developer = Developer(driver=mock_driver, execution_mode="agentic")

        with pytest.raises(AgenticExecutionError) as exc_info:
            await developer.execute_current_task(state, workflow_id="test-workflow")

        assert "Something went wrong" in str(exc_info.value)

    async def test_execute_current_task_structured_works(self, developer_test_context):
        """Developer in structured mode should work correctly."""
        mock_driver, state = developer_test_context(
            task_desc="Implement feature"
        )
        mock_driver.generate.return_value = "Generated response"
        developer = Developer(driver=mock_driver, execution_mode="structured")

        result = await developer.execute_current_task(state, workflow_id="test-workflow")

        assert result["status"] == "completed"
        mock_driver.generate.assert_called_once()


class TestDeveloperValidation:
    """Tests for execute_current_task validation."""

    async def test_raises_when_no_plan(self, mock_execution_state_factory):
        """execute_current_task should raise ValueError when plan is None."""
        mock_driver = AsyncMock(spec=DriverInterface)
        state = mock_execution_state_factory(plan=None, current_task_id="1")
        developer = Developer(driver=mock_driver)

        with pytest.raises(ValueError, match="State must have plan and current_task_id"):
            await developer.execute_current_task(state, workflow_id="test-workflow")

    async def test_raises_when_no_current_task_id(
        self, mock_task_factory, mock_execution_state_factory
    ):
        """execute_current_task should raise ValueError when current_task_id is None."""
        mock_driver = AsyncMock(spec=DriverInterface)
        task = mock_task_factory(id="1", description="Test task")
        state = mock_execution_state_factory(
            plan=TaskDAG(tasks=[task], original_issue="Test"),
            current_task_id=None,
        )
        developer = Developer(driver=mock_driver)

        with pytest.raises(ValueError, match="State must have plan and current_task_id"):
            await developer.execute_current_task(state, workflow_id="test-workflow")

    async def test_raises_when_task_not_found(
        self, mock_task_factory, mock_execution_state_factory
    ):
        """execute_current_task should raise ValueError when task ID not in plan."""
        mock_driver = AsyncMock(spec=DriverInterface)
        task = mock_task_factory(id="1", description="Test task")
        state = mock_execution_state_factory(
            plan=TaskDAG(tasks=[task], original_issue="Test"),
            current_task_id="nonexistent",
        )
        developer = Developer(driver=mock_driver)

        with pytest.raises(ValueError, match="Task not found: nonexistent"):
            await developer.execute_current_task(state, workflow_id="test-workflow")
