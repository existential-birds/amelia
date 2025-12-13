#!/usr/bin/env python3
"""Commit files to a GitHub repository using the Git Data API.

This script handles GitHub App authentication and commits multiple files
to a branch using the low-level Git Data API.

Usage:
    # Commit to existing branch
    uv run python commit_files.py --repo owner/repo --branch feature-branch \
        --message "Add new files" --files "file1.txt,file2.py"

    # Create new branch and commit
    uv run python commit_files.py --repo owner/repo --branch new-feature \
        --message "Initial commit" --files "README.md" --create-branch

    # With custom author
    uv run python commit_files.py --repo owner/repo --branch main \
        --message "Update docs" --files "docs/guide.md" \
        --author-name "Custom Author" --author-email "author@example.com"
"""

import argparse
import base64
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


def get_default_branch_sha(token: str, repo: str) -> str:
    """Get the commit SHA of the default branch."""
    owner, repo_name = repo.split("/")

    # First, get the default branch name
    repo_url = f"https://api.github.com/repos/{owner}/{repo_name}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    response = httpx.get(repo_url, headers=headers)
    response.raise_for_status()
    default_branch = response.json()["default_branch"]

    # Get the commit SHA for the default branch
    commit_sha = get_branch_commit_sha(token, repo, default_branch)
    if not commit_sha:
        raise RuntimeError(f"Could not get commit SHA for default branch: {default_branch}")

    return commit_sha


def create_branch(token: str, repo: str, branch: str, commit_sha: str) -> None:
    """Create a new branch pointing to the specified commit."""
    owner, repo_name = repo.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo_name}/git/refs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    data = {
        "ref": f"refs/heads/{branch}",
        "sha": commit_sha,
    }

    response = httpx.post(url, headers=headers, json=data)
    response.raise_for_status()
    print(f"Created branch: {branch}")


def get_commit_tree_sha(token: str, repo: str, commit_sha: str) -> str:
    """Get the tree SHA from a commit."""
    owner, repo_name = repo.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo_name}/git/commits/{commit_sha}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    response = httpx.get(url, headers=headers)
    response.raise_for_status()

    return response.json()["tree"]["sha"]


def create_blob(token: str, repo: str, content: str) -> str:
    """Create a blob with the file content.

    Returns the blob SHA.
    """
    owner, repo_name = repo.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo_name}/git/blobs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Encode content as base64
    encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    data = {
        "content": encoded_content,
        "encoding": "base64",
    }

    response = httpx.post(url, headers=headers, json=data)
    response.raise_for_status()

    return response.json()["sha"]


def create_tree(token: str, repo: str, base_tree_sha: str, file_blobs: list[dict]) -> str:
    """Create a new tree with the specified blobs.

    file_blobs: List of dicts with keys: path, blob_sha
    Returns the new tree SHA.
    """
    owner, repo_name = repo.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo_name}/git/trees"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    tree_items = [
        {
            "path": blob["path"],
            "mode": "100644",  # Regular file
            "type": "blob",
            "sha": blob["blob_sha"],
        }
        for blob in file_blobs
    ]

    data = {
        "base_tree": base_tree_sha,
        "tree": tree_items,
    }

    response = httpx.post(url, headers=headers, json=data)
    response.raise_for_status()

    return response.json()["sha"]


def create_commit(
    token: str,
    repo: str,
    tree_sha: str,
    parent_sha: str,
    message: str,
    author_name: str,
    author_email: str,
) -> str:
    """Create a commit with the specified tree.

    Returns the commit SHA.
    """
    owner, repo_name = repo.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo_name}/git/commits"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    data = {
        "message": message,
        "tree": tree_sha,
        "parents": [parent_sha],
        "author": {
            "name": author_name,
            "email": author_email,
        },
    }

    response = httpx.post(url, headers=headers, json=data)
    response.raise_for_status()

    return response.json()["sha"]


def update_branch_ref(token: str, repo: str, branch: str, commit_sha: str) -> None:
    """Update the branch reference to point to the new commit."""
    owner, repo_name = repo.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo_name}/git/refs/heads/{branch}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    data = {
        "sha": commit_sha,
        "force": False,
    }

    response = httpx.patch(url, headers=headers, json=data)
    response.raise_for_status()


