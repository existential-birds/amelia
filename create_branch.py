#!/usr/bin/env python3
"""Create branches as the hey-amelia GitHub App.

This script handles GitHub App authentication and creates branches
from a specified base branch or commit.

Usage:
    # Create branch from default branch
    uv run python create_branch.py --repo owner/repo --branch feature/new-feature

    # Create branch from specific base branch
    uv run python create_branch.py --repo owner/repo --branch feature/new-feature --base develop

    # Create branch from specific commit SHA
    uv run python create_branch.py --repo owner/repo --branch hotfix/urgent --sha abc1234
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


def get_default_branch(token: str, repo: str) -> str:
    """Get the default branch name for a repository."""
    owner, repo_name = repo.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo_name}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    response = httpx.get(url, headers=headers)
    response.raise_for_status()

    return response.json()["default_branch"]


def get_branch_commit_sha(token: str, repo: str, branch: str) -> str | None:
    """Get the current commit SHA for a branch.

    Returns None if the branch doesn't exist.
    """
    owner, repo_name = repo.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo_name}/git/ref/heads/{branch}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        response = httpx.get(url, headers=headers)
        response.raise_for_status()
        return response.json()["object"]["sha"]
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise


def create_branch(token: str, repo: str, branch: str, sha: str) -> dict:
    """Create a new branch pointing to the specified commit.

    Args:
        token: GitHub installation access token
        repo: Repository in owner/repo format
        branch: New branch name
        sha: Commit SHA to point the branch at

    Returns:
        API response with branch reference details

    Raises:
        httpx.HTTPStatusError: If the API request fails
    """
    owner, repo_name = repo.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo_name}/git/refs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    data = {
        "ref": f"refs/heads/{branch}",
        "sha": sha,
    }

    try:
        response = httpx.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 422:
            error_data = e.response.json()
            if "Reference already exists" in str(error_data):
                print(f"Error: Branch '{branch}' already exists", file=sys.stderr)
            else:
                print(f"Error: {error_data.get('message', 'Validation failed')}", file=sys.stderr)
        elif e.response.status_code == 404:
            print(f"Error: Repository '{repo}' not found or not accessible", file=sys.stderr)
        elif e.response.status_code == 403:
            print("Error: Insufficient permissions to create branch", file=sys.stderr)
        else:
            print(f"Error: {e.response.status_code} - {e.response.text}", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Create branches as the hey-amelia GitHub App"
    )
    parser.add_argument("--repo", required=True, help="Repository in owner/repo format")
    parser.add_argument("--branch", required=True, help="New branch name to create")
    parser.add_argument(
        "--base",
        help="Base branch to create from (default: repository's default branch)",
    )
    parser.add_argument(
        "--sha",
        help="Specific commit SHA to create branch from (overrides --base)",
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

        # Determine the commit SHA to branch from
        if args.sha:
            target_sha = args.sha
            source = f"commit {args.sha[:7]}"
        elif args.base:
            target_sha = get_branch_commit_sha(token, args.repo, args.base)
            if not target_sha:
                print(f"Error: Base branch '{args.base}' not found", file=sys.stderr)
                sys.exit(1)
            source = f"branch '{args.base}'"
        else:
            # Use default branch
            default_branch = get_default_branch(token, args.repo)
            target_sha = get_branch_commit_sha(token, args.repo, default_branch)
            if not target_sha:
                print(f"Error: Could not get SHA for default branch '{default_branch}'", file=sys.stderr)
                sys.exit(1)
            source = f"branch '{default_branch}' (default)"

        # Check if branch already exists
        existing_sha = get_branch_commit_sha(token, args.repo, args.branch)
        if existing_sha:
            print(f"Error: Branch '{args.branch}' already exists", file=sys.stderr)
            sys.exit(1)

        # Create the branch
        create_branch(token, args.repo, args.branch, target_sha)

        # Build branch URL
        owner, repo_name = args.repo.split("/")
        branch_url = f"https://github.com/{owner}/{repo_name}/tree/{args.branch}"

        print(f"Created branch '{args.branch}' from {source}")
        print(f"SHA: {target_sha[:7]}")
        print(f"URL: {branch_url}")

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
