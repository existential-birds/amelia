"""Unit tests for workflow branch creation logic.

These tests patch the git utility functions and call _setup_workflow_branch
directly via a module-level import (not through the class), so the conftest
autouse mock on the class method doesn't interfere.
"""

from unittest.mock import AsyncMock, patch

import pytest

# Import the actual function directly from the module to bypass class-level mock
import amelia.server.orchestrator.service as svc


# Grab reference before conftest mock applies to the class
_setup_workflow_branch = svc.OrchestratorService.__dict__["_setup_workflow_branch"]


async def _call_setup(worktree: str, issue_id: str, branch: str | None) -> str | None:
    """Call the real _setup_workflow_branch."""
    return await _setup_workflow_branch(worktree, issue_id, branch)


class TestSetupWorkflowBranch:
    """Tests for OrchestratorService._setup_workflow_branch."""

    @patch("amelia.tools.git_utils.create_and_checkout_branch", new_callable=AsyncMock)
    @patch("amelia.tools.git_utils.has_uncommitted_changes", new_callable=AsyncMock, return_value=False)
    @patch("amelia.tools.git_utils.get_current_branch", new_callable=AsyncMock, return_value="main")
    async def test_creates_amelia_branch_from_default(
        self,
        mock_get_branch: AsyncMock,
        mock_dirty: AsyncMock,
        mock_checkout: AsyncMock,
    ) -> None:
        """On a default branch, auto-creates amelia/<issue-id>."""
        result = await _call_setup("/repo", "ISSUE-123", None)
        assert result == "amelia/ISSUE-123"
        mock_checkout.assert_awaited_once_with("/repo", "amelia/ISSUE-123")

    @patch("amelia.tools.git_utils.create_and_checkout_branch", new_callable=AsyncMock)
    @patch("amelia.tools.git_utils.has_uncommitted_changes", new_callable=AsyncMock, return_value=False)
    @patch("amelia.tools.git_utils.get_current_branch", new_callable=AsyncMock, return_value="main")
    async def test_creates_custom_branch_when_specified(
        self,
        mock_get_branch: AsyncMock,
        mock_dirty: AsyncMock,
        mock_checkout: AsyncMock,
    ) -> None:
        """When --branch my-branch is passed, creates that branch."""
        result = await _call_setup("/repo", "ISSUE-123", "my-feature")
        assert result == "my-feature"
        mock_checkout.assert_awaited_once_with("/repo", "my-feature")

    @patch("amelia.tools.git_utils.get_current_branch", new_callable=AsyncMock, return_value="feat/existing")
    async def test_uses_current_branch_when_empty_string(
        self,
        mock_get_branch: AsyncMock,
    ) -> None:
        """When --branch '' is passed, uses current branch as-is."""
        result = await _call_setup("/repo", "ISSUE-123", "")
        assert result == "feat/existing"

    @patch("amelia.tools.git_utils.get_current_branch", new_callable=AsyncMock, return_value="feat/my-feature")
    async def test_rejects_non_default_branch_without_override(
        self,
        mock_get_branch: AsyncMock,
    ) -> None:
        """On a non-default branch without --branch, raises ValueError."""
        with pytest.raises(ValueError, match="non-default branch 'feat/my-feature'"):
            await _call_setup("/repo", "ISSUE-123", None)

    @patch("amelia.tools.git_utils.get_current_branch", new_callable=AsyncMock, return_value=None)
    async def test_rejects_detached_head(
        self,
        mock_get_branch: AsyncMock,
    ) -> None:
        """In detached HEAD state, raises ValueError."""
        with pytest.raises(ValueError, match="detached HEAD"):
            await _call_setup("/repo", "ISSUE-123", None)

    @patch("amelia.tools.git_utils.has_uncommitted_changes", new_callable=AsyncMock, return_value=True)
    @patch("amelia.tools.git_utils.get_current_branch", new_callable=AsyncMock, return_value="main")
    async def test_rejects_dirty_working_tree(
        self,
        mock_get_branch: AsyncMock,
        mock_dirty: AsyncMock,
    ) -> None:
        """With uncommitted changes, raises ValueError."""
        with pytest.raises(ValueError, match="uncommitted changes"):
            await _call_setup("/repo", "ISSUE-123", None)

    @patch("amelia.tools.git_utils.create_and_checkout_branch", new_callable=AsyncMock)
    @patch("amelia.tools.git_utils.has_uncommitted_changes", new_callable=AsyncMock, return_value=False)
    @patch("amelia.tools.git_utils.get_current_branch", new_callable=AsyncMock, return_value="main")
    async def test_branch_already_exists_error(
        self,
        mock_get_branch: AsyncMock,
        mock_dirty: AsyncMock,
        mock_checkout: AsyncMock,
    ) -> None:
        """When branch already exists, raises clear error."""
        mock_checkout.side_effect = ValueError("Branch 'amelia/ISSUE-123' already exists.")
        with pytest.raises(ValueError, match="already exists"):
            await _call_setup("/repo", "ISSUE-123", None)

    @patch("amelia.tools.git_utils.create_and_checkout_branch", new_callable=AsyncMock)
    @patch("amelia.tools.git_utils.has_uncommitted_changes", new_callable=AsyncMock, return_value=False)
    @patch("amelia.tools.git_utils.get_current_branch", new_callable=AsyncMock, return_value="develop")
    async def test_develop_is_default_branch(
        self,
        mock_get_branch: AsyncMock,
        mock_dirty: AsyncMock,
        mock_checkout: AsyncMock,
    ) -> None:
        """'develop' should be treated as a default branch."""
        result = await _call_setup("/repo", "ISSUE-123", None)
        assert result == "amelia/ISSUE-123"
