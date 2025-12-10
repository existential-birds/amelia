# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import pytest
from pydantic import ValidationError

from amelia.core.state import TaskDAG


class TestTaskDAG:
    """Tests for TaskDAG dependency resolution and validation."""

    def test_get_ready_tasks_returns_tasks_with_completed_deps(
        self, mock_task_factory, mock_task_dag_factory
    ):
        """Tasks with all dependencies completed should be ready."""
        task_a = mock_task_factory(id="A", status="completed", dependencies=[])
        task_b = mock_task_factory(id="B", status="pending", dependencies=["A"])
        dag = mock_task_dag_factory(tasks=[task_a, task_b])

        ready = dag.get_ready_tasks()

        assert len(ready) == 1
        assert ready[0].id == "B"

    def test_dependency_resolution_chain(self, mock_task_factory):
        """Test progressive dependency resolution through a chain."""
        task1 = mock_task_factory(id="1")
        task2 = mock_task_factory(id="2", dependencies=["1"])
        task3 = mock_task_factory(id="3", dependencies=["1", "2"])
        dag = TaskDAG(tasks=[task1, task2, task3], original_issue="ISSUE-125")

        ready_tasks = dag.get_ready_tasks()
        assert {t.id for t in ready_tasks} == {"1"}

        task1.status = "completed"
        ready_tasks = dag.get_ready_tasks()
        assert {t.id for t in ready_tasks} == {"2"}

        task2.status = "completed"
        ready_tasks = dag.get_ready_tasks()
        assert {t.id for t in ready_tasks} == {"3"}

    @pytest.mark.parametrize(
        "task_configs,expected_error",
        [
            # Cyclic dependency
            (
                [("A", ["C"]), ("B", ["A"]), ("C", ["B"])],
                "Cyclic dependency",
            ),
            # Missing dependency
            (
                [("1", ["non-existent"])],
                "not found",
            ),
        ],
        ids=["cyclic_dependency", "missing_dependency"],
    )
    def test_task_dag_validation_errors(
        self, task_configs, expected_error, mock_task_factory
    ):
        """TaskDAG should reject invalid dependency graphs."""
        tasks = [
            mock_task_factory(id=tid, dependencies=deps)
            for tid, deps in task_configs
        ]

        with pytest.raises(ValidationError, match=expected_error):
            TaskDAG(tasks=tasks, original_issue="TEST-1")
