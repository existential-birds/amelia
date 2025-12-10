# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for orchestrator developer node."""

from collections.abc import Callable
from typing import Literal
from unittest.mock import AsyncMock, patch

import pytest

from amelia.core.orchestrator import call_developer_node
from amelia.core.state import ExecutionState, Task, TaskDAG
from amelia.core.types import Issue, Profile


class TestDeveloperNode:
    """Tests for developer node."""

    @pytest.mark.parametrize(
        "execution_mode,working_dir",
        [
            ("agentic", "/test/dir"),
            ("structured", None),
        ],
    )
    async def test_developer_node_passes_execution_mode(
        self,
        mock_issue_factory: Callable[..., Issue],
        mock_task_factory: Callable[..., Task],
        execution_mode: Literal["structured", "agentic"],
        working_dir: str | None,
    ) -> None:
        """Developer node should pass execution_mode from profile to Developer."""
        profile = Profile(
            name="test",
            driver="cli:claude",
            execution_mode=execution_mode,
            working_dir=working_dir
        )
        task = mock_task_factory(id="1", description="Test task", status="pending")
        plan = TaskDAG(tasks=[task], original_issue="TEST-1")
        state = ExecutionState(
            profile=profile,
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

            mock_developer_class.assert_called_once_with(mock_driver, execution_mode=execution_mode)

    async def test_developer_node_passes_cwd_to_execute_task(
        self,
        mock_issue_factory: Callable[..., Issue],
        mock_task_factory: Callable[..., Task],
    ) -> None:
        """Developer node should pass cwd from profile.working_dir to execute_task."""
        profile = Profile(
            name="test",
            driver="cli:claude",
            execution_mode="agentic",
            working_dir="/test/dir"
        )
        task = mock_task_factory(id="1", description="Test task", status="pending")
        plan = TaskDAG(tasks=[task], original_issue="TEST-1")
        state = ExecutionState(
            profile=profile,
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
