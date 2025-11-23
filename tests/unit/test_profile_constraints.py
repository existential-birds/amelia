import pytest
from amelia.core.types import Profile
# from amelia.config import validate_constraints

@pytest.mark.skip(reason="Constraint validation logic TBD in T065")
def test_work_profile_cli_constraint():
    """
    Ensure that a profile designated as 'work' cannot use API drivers.
    """
    _work_profile = Profile(name="work", driver="api:openai")
    
    # Expected behavior:
    # validate_constraints(work_profile) -> raises ValueError
    pass
