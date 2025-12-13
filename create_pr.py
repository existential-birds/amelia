#!/usr/bin/env python3
"""Create pull requests as the hey-amelia GitHub App.

This script handles GitHub App authentication and creates pull requests
with the specified title, body, and branch configuration.

Usage:
    # Create a regular PR
    uv run python create_pr.py --repo owner/repo --head feature-branch --base main --title "Add feature" --body "Description"

    # Create a draft PR
    uv run python create_pr.py --repo owner/repo --head feature-branch --base main --title "WIP: Feature" --body "Draft PR" --draft
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


def create_pull_request(
    token: str,
    repo: str,
    head: str,
    base: str,
    title: str,
    body: str,
    draft: bool = False,
) -> dict:
    """Create a pull request.

    Args:
        token: GitHub installation access token
        repo: Repository in owner/repo format
        head: Branch name with changes (source branch)
        base: Branch to merge into (target branch)
        title: PR title
        body: PR description body
        draft: Whether to create as draft PR

    Returns:
        API response containing PR details

    Raises:
        httpx.HTTPStatusError: If the API request fails
    """
    owner, repo_name = repo.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo_name}/pulls"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    payload = {
        "title": title,
        "body": body,
        "head": head,
        "base": base,
        "draft": draft,
    }

    try:
        response = httpx.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        # Provide more helpful error messages
        if e.response.status_code == 422:
            error_data = e.response.json()
            errors = error_data.get("errors", [])
            if errors:
                error_msg = "; ".join(err.get("message", str(err)) for err in errors)
                print(f"Error: {error_msg}", file=sys.stderr)
            else:
                print(
                    f"Error: {error_data.get('message', 'Validation failed')}",
                    file=sys.stderr,
                )
            print("\nCommon issues:", file=sys.stderr)
            print("  - Head branch does not exist or has no commits", file=sys.stderr)
            print("  - PR already exists between these branches", file=sys.stderr)
            print("  - No commits between head and base branches", file=sys.stderr)
        elif e.response.status_code == 404:
            print(f"Error: Repository '{repo}' not found or not accessible", file=sys.stderr)
        elif e.response.status_code == 403:
            print("Error: Insufficient permissions to create PR", file=sys.stderr)
        else:
            print(f"Error: {e.response.status_code} - {e.response.text}", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Create pull requests as the hey-amelia GitHub App"
    )
    parser.add_argument("--repo", required=True, help="Repository in owner/repo format")
    parser.add_argument(
        "--head", required=True, help="Branch name with changes (source branch)"
    )
    parser.add_argument(
        "--base", required=True, help="Branch to merge into (target branch)"
    )
    parser.add_argument("--title", required=True, help="PR title")
    parser.add_argument("--body", required=True, help="PR description body")
    parser.add_argument(
        "--draft", action="store_true", help="Create as draft PR (default: false)"
    )

    args = parser.parse_args()

    # Validate repo format
    if "/" not in args.repo:
        print(
            "Error: --repo must be in owner/repo format (e.g., octocat/hello-world)",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        # Load config and authenticate
        config = load_config()
        jwt_token = generate_jwt(config["app_id"], config["private_key_path"])
        token = get_installation_token(jwt_token, config["installation_id"])

        # Create the pull request
        result = create_pull_request(
            token=token,
            repo=args.repo,
            head=args.head,
            base=args.base,
            title=args.title,
            body=args.body,
            draft=args.draft,
        )

        # Print success message
        pr_number = result["number"]
        pr_url = result["html_url"]
        draft_status = " (draft)" if args.draft else ""
        print(f"Successfully created PR #{pr_number}{draft_status}")
        print(f"URL: {pr_url}")

    except httpx.HTTPStatusError:
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyError as e:
        print(f"Error: Missing required configuration key: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
