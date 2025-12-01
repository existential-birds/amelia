import pytest
from pydantic import ValidationError

from amelia.core.state import ExecutionState
from amelia.core.state import FileOperation
from amelia.core.state import Task
from amelia.core.state import TaskDAG
from amelia.core.state import TaskStep
from amelia.core.types import Design
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


def test_design_minimal():
    design = Design(
        title="Auth Feature",
        goal="Add user authentication",
        architecture="JWT-based auth with middleware",
        tech_stack=["FastAPI", "PyJWT"],
        components=["AuthMiddleware", "TokenService"],
        raw_content="# Auth Feature Design\n..."
    )
    assert design.title == "Auth Feature"
    assert design.data_flow is None
    assert design.relevant_files == []


def test_design_full():
    design = Design(
        title="Auth Feature",
        goal="Add user authentication",
        architecture="JWT-based auth",
        tech_stack=["FastAPI"],
        components=["AuthMiddleware"],
        data_flow="Request -> Middleware -> Handler",
        error_handling="Return 401 on invalid token",
        testing_strategy="Unit test token validation",
        relevant_files=["src/auth.py", "src/middleware.py"],
        conventions="Use async/await throughout",
        raw_content="# Full design..."
    )
    assert design.data_flow == "Request -> Middleware -> Handler"
    assert len(design.relevant_files) == 2


def test_profile_plan_output_dir_default():
    from amelia.core.types import Profile

    profile = Profile(name="test", driver="api:openai")
    assert profile.plan_output_dir == "docs/plans"


def test_profile_plan_output_dir_custom():
    from amelia.core.types import Profile

    profile = Profile(name="test", driver="api:openai", plan_output_dir="output/my-plans")
    assert profile.plan_output_dir == "output/my-plans"


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
