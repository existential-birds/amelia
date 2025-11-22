from amelia.trackers.base import BaseTracker
from amelia.core.types import Issue
import httpx
import os

class JiraTracker(BaseTracker):
    def get_issue(self, issue_id: str) -> Issue:
        jira_url = os.environ.get("JIRA_URL", "https://your-domain.atlassian.net")
        email = os.environ.get("JIRA_EMAIL")
        token = os.environ.get("JIRA_API_TOKEN")
        
        if not email or not token:
             # Fallback to stub for tests that don't set env vars, 
             # OR better: if we are in a test with mocked httpx, we expect it to work.
             # But if real usage and no env vars, we should probably error or warn.
             # For this implementation, let's proceed to the request. 
             # If auth is missing, the API call will just fail (or 401), which is fine.
             pass

        auth = (email, token) if email and token else None
        
        url = f"{jira_url}/rest/api/3/issue/{issue_id}"
        
        try:
            response = httpx.get(url, auth=auth, headers={"Accept": "application/json"})
            response.raise_for_status()
            data = response.json()
            
            fields = data.get("fields", {})
            return Issue(
                id=data.get("key", issue_id),
                title=fields.get("summary", ""),
                description=fields.get("description", "") or "", # Handle None description
                status=fields.get("status", {}).get("name", "open")
            )
        except Exception as e:
             # If we are running tests without mocks, this might fail.
             # But with mocks it should pass.
             # If it fails in production, we re-raise or handle.
             raise ValueError(f"Failed to fetch issue {issue_id} from Jira: {e}")