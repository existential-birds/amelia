from typing import Protocol

from amelia.core.types import Issue


class BaseTracker(Protocol):
    def get_issue(self, issue_id: str) -> Issue:
        """
        Fetch an issue by its ID.
        """
        ...
