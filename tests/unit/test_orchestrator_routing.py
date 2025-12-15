# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for orchestrator routing functions."""

import pytest

from amelia.core.orchestrator import route_after_developer
from amelia.core.types import DeveloperStatus


class TestRouteAfterDeveloper:
    """Tests for route_after_developer routing function."""

    @pytest.mark.parametrize(
        "status,expected_route",
        [
            (DeveloperStatus.ALL_DONE, "reviewer"),
            (DeveloperStatus.BATCH_COMPLETE, "batch_approval"),
            (DeveloperStatus.BLOCKED, "blocker_resolution"),
            (DeveloperStatus.EXECUTING, "developer"),
        ],
        ids=[
            "all_done_to_reviewer",
            "batch_complete_to_batch_approval",
            "blocked_to_blocker_resolution",
            "executing_to_developer",
        ],
    )
    def test_route_after_developer_parametrized(
        self,
        status: DeveloperStatus,
        expected_route: str,
        mock_execution_state_factory,
    ):
        """Parametrized test covering all developer status routing scenarios."""
        state = mock_execution_state_factory(developer_status=status)

        result = route_after_developer(state)

        assert result == expected_route, (
            f"route_after_developer should return '{expected_route}' when "
            f"developer_status is {status.value}"
        )
