"""Path validation endpoints for worktree path verification."""

import asyncio
import subprocess
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field


router = APIRouter(prefix="/paths", tags=["paths"])


class PathValidationRequest(BaseModel):
    """Request model for validating a filesystem path."""

    path: str = Field(description="Absolute path to validate")


class PathValidationResponse(BaseModel):
    """Response model for path validation result."""

    exists: bool = Field(description="Whether the path exists on disk")
    is_git_repo: bool = Field(description="Whether the path is a git repository")
    branch: str | None = Field(default=None, description="Current branch name if git repo")
    repo_name: str | None = Field(default=None, description="Repository name (directory name)")
    has_changes: bool | None = Field(
        default=None, description="Whether there are uncommitted changes"
    )
    message: str = Field(description="Human-readable status message")


def _get_git_branch_sync(path: Path) -> str | None:
    """Get the current git branch name (sync implementation).

    Args:
        path: Path to the git repository.

    Returns:
        Branch name or None if not determinable.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


async def _get_git_branch(path: Path) -> str | None:
    """Get the current git branch name.

    Args:
        path: Path to the git repository.

    Returns:
        Branch name or None if not determinable.
    """
    return await asyncio.to_thread(_get_git_branch_sync, path)


def _has_uncommitted_changes_sync(path: Path) -> bool:
    """Check if the repository has uncommitted changes (sync implementation).

    Args:
        path: Path to the git repository.

    Returns:
        True if there are uncommitted changes.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, OSError):
        pass
    return False


async def _has_uncommitted_changes(path: Path) -> bool:
    """Check if the repository has uncommitted changes.

    Args:
        path: Path to the git repository.

    Returns:
        True if there are uncommitted changes.
    """
    return await asyncio.to_thread(_has_uncommitted_changes_sync, path)


@router.post("/validate", response_model=PathValidationResponse)
async def validate_path(request: PathValidationRequest) -> PathValidationResponse:
    """Validate a filesystem path and return git repository information.

    This endpoint checks whether a path exists, is a git repository,
    and provides additional context like branch name and change status.

    Args:
        request: Path validation request.

    Returns:
        Validation result with path status and git info.
    """
    file_path = Path(request.path)

    # Check if path is absolute
    if not file_path.is_absolute():
        return PathValidationResponse(
            exists=False,
            is_git_repo=False,
            message="Path must be absolute (start with /)",
        )

    # Resolve symlinks and normalize
    try:
        resolved_path = file_path.resolve()
    except (OSError, RuntimeError):
        return PathValidationResponse(
            exists=False,
            is_git_repo=False,
            message="Invalid path format",
        )

    # Check existence
    if not resolved_path.exists():
        return PathValidationResponse(
            exists=False,
            is_git_repo=False,
            message="Path does not exist",
        )

    # Check if it's a directory
    if not resolved_path.is_dir():
        return PathValidationResponse(
            exists=True,
            is_git_repo=False,
            message="Path is a file, not a directory",
        )

    # Check if it's a git repository
    git_dir = resolved_path / ".git"
    is_git_repo = git_dir.exists() and git_dir.is_dir()

    if not is_git_repo:
        return PathValidationResponse(
            exists=True,
            is_git_repo=False,
            repo_name=resolved_path.name,
            message="Directory exists but is not a git repository",
        )

    # Get git info (run in thread pool to avoid blocking event loop)
    branch = await _get_git_branch(resolved_path)
    has_changes = await _has_uncommitted_changes(resolved_path)

    # Build message
    change_indicator = " with uncommitted changes" if has_changes else ""
    branch_info = f" on branch '{branch}'" if branch else ""
    message = f"Git repository{branch_info}{change_indicator}"

    return PathValidationResponse(
        exists=True,
        is_git_repo=True,
        branch=branch,
        repo_name=resolved_path.name,
        has_changes=has_changes,
        message=message,
    )
