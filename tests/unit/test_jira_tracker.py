from unittest.mock import patch

from amelia.trackers.jira import JiraTracker


def test_jira_get_issue():
    tracker = JiraTracker()
    with patch("httpx.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "key": "PROJ-123",
            "fields": {"summary": "Test Issue", "description": "Desc"}
        }
        issue = tracker.get_issue("PROJ-123")
        assert issue.title == "Test Issue"
        assert issue.description == "Desc"
