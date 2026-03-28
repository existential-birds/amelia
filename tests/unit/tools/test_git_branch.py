"""Unit tests for git branch helper functions."""

import asyncio
import subprocess
from pathlib import Path

import pytest

from amelia.tools.git_utils import (
    create_and_checkout_branch,
    get_current_branch,
    has_uncommitted_changes,
)


@pytest.fixture
def git_repo(tmp_path: Path) -> str:
    """Create a real git repo for testing."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)
    (repo / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)
    return str(repo)


class TestGetCurrentBranch:
    """Tests for get_current_branch."""

    async def test_returns_branch_name(self, git_repo: str) -> None:
        """Should return the current branch name."""
        branch = await get_current_branch(git_repo)
        # Default branch name varies (main or master), just check it's not None
        assert branch is not None
        assert isinstance(branch, str)
        assert len(branch) > 0

    async def test_returns_none_for_detached_head(self, git_repo: str) -> None:
        """Should return None when in detached HEAD state."""
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "HEAD", cwd=git_repo,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        sha = stdout.decode().strip()

        proc = await asyncio.create_subprocess_exec(
            "git", "checkout", sha, cwd=git_repo,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        branch = await get_current_branch(git_repo)
        assert branch is None

    async def test_returns_none_for_non_git_dir(self, tmp_path: Path) -> None:
        """Should return None for a non-git directory."""
        branch = await get_current_branch(str(tmp_path))
        assert branch is None


class TestCreateAndCheckoutBranch:
    """Tests for create_and_checkout_branch."""

    async def test_creates_and_switches_to_branch(self, git_repo: str) -> None:
        """Should create a new branch and switch to it."""
        await create_and_checkout_branch(git_repo, "amelia/TEST-123")

        branch = await get_current_branch(git_repo)
        assert branch == "amelia/TEST-123"

    async def test_raises_on_existing_branch(self, git_repo: str) -> None:
        """Should raise ValueError if branch already exists."""
        await create_and_checkout_branch(git_repo, "amelia/TEST-123")

        # Switch back to original branch
        proc = await asyncio.create_subprocess_exec(
            "git", "checkout", "-", cwd=git_repo,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        with pytest.raises(ValueError, match="already exists"):
            await create_and_checkout_branch(git_repo, "amelia/TEST-123")

    async def test_raises_on_invalid_branch_name(self, git_repo: str) -> None:
        """Should raise ValueError for invalid branch names."""
        with pytest.raises(ValueError, match="Failed to create branch"):
            await create_and_checkout_branch(git_repo, "invalid..branch")


class TestHasUncommittedChanges:
    """Tests for has_uncommitted_changes."""

    async def test_returns_false_for_clean_repo(self, git_repo: str) -> None:
        """Should return False when working tree is clean."""
        result = await has_uncommitted_changes(git_repo)
        assert result is False

    async def test_returns_true_for_modified_file(self, git_repo: str) -> None:
        """Should return True when there are unstaged changes."""
        (Path(git_repo) / "README.md").write_text("modified")
        result = await has_uncommitted_changes(git_repo)
        assert result is True

    async def test_returns_true_for_new_file(self, git_repo: str) -> None:
        """Should return True when there are untracked files."""
        (Path(git_repo) / "new.txt").write_text("new")
        result = await has_uncommitted_changes(git_repo)
        assert result is True

    async def test_raises_for_non_git_dir(self, tmp_path: Path) -> None:
        """Should raise ValueError for a non-git directory."""
        with pytest.raises(ValueError, match="git status --porcelain failed"):
            await has_uncommitted_changes(str(tmp_path))
