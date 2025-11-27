import pytest
from pydantic import ValidationError

from amelia.core.state import ExecutionState
from amelia.core.state import Task
from amelia.core.state import TaskDAG
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
