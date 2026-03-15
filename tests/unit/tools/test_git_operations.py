"""Unit tests for GitOperations class."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.tools.git_utils import GitOperations


@pytest.fixture
def git_ops(tmp_path):
    """Create a GitOperations instance with a temporary repo path."""
    return GitOperations(repo_path=tmp_path)


@pytest.fixture
def mock_subprocess():
    """Patch asyncio.create_subprocess_exec with configurable mock processes.

    Returns a factory that sets up sequential mock process results.
    Each result is a tuple of (stdout, stderr, returncode).
    """
    with patch("amelia.tools.git_utils.asyncio.create_subprocess_exec") as mock_exec:
        processes: list[MagicMock] = []

        def setup(*results: tuple[str, str, int]):
            """Configure sequential process results.

            Args:
                results: Tuples of (stdout, stderr, returncode).
            """
            processes.clear()
            side_effects = []
            for stdout, stderr, returncode in results:
                proc = AsyncMock()
                proc.communicate.return_value = (
                    stdout.encode(),
                    stderr.encode(),
                )
                proc.returncode = returncode
                proc.kill = MagicMock()
                proc.wait = AsyncMock()
                processes.append(proc)
                side_effects.append(proc)
            mock_exec.side_effect = side_effects

        yield setup, mock_exec, processes


async def test_stage_and_commit_success(git_ops, mock_subprocess):
    """stage_and_commit runs git add, commit, rev-parse and returns SHA."""
    setup, mock_exec, _ = mock_subprocess
    setup(
        ("", "", 0),  # git add -A
        ("", "", 0),  # git commit -m "test msg"
        ("abc123def", "", 0),  # git rev-parse HEAD
    )

    sha = await git_ops.stage_and_commit("test msg")

    assert sha == "abc123def"
    # Verify correct git commands were called
    calls = mock_exec.call_args_list
    assert calls[0].args[:3] == ("git", "add", "-A")
    assert calls[1].args[:3] == ("git", "commit", "-m")
    assert calls[2].args[:3] == ("git", "rev-parse", "HEAD")


async def test_stage_and_commit_nothing_to_commit(git_ops, mock_subprocess):
    """stage_and_commit raises ValueError when nothing to commit."""
    setup, _, _ = mock_subprocess
    setup(
        ("", "", 0),  # git add -A
        ("", "nothing to commit", 1),  # git commit fails
    )

    with pytest.raises(ValueError, match="failed"):
        await git_ops.stage_and_commit("test msg")


async def test_safe_push_protected_branch_refused(git_ops, mock_subprocess):
    """safe_push refuses to push to protected branch 'main'."""
    _, mock_exec, _ = mock_subprocess

    with pytest.raises(ValueError, match="protected branch"):
        await git_ops.safe_push("main")

    # No subprocess should have been called
    mock_exec.assert_not_called()


@pytest.mark.parametrize("branch", ["main", "master", "develop", "release"])
async def test_safe_push_protected_branches_all(git_ops, mock_subprocess, branch):
    """safe_push refuses all protected branches."""
    _, mock_exec, _ = mock_subprocess

    with pytest.raises(ValueError, match="protected branch"):
        await git_ops.safe_push(branch)

    mock_exec.assert_not_called()


async def test_safe_push_success_local_ahead(git_ops, mock_subprocess):
    """safe_push succeeds when local is ahead of remote."""
    setup, mock_exec, _ = mock_subprocess
    setup(
        ("", "", 0),  # git fetch origin feat-branch
        ("aaa111", "", 0),  # git rev-parse HEAD (local)
        ("bbb222", "", 0),  # git rev-parse origin/feat-branch (remote)
        ("bbb222", "", 0),  # git merge-base aaa111 bbb222 = bbb222 (local ahead)
        ("", "", 0),  # git push origin HEAD
    )

    sha = await git_ops.safe_push("feat-branch")

    assert sha == "aaa111"
    # Verify push was called
    push_call = mock_exec.call_args_list[-1]
    assert push_call.args[:4] == ("git", "push", "origin", "HEAD")


async def test_safe_push_diverged_aborts(git_ops, mock_subprocess):
    """safe_push aborts when remote has diverged."""
    setup, mock_exec, _ = mock_subprocess
    setup(
        ("", "", 0),  # git fetch origin feat-branch
        ("aaa111", "", 0),  # git rev-parse HEAD (local)
        ("bbb222", "", 0),  # git rev-parse origin/feat-branch (remote)
        ("ccc333", "", 0),  # git merge-base = ccc333 (diverged)
    )

    with pytest.raises(ValueError, match="diverged"):
        await git_ops.safe_push("feat-branch")

    # push should NOT have been called (only 4 subprocess calls, no 5th)
    assert len(mock_exec.call_args_list) == 4


async def test_safe_push_new_branch(git_ops, mock_subprocess):
    """safe_push succeeds when remote branch doesn't exist yet."""
    setup, mock_exec, _ = mock_subprocess
    setup(
        ("", "", 0),  # git fetch origin feat-new (ok even if not found)
        ("aaa111", "", 0),  # git rev-parse HEAD (local)
        ("", "unknown revision", 1),  # git rev-parse origin/feat-new fails
        ("", "", 0),  # git push origin HEAD
    )

    sha = await git_ops.safe_push("feat-new")

    assert sha == "aaa111"
    push_call = mock_exec.call_args_list[-1]
    assert push_call.args[:4] == ("git", "push", "origin", "HEAD")


async def test_safe_push_never_force_pushes(git_ops, mock_subprocess):
    """safe_push never includes --force or -f in push args."""
    setup, mock_exec, _ = mock_subprocess
    setup(
        ("", "", 0),  # git fetch
        ("aaa111", "", 0),  # local SHA
        ("", "unknown revision", 1),  # remote doesn't exist
        ("", "", 0),  # git push
    )

    await git_ops.safe_push("feat-new")

    for call in mock_exec.call_args_list:
        all_args = call.args + tuple(call.kwargs.get("args", []))
        assert "--force" not in all_args, "push must not use --force"
        assert "-f" not in all_args, "push must not use -f"


async def test_git_command_timeout(git_ops, mock_subprocess):
    """Git command timeout raises ValueError."""
    _, mock_exec, _ = mock_subprocess

    proc = AsyncMock()
    proc.communicate.side_effect = TimeoutError("timed out")
    proc.kill = MagicMock()
    proc.wait = AsyncMock()
    proc.returncode = None
    mock_exec.side_effect = [proc]

    with pytest.raises(ValueError, match="timed out"):
        await git_ops.stage_and_commit("test msg")
