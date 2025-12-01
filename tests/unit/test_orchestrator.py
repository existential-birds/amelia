"""Tests for orchestrator developer node."""

from unittest.mock import AsyncMock, patch

import pytest

from amelia.core.orchestrator import call_developer_node
from amelia.core.state import ExecutionState, Task, TaskDAG
from amelia.core.types import Profile


@pytest.fixture
def agentic_profile():
    return Profile(name="test", driver="cli:claude", execution_mode="agentic", working_dir="/test/dir")


@pytest.fixture
def structured_profile():
    return Profile(name="test", driver="cli:claude", execution_mode="structured")


class TestDeveloperNodeAgenticMode:
    """Tests for developer node with agentic execution."""

    @pytest.mark.asyncio
    async def test_developer_node_passes_execution_mode(
        self, mock_issue_factory, agentic_profile, mock_task_factory
    ):
        """Developer node should pass execution_mode from profile to Developer."""
        task = mock_task_factory(id="1", description="Test task", status="pending")
        plan = TaskDAG(tasks=[task], original_issue="TEST-1")
        state = ExecutionState(
            profile=agentic_profile,
            issue=mock_issue_factory(),
            plan=plan,
            human_approved=True
        )

        with patch("amelia.core.orchestrator.DriverFactory") as mock_factory, \
             patch("amelia.core.orchestrator.Developer") as mock_developer_class:
            mock_driver = AsyncMock()
            mock_factory.get_driver.return_value = mock_driver

            mock_developer = AsyncMock()
            mock_developer.execute_task.return_value = {"status": "completed", "output": "done"}
            mock_developer_class.return_value = mock_developer

            await call_developer_node(state)

            mock_developer_class.assert_called_once_with(mock_driver, execution_mode="agentic")

    @pytest.mark.asyncio
    async def test_developer_node_passes_cwd_to_execute_task(
        self, mock_issue_factory, agentic_profile, mock_task_factory
    ):
        """Developer node should pass cwd from profile.working_dir to execute_task."""
        task = mock_task_factory(id="1", description="Test task", status="pending")
        plan = TaskDAG(tasks=[task], original_issue="TEST-1")
        state = ExecutionState(
            profile=agentic_profile,
            issue=mock_issue_factory(),
            plan=plan,
            human_approved=True
        )

        with patch("amelia.core.orchestrator.DriverFactory") as mock_factory, \
             patch("amelia.core.orchestrator.Developer") as mock_developer_class:
            mock_driver = AsyncMock()
            mock_factory.get_driver.return_value = mock_driver

            mock_developer = AsyncMock()
            mock_developer.execute_task.return_value = {"status": "completed", "output": "done"}
            mock_developer_class.return_value = mock_developer

            await call_developer_node(state)

            # Verify execute_task was called with cwd="/test/dir"
            mock_developer.execute_task.assert_called_once()
            call_kwargs = mock_developer.execute_task.call_args
            assert call_kwargs[1].get("cwd") == "/test/dir"

    @pytest.mark.asyncio
    async def test_developer_node_structured_mode(
        self, mock_issue_factory, structured_profile, mock_task_factory
    ):
        """Developer node should pass execution_mode='structured' from profile."""
        task = mock_task_factory(id="1", description="Test task", status="pending")
        plan = TaskDAG(tasks=[task], original_issue="TEST-1")
        state = ExecutionState(
            profile=structured_profile,
            issue=mock_issue_factory(),
            plan=plan,
            human_approved=True
        )

        with patch("amelia.core.orchestrator.DriverFactory") as mock_factory, \
             patch("amelia.core.orchestrator.Developer") as mock_developer_class:
            mock_driver = AsyncMock()
            mock_factory.get_driver.return_value = mock_driver

            mock_developer = AsyncMock()
            mock_developer.execute_task.return_value = {"status": "completed", "output": "done"}
            mock_developer_class.return_value = mock_developer

            await call_developer_node(state)

            mock_developer_class.assert_called_once_with(mock_driver, execution_mode="structured")
