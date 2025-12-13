#!/usr/bin/env python3
"""Create GitHub issues as the hey-amelia GitHub App.

This script handles GitHub App authentication and creates issues
with optional labels, assignees, and milestone.

Usage:
    # Create a basic issue
    uv run python create_issue.py --repo owner/repo --title "Bug report" --body "Description"

    # Create an issue with labels and assignees
    uv run python create_issue.py --repo owner/repo --title "Feature request" \
        --body "Description" --labels "enhancement,good first issue" \
        --assignees "username1,username2"

    # Create an issue with a milestone
    uv run python create_issue.py --repo owner/repo --title "Task" \
        --body "Description" --milestone 5
"""

import argparse
import os
import sys
import time
from pathlib import Path

import httpx
import jwt
import yaml


def load_config() -> dict:
    """Load GitHub App configuration from environment or config file."""
    # Check environment variables first
    app_id = os.environ.get("HEY_AMELIA_APP_ID")
    private_key_path = os.environ.get("HEY_AMELIA_PRIVATE_KEY_PATH")
    installation_id = os.environ.get("HEY_AMELIA_INSTALLATION_ID")

    if app_id and private_key_path and installation_id:
        return {
            "app_id": app_id,
            "private_key_path": os.path.expanduser(private_key_path),
            "installation_id": installation_id,
        }

    # Fall back to config file
    config_path = os.environ.get(
        "HEY_AMELIA_CONFIG", os.path.expanduser("~/.config/amelia/github-app.yaml")
    )

    if not Path(config_path).exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        print(
            "Set HEY_AMELIA_APP_ID, HEY_AMELIA_PRIVATE_KEY_PATH, and HEY_AMELIA_INSTALLATION_ID",
            file=sys.stderr,
        )
        print(f"Or create config file at: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Expand ~ in private key path
    if "private_key_path" in config:
        config["private_key_path"] = os.path.expanduser(config["private_key_path"])

    return config


def generate_jwt(app_id: str, private_key_path: str) -> str:
    """Generate a JWT for GitHub App authentication."""
    with open(private_key_path) as f:
        private_key = f.read()

    now = int(time.time())
    payload = {
        "iat": now - 60,  # Issued 60 seconds ago to account for clock drift
        "exp": now + 600,  # Expires in 10 minutes
        "iss": app_id,
    }

    return jwt.encode(payload, private_key, algorithm="RS256")


def get_installation_token(jwt_token: str, installation_id: str) -> str:
    """Exchange JWT for an installation access token."""
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    response = httpx.post(url, headers=headers)
    response.raise_for_status()

    return response.json()["token"]


def create_issue(
    token: str,
    repo: str,
    title: str,
    body: str,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
    milestone: int | None = None,
) -> dict:
    """Create a new issue in the repository.

    Args:
        token: GitHub installation access token
        repo: Repository in owner/repo format
        title: Issue title
        body: Issue description body
        labels: Optional list of label names
        assignees: Optional list of GitHub usernames
        milestone: Optional milestone number

    Returns:
        GitHub API response with issue details

    Raises:
        httpx.HTTPStatusError: If the API request fails
    """
    owner, repo_name = repo.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo_name}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Build request payload
    payload = {
        "title": title,
        "body": body,
    }

    if labels:
        payload["labels"] = labels

    if assignees:
        payload["assignees"] = assignees

    if milestone is not None:
        payload["milestone"] = milestone

    try:
        response = httpx.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        error_msg = f"Failed to create issue: {e.response.status_code}"
        try:
            error_detail = e.response.json()
            if "message" in error_detail:
                error_msg += f" - {error_detail['message']}"
            if "errors" in error_detail:
                for error in error_detail["errors"]:
                    if isinstance(error, dict):
                        error_msg += f"\n  - {error.get('message', error)}"
                    else:
                        error_msg += f"\n  - {error}"
        except Exception:
            error_msg += f"\n{e.response.text}"
        print(error_msg, file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Create GitHub issues as the hey-amelia GitHub App"
    )
    parser.add_argument("--repo", required=True, help="Repository in owner/repo format")
    parser.add_argument("--title", required=True, help="Issue title")
    parser.add_argument("--body", required=True, help="Issue description body")
    parser.add_argument(
        "--labels",
        help='Comma-separated list of label names (e.g., "bug,enhancement")',
    )
    parser.add_argument(
        "--assignees",
        help='Comma-separated list of GitHub usernames (e.g., "user1,user2")',
    )
    parser.add_argument(
        "--milestone",
        type=int,
        help="Milestone number (integer)",
    )

    args = parser.parse_args()

    # Parse comma-separated lists
    labels = [label.strip() for label in args.labels.split(",")] if args.labels else None
    assignees = (
        [assignee.strip() for assignee in args.assignees.split(",")]
        if args.assignees
        else None
    )

    # Validate repo format
    if "/" not in args.repo:
        print(
            "Error: --repo must be in owner/repo format (e.g., 'octocat/hello-world')",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load config and authenticate
    try:
        config = load_config()
        jwt_token = generate_jwt(config["app_id"], config["private_key_path"])
        token = get_installation_token(jwt_token, config["installation_id"])
    except Exception as e:
        print(f"Authentication failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Create the issue
    try:
        result = create_issue(
            token=token,
            repo=args.repo,
            title=args.title,
            body=args.body,
            labels=labels,
            assignees=assignees,
            milestone=args.milestone,
        )
        print(f"Created issue #{result['number']}: {result['html_url']}")
    except httpx.HTTPStatusError:
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
