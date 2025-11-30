import pytest
from pydantic import ValidationError

from amelia.core.types import Profile


@pytest.mark.parametrize(
    "name,driver,should_raise",
    [
        pytest.param("work", "cli:claude", False, id="work_cli_valid"),
        pytest.param("work", "api:openai", True, id="work_api_invalid"),
        pytest.param("home", "api:openai", False, id="home_api_valid"),
        pytest.param("home", "cli:claude", False, id="home_cli_valid"),
    ],
)
def test_profile_driver_constraints(name, driver, should_raise):
    """
    Ensure that 'work' profile cannot use API drivers (enterprise compliance).
    Other profiles can use any driver.
    """
    if should_raise:
        with pytest.raises(ValidationError, match="work.*cannot use.*api"):
            Profile(name=name, driver=driver, tracker="jira", strategy="single")
    else:
        profile = Profile(name=name, driver=driver, tracker="jira", strategy="single")
        assert profile.driver == driver
