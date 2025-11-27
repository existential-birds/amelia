from unittest.mock import patch

import pytest

from amelia.core.orchestrator import create_orchestrator_graph
from amelia.core.state import ExecutionState
from amelia.core.state import Profile
from amelia.core.types import Issue


@pytest.mark.skip(reason="Needs actual orchestrator execution with mocked human input.")
@pytest.mark.parametrize("confirm_return,prompt_return,expected_approved", [
    pytest.param(True, "Approved by test", True, id="approved"),
    pytest.param(False, "Rejected by test", False, id="rejected"),
])
async def test_human_approval_gate(confirm_return, prompt_return, expected_approved):
    """
    Parametrized test for human approval gate behavior.
    Tests both approval and rejection scenarios.
    """
    profile = Profile(name="test", driver="cli:claude", tracker="noop", strategy="single")
    test_issue = Issue(
        id=f"HA-{'approved' if expected_approved else 'rejected'}",
        title="Human Approval",
        description="Test approval gate."
    )
    initial_state = ExecutionState(profile=profile, issue=test_issue)

    with patch('typer.confirm', return_value=confirm_return), \
         patch('typer.prompt', return_value=prompt_return):

        app = create_orchestrator_graph()
        final_state = await app.ainvoke(initial_state)

        assert final_state.human_approved is expected_approved
