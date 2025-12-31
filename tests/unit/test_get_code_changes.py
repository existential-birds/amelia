"""Unit tests for get_code_changes_for_review function."""

from unittest.mock import AsyncMock, MagicMock, call, patch

from amelia.core.orchestrator import get_code_changes_for_review


class TestGetCodeChangesForReview:
    """Test all branches of get_code_changes_for_review."""

    async def test_returns_state_code_changes_when_present(
        self, mock_execution_state_factory
    ):
        """Branch 1: Returns state.code_changes_for_review when present."""
        state, profile = mock_execution_state_factory(
            code_changes_for_review="diff --git a/file.py\n+new line"
        )

        result = await get_code_changes_for_review(state, profile)

        assert result == "diff --git a/file.py\n+new line"

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_uses_base_commit_diff_when_available(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Uses git diff against base_commit when state has it set."""
        state, profile = mock_execution_state_factory(
            code_changes_for_review=None,
            base_commit="abc123def456"
        )

        # Mock successful diff against base_commit
        diff_process = MagicMock()
        diff_process.returncode = 0
        diff_process.communicate = AsyncMock(
            return_value=(b"diff --git a/file.py\n+committed change", b"")
        )

        mock_create_subprocess.return_value = diff_process

        result = await get_code_changes_for_review(state, profile)

        assert result == "diff --git a/file.py\n+committed change"
        # Should diff against base_commit, not merge-base
        mock_create_subprocess.assert_called_once_with(
            "git", "diff", "abc123def456",
            stdout=-1, stderr=-1, cwd=profile.working_dir,
        )

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_uses_merge_base_diff_when_available(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Uses git diff against merge-base when branch has committed changes."""
        state, profile = mock_execution_state_factory(code_changes_for_review=None)

        # Mock merge-base lookup succeeds, then diff against merge-base
        merge_base_process = MagicMock()
        merge_base_process.returncode = 0
        merge_base_process.communicate = AsyncMock(return_value=(b"abc123\n", b""))

        diff_process = MagicMock()
        diff_process.returncode = 0
        diff_process.communicate = AsyncMock(
            return_value=(b"diff --git a/file.py\n+committed change", b"")
        )

        mock_create_subprocess.side_effect = [merge_base_process, diff_process]

        result = await get_code_changes_for_review(state, profile)

        assert result == "diff --git a/file.py\n+committed change"
        assert mock_create_subprocess.call_count == 2
        # First call: merge-base lookup
        mock_create_subprocess.assert_any_call(
            "git", "merge-base", "main", "HEAD",
            stdout=-1, stderr=-1, cwd=profile.working_dir,
        )
        # Second call: diff against merge-base
        mock_create_subprocess.assert_any_call(
            "git", "diff", "abc123",
            stdout=-1, stderr=-1, cwd=profile.working_dir,
        )

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_tries_master_branch_when_main_not_found(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Falls back to 'master' when 'main' branch doesn't exist."""
        state, profile = mock_execution_state_factory(code_changes_for_review=None)

        # Mock: 'main' fails, 'master' succeeds
        main_fails = MagicMock()
        main_fails.returncode = 128
        main_fails.communicate = AsyncMock(return_value=(b"", b"fatal: not a valid object name"))

        master_succeeds = MagicMock()
        master_succeeds.returncode = 0
        master_succeeds.communicate = AsyncMock(return_value=(b"def456\n", b""))

        diff_process = MagicMock()
        diff_process.returncode = 0
        diff_process.communicate = AsyncMock(return_value=(b"diff output", b""))

        mock_create_subprocess.side_effect = [main_fails, master_succeeds, diff_process]

        result = await get_code_changes_for_review(state, profile)

        assert result == "diff output"
        assert mock_create_subprocess.call_count == 3

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_falls_back_to_git_diff_head_when_merge_base_empty(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Falls back to git diff HEAD when merge-base diff is empty."""
        state, profile = mock_execution_state_factory(code_changes_for_review=None)

        # Mock: merge-base succeeds but diff is empty, then git diff HEAD has content
        merge_base_process = MagicMock()
        merge_base_process.returncode = 0
        merge_base_process.communicate = AsyncMock(return_value=(b"abc123\n", b""))

        empty_diff = MagicMock()
        empty_diff.returncode = 0
        empty_diff.communicate = AsyncMock(return_value=(b"", b""))

        head_diff = MagicMock()
        head_diff.returncode = 0
        head_diff.communicate = AsyncMock(return_value=(b"uncommitted changes", b""))

        mock_create_subprocess.side_effect = [merge_base_process, empty_diff, head_diff]

        result = await get_code_changes_for_review(state, profile)

        assert result == "uncommitted changes"

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_falls_back_to_git_diff_head_when_no_base_branch(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Falls back to git diff HEAD when neither main nor master exists."""
        state, profile = mock_execution_state_factory(code_changes_for_review=None)

        # Mock: both main and master fail, then git diff HEAD succeeds
        fails = MagicMock()
        fails.returncode = 128
        fails.communicate = AsyncMock(return_value=(b"", b"fatal: not found"))

        head_diff = MagicMock()
        head_diff.returncode = 0
        head_diff.communicate = AsyncMock(return_value=(b"local changes", b""))

        mock_create_subprocess.side_effect = [fails, fails, head_diff]

        result = await get_code_changes_for_review(state, profile)

        assert result == "local changes"
        # Last call should be git diff HEAD
        last_call = mock_create_subprocess.call_args_list[-1]
        assert last_call == call(
            "git", "diff", "HEAD",
            stdout=-1, stderr=-1, cwd=profile.working_dir,
        )

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_returns_error_message_when_all_diffs_fail(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Returns error message when git diff fails (not a git repo)."""
        state, profile = mock_execution_state_factory(code_changes_for_review=None)

        # Mock: all git commands fail
        fails = MagicMock()
        fails.returncode = 128
        fails.communicate = AsyncMock(
            return_value=(b"", b"fatal: not a git repository")
        )
        mock_create_subprocess.return_value = fails

        result = await get_code_changes_for_review(state, profile)

        assert result == "Error getting git diff: fatal: not a git repository"

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_returns_error_message_when_subprocess_raises_exception(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Returns error message when subprocess raises exception."""
        state, profile = mock_execution_state_factory(code_changes_for_review=None)

        mock_create_subprocess.side_effect = FileNotFoundError("git command not found")

        result = await get_code_changes_for_review(state, profile)

        assert result == "Failed to execute git diff: git command not found"

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_handles_empty_git_diff_output(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Handles empty git diff output (no changes anywhere)."""
        state, profile = mock_execution_state_factory(code_changes_for_review=None)

        # All diffs return empty
        empty = MagicMock()
        empty.returncode = 0
        empty.communicate = AsyncMock(return_value=(b"", b""))

        # merge-base fails, git diff HEAD returns empty
        fails = MagicMock()
        fails.returncode = 128
        fails.communicate = AsyncMock(return_value=(b"", b"not found"))

        # Sequence: merge-base main fails, merge-base master fails, git diff HEAD empty,
        # git rev-list @{upstream} fails (no upstream), git diff HEAD~1 empty
        mock_create_subprocess.side_effect = [fails, fails, empty, fails, empty]

        result = await get_code_changes_for_review(state, profile)

        assert result == ""

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_handles_empty_string_in_state(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Empty string in state is treated as falsy, triggers git diff."""
        state, profile = mock_execution_state_factory(code_changes_for_review="")

        # Mock: merge-base fails, git diff HEAD returns output
        fails = MagicMock()
        fails.returncode = 128
        fails.communicate = AsyncMock(return_value=(b"", b"not found"))

        succeeds = MagicMock()
        succeeds.returncode = 0
        succeeds.communicate = AsyncMock(return_value=(b"git output", b""))

        mock_create_subprocess.side_effect = [fails, fails, succeeds]

        result = await get_code_changes_for_review(state, profile)

        assert result == "git output"

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_uses_profile_working_dir_for_all_git_commands(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Verify all git commands are run in profile.working_dir."""
        state, profile = mock_execution_state_factory(code_changes_for_review=None)

        merge_base_process = MagicMock()
        merge_base_process.returncode = 0
        merge_base_process.communicate = AsyncMock(return_value=(b"abc123\n", b""))

        diff_process = MagicMock()
        diff_process.returncode = 0
        diff_process.communicate = AsyncMock(return_value=(b"diff output", b""))

        mock_create_subprocess.side_effect = [merge_base_process, diff_process]

        await get_code_changes_for_review(state, profile)

        # Verify cwd parameter was passed to all subprocess calls
        for call_args in mock_create_subprocess.call_args_list:
            assert call_args.kwargs.get("cwd") == profile.working_dir

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_uses_last_commit_when_no_upstream(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Falls back to HEAD~1 diff when no upstream tracking branch exists."""
        state, profile = mock_execution_state_factory(code_changes_for_review=None)

        # Sequence: merge-base main fails, merge-base master fails,
        # git diff HEAD empty, git rev-list @{upstream} fails (no upstream),
        # git diff HEAD~1 returns the committed change
        merge_base_fails = MagicMock()
        merge_base_fails.returncode = 128
        merge_base_fails.communicate = AsyncMock(return_value=(b"", b"not found"))

        diff_head_empty = MagicMock()
        diff_head_empty.returncode = 0
        diff_head_empty.communicate = AsyncMock(return_value=(b"", b""))

        upstream_fails = MagicMock()
        upstream_fails.returncode = 128
        upstream_fails.communicate = AsyncMock(return_value=(b"", b"no upstream"))

        diff_last_commit = MagicMock()
        diff_last_commit.returncode = 0
        diff_last_commit.communicate = AsyncMock(return_value=(b"committed changes", b""))

        mock_create_subprocess.side_effect = [
            merge_base_fails, merge_base_fails,  # main, master
            diff_head_empty,                     # git diff HEAD
            upstream_fails,                      # git rev-list @{upstream}
            diff_last_commit,                    # git diff HEAD~1
        ]

        result = await get_code_changes_for_review(state, profile)

        assert result == "committed changes"
        # Verify the HEAD~1 diff was called
        last_call = mock_create_subprocess.call_args_list[-1]
        assert last_call == call(
            "git", "diff", "HEAD~1",
            stdout=-1, stderr=-1, cwd=profile.working_dir,
        )

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_uses_unpushed_commits_diff(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Uses diff of unpushed commits when upstream exists but changes uncommitted."""
        state, profile = mock_execution_state_factory(code_changes_for_review=None)

        # Sequence: merge-base main fails, merge-base master fails,
        # git diff HEAD empty (all committed), git rev-list @{upstream}..HEAD returns 2,
        # git diff HEAD~2 returns the committed changes
        merge_base_fails = MagicMock()
        merge_base_fails.returncode = 128
        merge_base_fails.communicate = AsyncMock(return_value=(b"", b"not found"))

        diff_head_empty = MagicMock()
        diff_head_empty.returncode = 0
        diff_head_empty.communicate = AsyncMock(return_value=(b"", b""))

        unpushed_count = MagicMock()
        unpushed_count.returncode = 0
        unpushed_count.communicate = AsyncMock(return_value=(b"2\n", b""))

        diff_unpushed = MagicMock()
        diff_unpushed.returncode = 0
        diff_unpushed.communicate = AsyncMock(return_value=(b"two unpushed commits", b""))

        mock_create_subprocess.side_effect = [
            merge_base_fails, merge_base_fails,  # main, master
            diff_head_empty,                     # git diff HEAD
            unpushed_count,                      # git rev-list @{upstream}..HEAD
            diff_unpushed,                       # git diff HEAD~2
        ]

        result = await get_code_changes_for_review(state, profile)

        assert result == "two unpushed commits"
        # Verify the HEAD~2 diff was called
        last_call = mock_create_subprocess.call_args_list[-1]
        assert last_call == call(
            "git", "diff", "HEAD~2",
            stdout=-1, stderr=-1, cwd=profile.working_dir,
        )
