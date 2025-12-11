#!/usr/bin/env python3
"""Post comments as the hey-amelia GitHub App.

This script handles GitHub App authentication and posts comments
to issues, PRs, or as replies to review comments.

Usage:
    # Reply to a review comment
    uv run python post_comment.py --repo owner/repo --comment-id 123 --body "Response"

    # Post a PR comment
    uv run python post_comment.py --repo owner/repo --pr 42 --body "Comment"

    # Post an issue comment
    uv run python post_comment.py --repo owner/repo --issue 42 --body "Comment"
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
            "private_key_path": private_key_path,
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


def get_comment_pr_number(token: str, repo: str, comment_id: int) -> int:
    """Get the PR number from a review comment."""
    owner, repo_name = repo.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo_name}/pulls/comments/{comment_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    response = httpx.get(url, headers=headers)
    response.raise_for_status()

    # Extract PR number from pull_request_url
    # Format: https://api.github.com/repos/{owner}/{repo}/pulls/{number}
    pr_url = response.json()["pull_request_url"]
    return int(pr_url.split("/")[-1])


def post_review_comment_reply(
    token: str, repo: str, comment_id: int, body: str
) -> dict:
    """Post a reply to a review comment.

    Uses the correct GitHub API endpoint:
    POST /repos/{owner}/{repo}/pulls/{pull_number}/comments
    with in_reply_to_id in the request body.
    """
    owner, repo_name = repo.split("/")

    # First, get the PR number from the comment
    pr_number = get_comment_pr_number(token, repo, comment_id)

    url = f"https://api.github.com/repos/{owner}/{repo_name}/pulls/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    response = httpx.post(
        url, headers=headers, json={"body": body, "in_reply_to": comment_id}
    )
    response.raise_for_status()

    return response.json()


def post_pr_comment(token: str, repo: str, pr_number: int, body: str) -> dict:
    """Post a general comment on a PR."""
    owner, repo_name = repo.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo_name}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    response = httpx.post(url, headers=headers, json={"body": body})
    response.raise_for_status()

    return response.json()


def post_issue_comment(token: str, repo: str, issue_number: int, body: str) -> dict:
    """Post a comment on an issue."""
    # Same endpoint as PR comments (issues and PRs share the comments API)
    return post_pr_comment(token, repo, issue_number, body)


def main():
    parser = argparse.ArgumentParser(
        description="Post comments as the hey-amelia GitHub App"
    )
    parser.add_argument("--repo", required=True, help="Repository in owner/repo format")
    parser.add_argument("--body", required=True, help="Comment body")
    parser.add_argument(
        "--comment-id", type=int, help="Review comment ID to reply to"
    )
    parser.add_argument("--pr", type=int, help="PR number for general comment")
    parser.add_argument("--issue", type=int, help="Issue number for comment")

    args = parser.parse_args()

    # Validate that exactly one target is specified
    targets = [args.comment_id, args.pr, args.issue]
    if sum(t is not None for t in targets) != 1:
        print(
            "Error: Specify exactly one of --comment-id, --pr, or --issue",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load config and authenticate
    config = load_config()
    jwt_token = generate_jwt(config["app_id"], config["private_key_path"])
    token = get_installation_token(jwt_token, config["installation_id"])

    # Post the comment
    if args.comment_id:
        result = post_review_comment_reply(token, args.repo, args.comment_id, args.body)
        print(f"Posted reply to comment {args.comment_id}: {result['html_url']}")
    elif args.pr:
        result = post_pr_comment(token, args.repo, args.pr, args.body)
        print(f"Posted comment on PR #{args.pr}: {result['html_url']}")
    elif args.issue:
        result = post_issue_comment(token, args.repo, args.issue, args.body)
        print(f"Posted comment on issue #{args.issue}: {result['html_url']}")


if __name__ == "__main__":
    main()
