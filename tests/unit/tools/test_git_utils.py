"""Tests for LocalWorktree async context manager."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from amelia.tools.git_utils import LocalWorktree


@pytest.fixture()
async def git_repo(tmp_path: Path) -> Path:
    """Create a real git repo with one commit on 'main' and push to a bare remote."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Initialize a real git repo
    await _run("git", "init", "-b", "main", cwd=repo)
    await _run("git", "config", "user.email", "test@test.com", cwd=repo)
    await _run("git", "config", "user.name", "Test", cwd=repo)

    # Create initial commit
    (repo / "README.md").write_text("hello")
    await _run("git", "add", ".", cwd=repo)
    await _run("git", "commit", "-m", "initial", cwd=repo)

    # Create a bare remote and push to it so origin/<branch> refs exist
    bare = tmp_path / "bare.git"
    await _run("git", "clone", "--bare", str(repo), str(bare))
    await _run("git", "remote", "add", "origin", str(bare), cwd=repo)
    await _run("git", "fetch", "origin", cwd=repo)

    return repo


async def _run(*args: str, cwd: Path | None = None) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed: {stderr.decode()}")
    return stdout.decode().strip()


class TestLocalWorktree:
    async def test_creates_and_cleans_up(self, git_repo: Path) -> None:
        """Worktree path exists inside context, gone after exit."""
        wt = LocalWorktree(git_repo, "main", "test-wt-1")
        worktree_path: Path | None = None

        async with wt as path:
            worktree_path = Path(path)
            assert worktree_path.is_dir()
            # Should contain the repo files
            assert (worktree_path / "README.md").exists()

        assert worktree_path is not None
        assert not worktree_path.exists()

    async def test_removes_stale_on_entry(self, git_repo: Path) -> None:
        """Pre-existing stale directory at worktree path is handled."""
        wt = LocalWorktree(git_repo, "main", "test-wt-stale")
        # Pre-create a stale directory at the worktree path
        stale_path = wt.path
        stale_path.mkdir(parents=True, exist_ok=True)
        (stale_path / "stale-file.txt").write_text("stale")

        async with wt as path:
            worktree_path = Path(path)
            assert worktree_path.is_dir()
            # Should have repo content, not stale content
            assert (worktree_path / "README.md").exists()
            assert not (worktree_path / "stale-file.txt").exists()

        assert not worktree_path.exists()

    async def test_cleans_up_on_exception(self, git_repo: Path) -> None:
        """Worktree is removed even when an exception occurs inside context."""
        wt = LocalWorktree(git_repo, "main", "test-wt-exc")
        worktree_path: Path | None = None

        with pytest.raises(ValueError, match="test error"):
            async with wt as path:
                worktree_path = Path(path)
                assert worktree_path.is_dir()
                raise ValueError("test error")

        assert worktree_path is not None
        assert not worktree_path.exists()

    async def test_raises_on_bad_branch(self, git_repo: Path) -> None:
        """ValueError raised when branch does not exist."""
        wt = LocalWorktree(git_repo, "nonexistent-branch", "test-wt-bad")
        with pytest.raises(ValueError, match="worktree add"):
            async with wt:
                pass
