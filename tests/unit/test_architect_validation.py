"""Tests for Architect agent validation error handling."""


import pytest

from amelia.agents.architect import Architect
from amelia.agents.architect import TaskListResponse
from amelia.core.state import Task


class TestArchitectTaskDAGValidation:
    """Tests for handling invalid TaskDAG generation."""

    @pytest.mark.asyncio
    async def test_handles_cyclic_dependency_from_llm(
        self, mock_issue_factory, mock_async_driver_factory
    ):
        """
        When LLM generates tasks with cyclic dependencies,
        Architect should raise ValueError with clear context.
        """
        # Create tasks with a cycle: 1 -> 2 -> 1
        cyclic_tasks = [
            Task(id="1", description="Task 1", dependencies=["2"]),
            Task(id="2", description="Task 2", dependencies=["1"]),
        ]
        mock_response = TaskListResponse(tasks=cyclic_tasks)

        mock_driver = mock_async_driver_factory(generate_return=mock_response)
        architect = Architect(mock_driver)
        issue = mock_issue_factory()

        with pytest.raises(ValueError) as exc_info:
            await architect.plan(issue)

        assert "cyclic" in str(exc_info.value).lower() or "cycle" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_handles_missing_dependency_from_llm(
        self, mock_issue_factory, mock_async_driver_factory
    ):
        """
        When LLM generates tasks referencing non-existent dependencies,
        Architect should raise ValueError with clear context.
        """
        # Task 1 depends on non-existent task "99"
        invalid_tasks = [
            Task(id="1", description="Task 1", dependencies=["99"]),
        ]
        mock_response = TaskListResponse(tasks=invalid_tasks)

        mock_driver = mock_async_driver_factory(generate_return=mock_response)
        architect = Architect(mock_driver)
        issue = mock_issue_factory()

        with pytest.raises(ValueError) as exc_info:
            await architect.plan(issue)

        assert "99" in str(exc_info.value) or "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_valid_tasks_succeed(
        self, mock_issue_factory, mock_async_driver_factory, tmp_path
    ):
        """Valid task generation should succeed without errors."""
        valid_tasks = [
            Task(id="1", description="Task 1", dependencies=[]),
            Task(id="2", description="Task 2", dependencies=["1"]),
        ]
        mock_response = TaskListResponse(tasks=valid_tasks)

        mock_driver = mock_async_driver_factory(generate_return=mock_response)
        architect = Architect(mock_driver)
        issue = mock_issue_factory()

        result = await architect.plan(issue, output_dir=str(tmp_path))

        assert result.task_dag is not None
        assert len(result.task_dag.tasks) == 2
