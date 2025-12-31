import pytest

from amelia.core.types import Profile


@pytest.mark.parametrize(
    "name,driver",
    [
        pytest.param("work", "cli:claude", id="work_cli"),
        pytest.param("work", "api:openrouter", id="work_api"),
        pytest.param("home", "api:openrouter", id="home_api"),
        pytest.param("home", "cli:claude", id="home_cli"),
        pytest.param("enterprise", "api:openrouter", id="enterprise_api"),
    ],
)
def test_profile_allows_any_driver_combination(name, driver):
    """
    Any profile name can use any driver type.
    Driver restrictions are not hard-coded; users configure via settings.
    """
    profile = Profile(name=name, driver=driver, model="sonnet", tracker="jira", strategy="single")
    assert profile.name == name
    assert profile.driver == driver
