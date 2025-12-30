# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for get_code_changes_for_review function."""

from unittest.mock import AsyncMock, MagicMock, patch

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
    async def test_falls_back_to_git_diff_when_state_empty(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Branch 2: Falls back to git diff HEAD stdout when state has no changes."""
        state, profile = mock_execution_state_factory(code_changes_for_review=None)

        # Mock successful git diff with output
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"diff --git a/file.py\n-old line\n+new line", b"")
        )
        mock_create_subprocess.return_value = mock_process

        result = await get_code_changes_for_review(state, profile)

        assert result == "diff --git a/file.py\n-old line\n+new line"
        mock_create_subprocess.assert_called_once()

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_returns_error_message_when_git_diff_fails(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Branch 3: Returns error message when git diff fails (non-zero exit code)."""
        state, profile = mock_execution_state_factory(code_changes_for_review=None)

        # Mock failed git diff
        mock_process = MagicMock()
        mock_process.returncode = 128
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"fatal: not a git repository")
        )
        mock_create_subprocess.return_value = mock_process

        result = await get_code_changes_for_review(state, profile)

        assert result == "Error getting git diff: fatal: not a git repository"
        mock_create_subprocess.assert_called_once()

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_returns_error_message_when_subprocess_raises_exception(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Branch 4: Returns error message when subprocess raises exception."""
        state, profile = mock_execution_state_factory(code_changes_for_review=None)

        # Mock subprocess raising exception
        mock_create_subprocess.side_effect = FileNotFoundError("git command not found")

        result = await get_code_changes_for_review(state, profile)

        assert result == "Failed to execute git diff: git command not found"
        mock_create_subprocess.assert_called_once()

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_handles_empty_git_diff_output(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Edge case: Handles empty git diff output (no changes)."""
        state, profile = mock_execution_state_factory(code_changes_for_review=None)

        # Mock successful git diff with empty output
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_create_subprocess.return_value = mock_process

        result = await get_code_changes_for_review(state, profile)

        assert result == ""
        mock_create_subprocess.assert_called_once()

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_handles_empty_string_in_state(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Edge case: Empty string in state is treated as falsy, triggers git diff."""
        state, profile = mock_execution_state_factory(code_changes_for_review="")

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"git output", b""))
        mock_create_subprocess.return_value = mock_process

        result = await get_code_changes_for_review(state, profile)

        # Empty string is falsy, should trigger git diff fallback
        assert result == "git output"
        mock_create_subprocess.assert_called_once()

    @patch("amelia.core.orchestrator.asyncio.create_subprocess_exec")
    async def test_uses_profile_working_dir_for_git_diff(
        self, mock_create_subprocess, mock_execution_state_factory
    ):
        """Verify git diff is run in profile.working_dir, not server cwd."""
        state, profile = mock_execution_state_factory(code_changes_for_review=None)

        # Mock successful git diff
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"diff output", b""))
        mock_create_subprocess.return_value = mock_process

        await get_code_changes_for_review(state, profile)

        # Verify cwd parameter was passed to subprocess
        mock_create_subprocess.assert_called_once_with(
            "git", "diff", "HEAD",
            stdout=-1,  # asyncio.subprocess.PIPE
            stderr=-1,  # asyncio.subprocess.PIPE
            cwd=profile.working_dir,
        )
