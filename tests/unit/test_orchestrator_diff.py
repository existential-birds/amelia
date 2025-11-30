from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_get_real_git_diff(mock_execution_state_factory):
    """Tests that get_code_changes_for_review calls git diff correctly."""
    from amelia.core.orchestrator import get_code_changes_for_review

    state = mock_execution_state_factory()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "diff --git a/file.py b/file.py\n..."
        mock_run.return_value.returncode = 0

        diff = await get_code_changes_for_review(state)

        assert "diff --git" in diff
        mock_run.assert_called_with(
            ["git", "diff", "HEAD"],
            capture_output=True,
            text=True,
            check=False
        )
