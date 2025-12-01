from typing import Protocol

from amelia.core.types import Issue


class BaseTracker(Protocol):
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
