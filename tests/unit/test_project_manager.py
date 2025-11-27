import pytest

from amelia.agents.project_manager import ProjectManager
from amelia.trackers.base import BaseTracker
from amelia.trackers.base import Issue


class MockTracker(BaseTracker):
    def get_issue(self, issue_id: str) -> Issue:
        if issue_id == "MISSING":
            raise ValueError("Issue not found")
        return Issue(id=issue_id, title="Test Issue", description="Do something")

def test_project_manager_get_issue():
    tracker = MockTracker()
    pm = ProjectManager(tracker=tracker)
    
    issue = pm.get_issue("PROJ-123")
    assert issue.id == "PROJ-123"
    assert issue.title == "Test Issue"

def test_project_manager_missing_issue():
    tracker = MockTracker()
    pm = ProjectManager(tracker=tracker)
    
    with pytest.raises(ValueError):
        pm.get_issue("MISSING")
