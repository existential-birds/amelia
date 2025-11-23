from amelia.trackers.noop import NoopTracker
# from amelia.trackers.github import GithubTracker # Not yet implemented
# from amelia.trackers.jira import JiraTracker # Not yet implemented

def test_noop_tracker_get_issue():
    tracker = NoopTracker()
    issue = tracker.get_issue("ANY-123")
    assert issue.id == "ANY-123"
    assert issue.title == "Placeholder Issue"
    assert issue.description == "Tracker not configured"

# TODO: Add tests for GithubTracker and JiraTracker once implemented
