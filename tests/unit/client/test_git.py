# tests/unit/client/test_git.py
"""Tests for git worktree context detection."""
import subprocess
from unittest.mock import MagicMock, patch

import pytest


class TestGetWorktreeContext:
    """Tests for get_worktree_context function."""

    def test_returns_tuple(self):
        """Returns (worktree_path, worktree_name) tuple."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            # Mock git rev-parse --is-inside-work-tree
            mock_run.return_value = MagicMock(
                returncode=0, stdout="true\n", stderr=""
            )

            # Second call: git rev-parse --show-toplevel
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n", stderr=""),
                MagicMock(returncode=0, stdout="/home/user/repo\n", stderr=""),
                MagicMock(returncode=0, stdout="main\n", stderr=""),
            ]

            path, name = get_worktree_context()

            assert isinstance(path, str)
            assert isinstance(name, str)
            assert path == "/home/user/repo"
            assert name == "main"

    def test_raises_when_not_in_git_repo(self):
        """Raises ValueError when not in a git repository."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128, stdout="false\n", stderr="not a git repository"
            )

            with pytest.raises(ValueError, match="Not inside a git repository"):
                get_worktree_context()

    def test_raises_when_in_bare_repo(self):
        """Raises ValueError when in a bare repository."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            # First call: --is-inside-work-tree (fails)
            # Second call: --is-bare-repository (true)
            mock_run.side_effect = [
                MagicMock(returncode=128, stdout="false\n", stderr=""),
                MagicMock(returncode=0, stdout="true\n", stderr=""),
            ]

            with pytest.raises(ValueError, match="Cannot run workflows in a bare repository"):
                get_worktree_context()

    def test_handles_detached_head(self):
        """Uses short commit hash as name for detached HEAD."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n", stderr=""),  # is-inside-work-tree
                MagicMock(returncode=0, stdout="/home/user/repo\n", stderr=""),  # show-toplevel
                MagicMock(returncode=0, stdout="HEAD\n", stderr=""),  # abbrev-ref HEAD
                MagicMock(returncode=0, stdout="abc1234\n", stderr=""),  # short hash
            ]

            path, name = get_worktree_context()

            assert path == "/home/user/repo"
            assert name == "detached-abc1234"

    def test_handles_detached_head_hash_failure(self):
        """Falls back to 'detached' if short hash fails."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n", stderr=""),  # is-inside-work-tree
                MagicMock(returncode=0, stdout="/home/user/repo\n", stderr=""),  # show-toplevel
                MagicMock(returncode=0, stdout="HEAD\n", stderr=""),  # abbrev-ref HEAD
                subprocess.CalledProcessError(1, "git"),  # short hash fails
            ]

            path, name = get_worktree_context()

            assert path == "/home/user/repo"
            assert name == "detached"

    def test_uses_directory_name_when_branch_detection_fails(self):
        """Falls back to directory name if branch detection fails."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n", stderr=""),  # is-inside-work-tree
                MagicMock(returncode=0, stdout="/home/user/my-repo\n", stderr=""),  # show-toplevel
                subprocess.CalledProcessError(1, "git"),  # abbrev-ref fails
            ]

            path, name = get_worktree_context()

            assert path == "/home/user/my-repo"
            assert name == "my-repo"

    def test_raises_runtime_error_on_toplevel_failure(self):
        """Raises RuntimeError if git rev-parse --show-toplevel fails."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n", stderr=""),  # is-inside-work-tree
                subprocess.CalledProcessError(
                    1, "git", stderr="fatal: not a git repository"
                ),  # show-toplevel
            ]

            with pytest.raises(RuntimeError, match="Failed to determine worktree root"):
                get_worktree_context()

    def test_empty_branch_name_uses_directory(self):
        """Uses directory name if branch name is empty."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n", stderr=""),  # is-inside-work-tree
                MagicMock(returncode=0, stdout="/home/user/project\n", stderr=""),  # show-toplevel
                MagicMock(returncode=0, stdout="\n", stderr=""),  # empty branch name
            ]

            path, name = get_worktree_context()

            assert path == "/home/user/project"
            assert name == "project"
