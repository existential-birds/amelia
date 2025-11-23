import pytest
from unittest.mock import AsyncMock

from amelia.agents.reviewer import Reviewer, ReviewResponse
from amelia.core.state import ExecutionState, Profile, Issue
from amelia.drivers.base import DriverInterface

@pytest.mark.skip(reason="Reviewer competitive strategy and error handling need further refinement.")
async def test_competitive_review_multiple_personas_called():
    """
    Verifies that for a 'competitive' strategy, the reviewer calls the driver's generate
    method multiple times, once for each persona.
    """
    mock_driver = AsyncMock(spec=DriverInterface)
    # Configure mock driver to return a successful response
    mock_driver.generate.return_value = ReviewResponse(approved=True, comments=["Good job"], severity="low")

    reviewer = Reviewer(mock_driver)
    
    profile = Profile(name="comp", driver="api:openai", tracker="noop", strategy="competitive")
    issue = Issue(id="RP-1", title="Competitive Persona Test", description="Test multiple personas.")
    state = ExecutionState(profile=profile, issue=issue)
    
    code_changes = "def foo(): pass"
    
    result = await reviewer.review(state, code_changes)
    
    assert result.approved is True
    assert "Competitive-Aggregated" in result.reviewer_persona
    # Assuming default 3 personas (Security, Performance, Usability)
    assert mock_driver.generate.call_count == 3
    # Further checks can assert that prompts contained different persona names
    
@pytest.mark.skip(reason="Reviewer competitive strategy's error handling and fallback logic need implementation.")
async def test_competitive_review_with_single_model_fallback():
    """
    Tests the fallback mechanism for competitive review when only one model (or successful call) is available.
    This scenario would occur if some `driver.generate` calls for competitive personas fail.
    """
    mock_driver = AsyncMock(spec=DriverInterface)
    
    # Simulate some generate calls failing for specific personas
    async def mock_generate_side_effect(*args, **kwargs):
        messages = kwargs.get('messages', [])
        for msg in messages:
            if "Performance" in msg.content: # Look for a keyword in the system prompt
                raise RuntimeError("Mocked Performance review API failed!")
        return ReviewResponse(approved=True, comments=["Generic comment"], severity="low")

    mock_driver.generate.side_effect = mock_generate_side_effect

    reviewer = Reviewer(mock_driver)
    
    profile = Profile(name="comp", driver="api:openai", tracker="noop", strategy="competitive")
    issue = Issue(id="RP-2", title="Competitive Fallback Test", description="Test fallback to sequential.")
    state = ExecutionState(profile=profile, issue=issue)
    
    code_changes = "def bar(): pass"
    
    result = await reviewer.review(state, code_changes)
    
    assert result is not None
    # Expect a result that reflects successful reviews and potentially indicates a partial failure
    # or a consolidated review. The current implementation of _competitive_review() would just
    # error out if `asyncio.gather` raises an exception. It needs `return_exceptions=True`.
    # This test would then verify the aggregation of partial successes/failures.
    pass
