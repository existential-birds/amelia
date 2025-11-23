import pytest
from unittest.mock import patch

from amelia.core.orchestrator import create_orchestrator_graph
from amelia.core.state import ExecutionState, Profile
from amelia.core.types import Issue

@pytest.mark.skip(reason="Needs actual orchestrator execution with mocked human input.")
async def test_human_approval_gate_approved():
    """
    Test that the orchestrator proceeds when human approval is given.
    """
    profile = Profile(name="test", driver="cli:claude", tracker="noop", strategy="single")
    test_issue = Issue(id="HA-1", title="Human Approval", description="Test approval gate.")
    initial_state = ExecutionState(profile=profile, issue=test_issue)

    # Mock typer.confirm to return True (approved)
    with patch('typer.confirm', return_value=True), \
         patch('typer.prompt', return_value="Approved by test"):
        
        app = create_orchestrator_graph()
        # Simulate architect call to set the plan, then run the approval node
        # This will be more robust when the full graph execution can be mocked.
        # For now, just ensure the approval node does not immediately end.
        final_state = await app.ainvoke(initial_state)
        
        # Assert that the human_approved flag is set to True
        assert final_state.human_approved is True
        # Further assertions will check if execution proceeded past the gate
        pass

@pytest.mark.skip(reason="Needs actual orchestrator execution with mocked human input.")
async def test_human_approval_gate_rejected():
    """
    Test that the orchestrator halts when human approval is rejected.
    """
    profile = Profile(name="test", driver="cli:claude", tracker="noop", strategy="single")
    test_issue = Issue(id="HA-2", title="Human Approval", description="Test rejection gate.")
    initial_state = ExecutionState(profile=profile, issue=test_issue)

    # Mock typer.confirm to return False (rejected)
    with patch('typer.confirm', return_value=False), \
         patch('typer.prompt', return_value="Rejected by test"):
        
        app = create_orchestrator_graph()
        # Similar to above, verify that the graph ends or transitions to a "rejected" state
        final_state = await app.ainvoke(initial_state)
        
        # Assert that the human_approved flag is set to False
        assert final_state.human_approved is False
        # Further assertions will check if execution ended
        pass
