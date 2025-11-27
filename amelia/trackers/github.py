import json
import subprocess

from amelia.core.types import Issue
from amelia.trackers.base import BaseTracker


class GithubTracker(BaseTracker):
    def get_issue(self, issue_id: str) -> Issue:
        try:
            result = subprocess.run(
                ["gh", "issue", "view", issue_id, "--json", "title,body,state"],
                capture_output=True,
                text=True,
                check=True
            )
            data = json.loads(result.stdout)
            return Issue(
                id=issue_id,
                title=data.get("title", ""),
                description=data.get("body", ""),
                status=data.get("state", "open")
            )
        except subprocess.CalledProcessError as e:
            # Fallback or re-raise with more info
            raise ValueError(f"Failed to fetch issue {issue_id} from GitHub: {e.stderr}") from e
        except json.JSONDecodeError as e:
             raise ValueError(f"Failed to parse GitHub CLI output for issue {issue_id}") from e