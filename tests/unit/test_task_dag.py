import pytest
from pydantic import ValidationError

from amelia.core.state import Task
from amelia.core.state import TaskDAG


def test_task_dag_creation():
    task1 = Task(id="1", description="Task 1")
    task2 = Task(id="2", description="Task 2")
    dag = TaskDAG(tasks=[task1, task2], original_issue="ISSUE-123")
    assert len(dag.tasks) == 2
    assert dag.original_issue == "ISSUE-123"

def test_task_dag_with_dependencies():
    task1 = Task(id="1", description="Task 1")
    task2 = Task(id="2", description="Task 2", dependencies=["1"])
    task3 = Task(id="3", description="Task 3", dependencies=["1", "2"])
    _dag = TaskDAG(tasks=[task1, task2, task3], original_issue="ISSUE-124")
    assert task3.dependencies == ["1", "2"]

@pytest.mark.skip(reason="Cycle detection logic for TaskDAG is not yet implemented")
def test_task_dag_cycle_detection():
    # Example of a cyclic dependency
    task_a = Task(id="A", description="Task A", dependencies=["C"])
    task_b = Task(id="B", description="Task B", dependencies=["A"])
    task_c = Task(id="C", description="Task C", dependencies=["B"])

    with pytest.raises(ValidationError, match="Cyclic dependency detected"):
        TaskDAG(tasks=[task_a, task_b, task_c], original_issue="ISSUE-CYCLE")

@pytest.mark.skip(reason="Dependency resolution logic for TaskDAG is not yet implemented")
def test_task_dag_dependency_resolution():
    task1 = Task(id="1", description="Task 1")
    task2 = Task(id="2", description="Task 2", dependencies=["1"])
    task3 = Task(id="3", description="Task 3", dependencies=["1", "2"])
    _dag = TaskDAG(tasks=[task1, task2, task3], original_issue="ISSUE-125")

    # Assuming a method like `dag.get_ready_tasks()` or similar
    # ready_tasks = dag.get_ready_tasks()
    # assert set(t.id for t in ready_tasks) == {"1"}
    pass

@pytest.mark.skip(reason="Invalid graph handling for TaskDAG is not yet implemented")
def test_task_dag_invalid_graph_handling():
    # Task with a dependency that does not exist in the DAG
    task1 = Task(id="1", description="Task 1", dependencies=["non-existent"])
    with pytest.raises(ValidationError, match="Task 'non-existent' not found"):
        TaskDAG(tasks=[task1], original_issue="ISSUE-INVALID")
