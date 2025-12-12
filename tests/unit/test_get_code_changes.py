# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for get_code_changes_for_review function."""

from unittest.mock import MagicMock, patch

from amelia.core.orchestrator import get_code_changes_for_review


class TestGetCodeChangesForReview:
    """Test all branches of get_code_changes_for_review."""

    async def test_returns_state_code_changes_when_present(
        self, mock_execution_state_factory
    ):
        """Branch 1: Returns state.code_changes_for_review when present."""
        state = mock_execution_state_factory(
            code_changes_for_review="diff --git a/file.py\n+new line"
        )

        result = await get_code_changes_for_review(state)

        assert result == "diff --git a/file.py\n+new line"

    @patch("subprocess.run")
    async def test_falls_back_to_git_diff_when_state_empty(
        self, mock_run, mock_execution_state_factory
    ):
        """Branch 2: Falls back to git diff HEAD stdout when state has no changes."""
        state = mock_execution_state_factory(code_changes_for_review=None)

        # Mock successful git diff with output
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = "diff --git a/file.py\n-old line\n+new line"
        mock_run.return_value = mock_process

        result = await get_code_changes_for_review(state)

        assert result == "diff --git a/file.py\n-old line\n+new line"
        mock_run.assert_called_once_with(
            ["git", "diff", "HEAD"],
            capture_output=True,
            text=True,
            check=False
        )

    @patch("subprocess.run")
    async def test_returns_error_message_when_git_diff_fails(
        self, mock_run, mock_execution_state_factory
    ):
        """Branch 3: Returns error message when git diff fails (non-zero exit code)."""
        state = mock_execution_state_factory(code_changes_for_review=None)

        # Mock failed git diff
        mock_process = MagicMock()
        mock_process.returncode = 128
        mock_process.stderr = "fatal: not a git repository"
        mock_run.return_value = mock_process

        result = await get_code_changes_for_review(state)

        assert result == "Error getting git diff: fatal: not a git repository"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    async def test_returns_error_message_when_subprocess_raises_exception(
        self, mock_run, mock_execution_state_factory
    ):
        """Branch 4: Returns error message when subprocess raises exception."""
        state = mock_execution_state_factory(code_changes_for_review=None)

        # Mock subprocess raising exception
        mock_run.side_effect = FileNotFoundError("git command not found")

        result = await get_code_changes_for_review(state)

        assert result == "Failed to execute git diff: git command not found"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    async def test_handles_empty_git_diff_output(
        self, mock_run, mock_execution_state_factory
    ):
        """Edge case: Handles empty git diff output (no changes)."""
        state = mock_execution_state_factory(code_changes_for_review=None)

        # Mock successful git diff with empty output
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = ""
        mock_run.return_value = mock_process

        result = await get_code_changes_for_review(state)

        assert result == ""
        mock_run.assert_called_once()

    async def test_handles_empty_string_in_state(
        self, mock_execution_state_factory
    ):
        """Edge case: Empty string in state is treated as falsy, triggers git diff."""
        state = mock_execution_state_factory(code_changes_for_review="")

        with patch("subprocess.run") as mock_run:
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.stdout = "git output"
            mock_run.return_value = mock_process

            result = await get_code_changes_for_review(state)

            # Empty string is falsy, should trigger git diff fallback
            assert result == "git output"
            mock_run.assert_called_once()
