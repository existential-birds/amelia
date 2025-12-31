# amelia/trackers/jira.py
"""Jira issue tracker integration."""

import os

import httpx

from amelia.core.exceptions import ConfigurationError
from amelia.core.types import Issue
from amelia.trackers.base import BaseTracker


class JiraTracker(BaseTracker):
    """Fetches issues from Jira."""

    def __init__(self) -> None:
        """Initialize JiraTracker with configuration validation."""
        self._validate_config()
        self.jira_url = os.environ["JIRA_BASE_URL"]
        self.email = os.environ["JIRA_EMAIL"]
        self.token = os.environ["JIRA_API_TOKEN"]

    def _validate_config(self) -> None:
        """
        Validate required environment variables are set.

        Raises:
            ConfigurationError: If any required variable is missing
        """
        missing = []
        if not os.environ.get("JIRA_BASE_URL"):
            missing.append("JIRA_BASE_URL")
        if not os.environ.get("JIRA_EMAIL"):
            missing.append("JIRA_EMAIL")
        if not os.environ.get("JIRA_API_TOKEN"):
            missing.append("JIRA_API_TOKEN")

        if missing:
            raise ConfigurationError(
                f"Missing required environment variables for JiraTracker: {', '.join(missing)}"
            )

    def get_issue(self, issue_id: str, *, cwd: str | None = None) -> Issue:
        """Fetch an issue from Jira.

        Args:
            issue_id: The Jira issue key (e.g., 'PROJECT-123').
            cwd: Unused. Jira uses API calls, not CLI, so working directory is irrelevant.

        Returns:
            An Issue object containing the Jira issue's metadata and description.

        Raises:
            ValueError: If the issue cannot be fetched or does not exist.
        """
        del cwd  # Unused - Jira uses API, not CLI
        url = f"{self.jira_url}/rest/api/3/issue/{issue_id}"

        try:
            response = httpx.get(
                url,
                auth=(self.email, self.token),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            fields = data.get("fields", {})
            return Issue(
                id=data.get("key", issue_id),
                title=fields.get("summary", ""),
                description=fields.get("description", "") or "",
                status=fields.get("status", {}).get("name", "open"),
            )
        except httpx.HTTPError as e:
            raise ValueError(f"Failed to fetch issue {issue_id} from Jira: {e}") from e
