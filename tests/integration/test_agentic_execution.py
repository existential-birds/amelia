# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Integration tests for agentic execution mode."""

from unittest.mock import AsyncMock, patch

import pytest

from amelia.core.orchestrator import call_developer_node
from amelia.core.state import ExecutionState, FileOperation, Task, TaskDAG, TaskStep
from amelia.core.types import Issue, Profile
from amelia.drivers.cli.claude import ClaudeStreamEvent


@pytest.fixture
def agentic_state():
    """Create execution state with agentic profile."""
    profile = Profile(
        name="test",
        driver="cli:claude",
        execution_mode="agentic",
        working_dir="/tmp/test"
    )
    issue = Issue(id="TEST-1", title="Test", description="Test issue")
    task = Task(
        id="1",
        description="Implement feature",
        files=[FileOperation(operation="create", path="test.py")],
        steps=[TaskStep(description="Write test", code="def test(): pass")]
    )
    plan = TaskDAG(tasks=[task], original_issue="TEST-1")

    return ExecutionState(
        profile=profile,
        issue=issue,
        plan=plan,
        human_approved=True
    )


class TestAgenticExecution:
    """Integration tests for agentic execution."""

    async def test_agentic_profile_triggers_agentic_execution(self, agentic_state):
        """Agentic profile should use execute_agentic method."""

        async def mock_execute_agentic(prompt, cwd, session_id=None, system_prompt=None):
            yield ClaudeStreamEvent(type="assistant", content="Working...")
            yield ClaudeStreamEvent(type="result", session_id="sess_001")

        with patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_driver = AsyncMock()
            mock_driver.execute_agentic = mock_execute_agentic
            mock_factory.get_driver.return_value = mock_driver

            config = {"configurable": {"thread_id": "test-workflow-1"}}
            result_dict = await call_developer_node(agentic_state, config)

            # Nodes now return partial state dicts, not full ExecutionState
            assert result_dict["plan"].tasks[0].status == "completed"

    async def test_agentic_execution_passes_working_dir(self, agentic_state):
        """Agentic execution should pass working_dir from profile to execute_agentic."""
        captured_cwd = None

        async def mock_execute_agentic(prompt, cwd, session_id=None, system_prompt=None):
            nonlocal captured_cwd
            captured_cwd = cwd
            yield ClaudeStreamEvent(type="result", session_id="sess_001")

        with patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_driver = AsyncMock()
            mock_driver.execute_agentic = mock_execute_agentic
            mock_factory.get_driver.return_value = mock_driver

            config = {"configurable": {"thread_id": "test-workflow-2"}}
            await call_developer_node(agentic_state, config)

            assert captured_cwd == "/tmp/test"

    async def test_structured_profile_does_not_use_agentic(self):
        """Structured profile should use execute_current_task, not execute_agentic directly."""
        profile = Profile(
            name="test",
            driver="cli:claude",
            execution_mode="structured"
        )
        issue = Issue(id="TEST-2", title="Test", description="Test issue")
        task = Task(id="1", description="Test task")
        plan = TaskDAG(tasks=[task], original_issue="TEST-2")
        state = ExecutionState(
            profile=profile,
            issue=issue,
            plan=plan,
            human_approved=True
        )

        with patch("amelia.core.orchestrator.DriverFactory") as mock_factory, \
             patch("amelia.core.orchestrator.Developer") as mock_developer_class:
            mock_driver = AsyncMock()
            mock_factory.get_driver.return_value = mock_driver

            mock_developer = AsyncMock()
            mock_developer.execute_current_task.return_value = {"status": "completed", "output": "done"}
            mock_developer_class.return_value = mock_developer

            config = {"configurable": {"thread_id": "test-workflow-3"}}
            await call_developer_node(state, config)

            # Developer should be initialized with structured mode
            mock_developer_class.assert_called_once_with(
                mock_driver,
                execution_mode="structured",
                stream_emitter=None,
            )
            # execute_current_task should be called
            mock_developer.execute_current_task.assert_called_once()
