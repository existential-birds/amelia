# amelia/trackers/github.py
"""GitHub issue tracker integration."""

import json
import subprocess

from amelia.core.exceptions import ConfigurationError
from amelia.core.types import Issue
from amelia.trackers.base import BaseTracker


class GithubTracker(BaseTracker):
    """Fetches issues from GitHub using the gh CLI."""

    def __init__(self) -> None:
        """Initialize GithubTracker with configuration validation."""
        self._validate_config()

    def _validate_config(self) -> None:
        """
        Validate gh CLI is installed and authenticated.

        Raises:
            ConfigurationError: If gh CLI is not available or not authenticated
        """
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise ConfigurationError(
                    "GitHub CLI is not authenticated. Run 'gh auth login' first. "
                    f"Details: {result.stderr}"
                )
        except FileNotFoundError as e:
            raise ConfigurationError(
                "GitHub CLI 'gh' not found. Install from https://cli.github.com"
            ) from e

    def get_issue(self, issue_id: str) -> Issue:
        """Fetch an issue from GitHub.

        Args:
            issue_id: The GitHub issue number (e.g., '123') or full reference (e.g., 'owner/repo#123').

        Returns:
            An Issue object containing the GitHub issue's metadata and description.

        Raises:
            ValueError: If the issue cannot be fetched, does not exist, or CLI output is invalid.
        """
        try:
            result = subprocess.run(
                ["gh", "issue", "view", issue_id, "--json", "title,body,state"],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)
            return Issue(
                id=issue_id,
                title=data.get("title", ""),
                description=data.get("body", ""),
                status=data.get("state", "open"),
            )
        except subprocess.CalledProcessError as e:
            raise ValueError(
                f"Failed to fetch issue {issue_id} from GitHub: {e.stderr}"
            ) from e
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse GitHub CLI output for issue {issue_id}"
            ) from e
