import pytest


@pytest.mark.skip(reason="Architect agent not yet implemented")
def test_architect_generates_plan():
    """
    Test that the Architect agent can generate a valid plan (TaskDAG) from an issue.
    """
    pass

@pytest.mark.skip(reason="Developer agent not yet implemented")
def test_developer_executes_task():
    """
    Test that the Developer agent can execute a given task.
    """
    pass
