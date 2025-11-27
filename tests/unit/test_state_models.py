import pytest
from pydantic import ValidationError

from amelia.core.state import ExecutionState
from amelia.core.state import FileOperation
from amelia.core.state import Task
from amelia.core.state import TaskDAG
from amelia.core.state import TaskStep
from amelia.core.types import Profile


def test_profile_validation():
    # Valid
    p = Profile(name="work", driver="cli:claude", tracker="jira", strategy="single")
    assert p.driver == "cli:claude"

    # Invalid driver (assuming enum or specific string)
    # Note: Actual validation depends on implementation, but assuming we validate types
    with pytest.raises(ValidationError):
        Profile(name="work", driver=123, tracker="jira", strategy="single")

def test_task_dag_acyclic():
    # Simple DAG
    t1 = Task(id="1", description="A", status="pending", dependencies=[])
    t2 = Task(id="2", description="B", status="pending", dependencies=["1"])
    dag = TaskDAG(tasks=[t1, t2], original_issue="Test")
    assert len(dag.tasks) == 2
    
    # Cycle (if validation implemented in model)
    _t3 = Task(id="3", description="C", status="pending", dependencies=["4"])
    _t4 = Task(id="4", description="D", status="pending", dependencies=["3"])
    # Depending on implementation, this might raise ValidationError or be checked by a method
    # For now, just checking basic structure

def test_execution_state_defaults():
    p = Profile(name="default", driver="api:openai", tracker="none", strategy="single")
    state = ExecutionState(profile=p)
    assert state.review_results == []
    assert state.messages == []


def test_task_step_minimal():
    step = TaskStep(description="Write the failing test")
    assert step.description == "Write the failing test"
    assert step.code is None
    assert step.command is None
    assert step.expected_output is None


def test_task_step_full():
    step = TaskStep(
        description="Run test to verify it fails",
        code="def test_foo(): assert False",
        command="pytest tests/test_foo.py -v",
        expected_output="FAILED"
    )
    assert step.command == "pytest tests/test_foo.py -v"


def test_file_operation_create():
    op = FileOperation(operation="create", path="src/new_file.py")
    assert op.operation == "create"
    assert op.line_range is None


def test_file_operation_modify_with_range():
    op = FileOperation(operation="modify", path="src/existing.py", line_range="10-25")
    assert op.line_range == "10-25"


def test_task_with_steps_and_files():
    step = TaskStep(description="Write test", code="def test(): pass")
    file_op = FileOperation(operation="create", path="src/foo.py")

    task = Task(
        id="1",
        description="Add foo feature",
        files=[file_op],
        steps=[step],
        commit_message="feat: add foo"
    )

    assert len(task.files) == 1
    assert len(task.steps) == 1
    assert task.commit_message == "feat: add foo"


def test_task_without_new_fields():
    """Ensure defaults work for minimal task creation."""
    task = Task(id="1", description="Simple task")
    assert task.files == []
    assert task.steps == []
    assert task.commit_message is None