def commit_files(
    token: str,
    repo: str,
    branch: str,
    message: str,
    file_paths: list[str],
    create_branch_if_missing: bool,
    author_name: str,
    author_email: str,
) -> str:
    """Commit files to a branch using the Git Data API.

    Returns the commit SHA.
    """
    # Validate all files exist
    for file_path in file_paths:
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

    # Get current commit SHA for the branch
    current_commit_sha = get_branch_commit_sha(token, repo, branch)

    # Handle branch creation if needed
    if current_commit_sha is None:
        if not create_branch_if_missing:
            raise ValueError(f"Branch '{branch}' does not exist. Use --create-branch to create it.")

        # Get default branch SHA and create the new branch
        default_sha = get_default_branch_sha(token, repo)
        create_branch(token, repo, branch, default_sha)
        current_commit_sha = default_sha

    # Get the tree SHA from the current commit
    base_tree_sha = get_commit_tree_sha(token, repo, current_commit_sha)

    # Create blobs for each file
    print(f"Creating blobs for {len(file_paths)} file(s)...")
    file_blobs = []
    for file_path in file_paths:
        with open(file_path) as f:
            content = f.read()

        blob_sha = create_blob(token, repo, content)
        # Preserve the relative path structure in the repository
        file_blobs.append({
            "path": file_path,
            "blob_sha": blob_sha,
        })
        print(f"  Created blob for {file_path}: {blob_sha[:7]}")

    # Create a new tree with all the blobs
    print("Creating tree...")
    tree_sha = create_tree(token, repo, base_tree_sha, file_blobs)
    print(f"  Tree SHA: {tree_sha[:7]}")

    # Create the commit
    print("Creating commit...")
    commit_sha = create_commit(
        token, repo, tree_sha, current_commit_sha, message, author_name, author_email
    )
    print(f"  Commit SHA: {commit_sha[:7]}")

    # Update the branch reference
    print(f"Updating branch '{branch}'...")
    update_branch_ref(token, repo, branch, commit_sha)

    return commit_sha


def main():
    parser = argparse.ArgumentParser(
        description="Commit files to a GitHub repository using the Git Data API"
    )
    parser.add_argument("--repo", required=True, help="Repository in owner/repo format")
    parser.add_argument("--branch", required=True, help="Branch name to commit to")
    parser.add_argument("--message", required=True, help="Commit message")
    parser.add_argument(
        "--files",
        required=True,
        help="Comma-separated list of local file paths to commit",
    )
    parser.add_argument(
        "--create-branch",
        action="store_true",
        help="Create branch if it doesn't exist",
    )
    parser.add_argument(
        "--author-name",
        default="hey-amelia[bot]",
        help="Commit author name (default: hey-amelia[bot])",
    )
    parser.add_argument(
        "--author-email",
        default="hey-amelia[bot]@users.noreply.github.com",
        help="Commit author email (default: hey-amelia[bot]@users.noreply.github.com)",
    )

    args = parser.parse_args()

    # Parse file paths
    file_paths = [f.strip() for f in args.files.split(",")]

    # Load config and authenticate
    try:
        config = load_config()
        jwt_token = generate_jwt(config["app_id"], config["private_key_path"])
        token = get_installation_token(jwt_token, config["installation_id"])
    except Exception as e:
        print(f"Error: Failed to authenticate: {e}", file=sys.stderr)
        sys.exit(1)

    # Commit the files
    try:
        commit_sha = commit_files(
            token,
            args.repo,
            args.branch,
            args.message,
            file_paths,
            args.create_branch,
            args.author_name,
            args.author_email,
        )

        # Build commit URL
        owner, repo_name = args.repo.split("/")
        commit_url = f"https://github.com/{owner}/{repo_name}/commit/{commit_sha}"

        print("\nSuccess!")
        print(f"Commit SHA: {commit_sha}")
        print(f"Commit URL: {commit_url}")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"Error: GitHub API request failed: {e}", file=sys.stderr)
        print(f"Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
