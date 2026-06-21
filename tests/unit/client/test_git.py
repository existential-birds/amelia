# tests/unit/client/test_git.py
"""Tests for git worktree context detection.

Worktree context is resolved in a SINGLE git invocation for the common case:
``git rev-parse --is-inside-work-tree --is-bare-repository --show-toplevel
--abbrev-ref HEAD``. Each flag emits one output line, in order:
    1. is_inside_work_tree  ("true" / "false")
    2. is_bare              ("true" / "false")
    3. toplevel             (absolute worktree root)
    4. branch               (branch name, or "HEAD" when detached)

For detached HEAD only, a second call ``git rev-parse --short HEAD`` fetches
the short sha.  --short cannot be combined with --abbrev-ref in the same
rev-parse invocation: --abbrev-ref is a sticky output-format mode that
overrides --short, causing git to emit the abbrev-ref value ("HEAD") instead
of the commit sha.
"""
from unittest.mock import MagicMock, patch

import pytest


def _combined(*lines: str) -> str:
    """Build the multi-line stdout `git rev-parse` emits for the combined call.

    Only 4 lines are emitted by the combined invocation (is_inside_work_tree,
    is_bare, toplevel, branch).  A 5th line is NOT produced; see module
    docstring for why --short cannot be combined with --abbrev-ref.
    """
    return "".join(f"{line}\n" for line in lines)


class TestGetWorktreeContext:
    """Tests for get_worktree_context function."""

    def test_returns_tuple_in_single_invocation(self):
        """Resolves context in ONE git call and parses combined output."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=_combined("true", "false", "/home/user/repo", "main"),
                stderr="",
            )

            path, name = get_worktree_context()

            assert isinstance(path, str)
            assert isinstance(name, str)
            assert path == "/home/user/repo"
            assert name == "main"
            # Acceptance criterion: a SINGLE git invocation resolves context
            # for the common (non-detached) case.
            assert mock_run.call_count == 1

    def test_raises_when_not_in_git_repo(self):
        """Raises ValueError when not in a git repository."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            # Combined rev-parse exits non-zero with no usable stdout, then the
            # bare-repository probe reports false.
            mock_run.side_effect = [
                MagicMock(returncode=128, stdout="", stderr="not a git repository"),
                MagicMock(returncode=128, stdout="false\n", stderr=""),
            ]

            with pytest.raises(ValueError, match="Not inside a git repository"):
                get_worktree_context()

    def test_raises_when_in_bare_repo(self):
        """Raises ValueError when in a bare repository.

        In a bare repo, --show-toplevel makes the combined rev-parse exit
        non-zero, so the follow-up --is-bare-repository probe disambiguates.
        """
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=128, stdout="false\ntrue\n", stderr="fatal"),
                MagicMock(returncode=0, stdout="true\n", stderr=""),
            ]

            with pytest.raises(ValueError, match="Cannot run workflows in a bare repository"):
                get_worktree_context()

    def test_handles_detached_head(self):
        """Uses short commit hash as name for detached HEAD.

        When detached, --abbrev-ref HEAD emits "HEAD" on line 4.  Because
        --abbrev-ref is a sticky output-format mode in git rev-parse, the
        short sha cannot be retrieved from the same invocation; get_worktree_context
        issues a second targeted ``git rev-parse --short HEAD`` call to obtain it.
        """
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                # First call: combined rev-parse; line 4 is "HEAD" (detached).
                MagicMock(
                    returncode=0,
                    stdout=_combined("true", "false", "/home/user/repo", "HEAD"),
                    stderr="",
                ),
                # Second call: targeted --short HEAD to get the actual sha.
                MagicMock(returncode=0, stdout="abc1234\n", stderr=""),
            ]

            path, name = get_worktree_context()

            assert path == "/home/user/repo"
            assert name == "detached-abc1234"
            assert mock_run.call_count == 2

    def test_handles_detached_head_missing_hash(self):
        """Falls back to directory name if the targeted --short HEAD call fails.

        This covers the unborn-branch case (git init, no commits yet): git
        reports is-inside-work-tree=true but --short HEAD fails with rc=128
        because HEAD is unresolvable.  The fallback is the directory name,
        matching pre-PR behavior.
        """
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                # First call: combined rev-parse; line 4 is "HEAD" (detached or unborn).
                MagicMock(
                    returncode=128,
                    stdout=_combined("true", "false", "/home/user/repo", "HEAD"),
                    stderr="fatal: ambiguous argument 'HEAD'",
                ),
                # Second call: --short HEAD fails (e.g., unborn branch / no commits).
                MagicMock(returncode=128, stdout="", stderr="fatal"),
            ]

            path, name = get_worktree_context()

            assert path == "/home/user/repo"
            assert name == "repo"

    def test_empty_branch_name_uses_directory(self):
        """Uses directory name if the branch line is empty."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=_combined("true", "false", "/home/user/project", ""),
                stderr="",
            )

            path, name = get_worktree_context()

            assert path == "/home/user/project"
            assert name == "project"

    def test_branch_with_slash_is_preserved(self):
        """A branch name containing '/' must not be split or truncated.

        This is the shape that breaks naive parsing that splits on '/' or
        assumes the path is the last token.
        """
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=_combined("true", "false", "/home/user/repo", "feature/foo-bar"),
                stderr="",
            )

            path, name = get_worktree_context()

            assert path == "/home/user/repo"
            assert name == "feature/foo-bar"

    def test_truncated_output_raises_runtime_error(self):
        """Raises RuntimeError if combined output is missing required lines."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            # rev-parse succeeded but emitted fewer lines than expected.
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=_combined("true", "false"),
                stderr="",
            )

            with pytest.raises(RuntimeError, match="Failed to determine worktree root"):
                get_worktree_context()
