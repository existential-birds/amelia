from amelia.trackers.base import BaseTracker
from amelia.core.types import Issue

class NoopTracker(BaseTracker):
    def get_issue(self, issue_id: str) -> Issue:
        return Issue(id=issue_id, title="Placeholder Issue", description="Tracker not configured")
