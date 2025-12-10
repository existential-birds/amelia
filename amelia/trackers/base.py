# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from typing import Protocol

from amelia.core.types import Issue


class BaseTracker(Protocol):
    """Protocol interface for issue tracking system integrations.

    Implementations must provide issue fetching capability from various
    tracking systems (Jira, GitHub, etc.).
    """

    def get_issue(self, issue_id: str) -> Issue:
        """Fetch an issue by its ID.

        Args:
            issue_id: The unique identifier for the issue in the tracking system.

        Returns:
            An Issue object containing the issue's metadata and description.

        Raises:
            ValueError: If the issue cannot be fetched or does not exist.
            ConfigurationError: If the tracker is not properly configured.
        """
        ...
