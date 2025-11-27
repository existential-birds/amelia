import pytest
from langgraph.checkpoint.memory import MemorySaver

from amelia.core.state import ExecutionState
from amelia.core.state import Issue
from amelia.core.state import Profile


@pytest.mark.skip(reason="LangGraph checkpointing is not yet configured in orchestrator.py (T024b)")
def test_orchestrator_state_persistence():
    """
    Verifies that the orchestrator state can be persisted and restored.
    """
    # Setup a mock checkpoint saver
    _checkpoint_saver = MemorySaver()

    # Initial state
    profile = Profile(name="test", driver="cli:claude", tracker="noop", strategy="single")
    test_issue = Issue(id="MEM-1", title="Memory Test", description="Test state persistence.")
    _initial_state = ExecutionState(profile=profile, issue=test_issue)

    # Need to configure the orchestrator to use the checkpoint_saver
    # This will be done in T024b
    
    # Simulate a run and checkpointing
    # Then simulate restoring and verify the state
    pass
