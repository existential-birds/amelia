# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
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
    profile = Profile(name=name, driver=driver, tracker="jira", strategy="single")
    assert profile.name == name
    assert profile.driver == driver
