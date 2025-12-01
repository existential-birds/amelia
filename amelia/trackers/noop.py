from amelia.core.types import Issue
from amelia.trackers.base import BaseTracker


class NoopTracker(BaseTracker):
    """A null-object tracker that returns placeholder issues without external calls.

    This tracker implements the BaseTracker protocol without connecting to any
    external issue tracking system. It enables several key workflows:

    1. Testing: All test profile presets default to this tracker, allowing unit,
       integration, and e2e tests to run without Jira credentials or GitHub auth.

    2. Local development: Developers can iterate on the orchestrator itself using
       a profile with `tracker: noop` without needing issue tracker access.

    3. Manual task entry: When the issue ID is just a reference tag and the task
       description will be provided directly via CLI arguments or prompts.

    The factory accepts both "noop" and "none" as aliases for this tracker.
    """

    def get_issue(self, issue_id: str) -> Issue:
        """Return a placeholder issue without making any external calls.

        Args:
            issue_id: The issue identifier to use for the placeholder.

        Returns:
            A placeholder Issue object with generic title and description.
        """
        return Issue(id=issue_id, title="Placeholder Issue", description="Tracker not configured")
