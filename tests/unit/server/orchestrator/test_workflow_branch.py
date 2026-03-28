"""Unit tests for workflow branch creation logic."""

from unittest.mock import AsyncMock, patch

import pytest

from amelia.server.orchestrator.service import OrchestratorService


@pytest.fixture(autouse=True)
def mock_setup_workflow_branch():
    """Override conftest autouse mock — this module tests the real function."""
    yield


class TestSetupWorkflowBranch:
    """Tests for OrchestratorService._setup_workflow_branch."""

    @patch("amelia.tools.git_utils.checkout_branch", new_callable=AsyncMock)
    @patch("amelia.tools.git_utils.create_and_checkout_branch", new_callable=AsyncMock)
    @patch("amelia.tools.git_utils.has_uncommitted_changes", new_callable=AsyncMock, return_value=False)
    @patch("amelia.tools.git_utils.get_current_branch", new_callable=AsyncMock, return_value="main")
    async def test_creates_amelia_branch_from_default(
        self,
        mock_get_branch: AsyncMock,
        mock_dirty: AsyncMock,
        mock_create: AsyncMock,
        mock_checkout: AsyncMock,
    ) -> None:
        """On a default branch, auto-creates amelia/<issue-id>."""
        result = await OrchestratorService._setup_workflow_branch("/repo", "ISSUE-123", None)
        assert result == "amelia/ISSUE-123"
        mock_create.assert_awaited_once_with("/repo", "amelia/ISSUE-123")
        mock_checkout.assert_awaited_once_with("/repo", "main")

    @patch("amelia.tools.git_utils.checkout_branch", new_callable=AsyncMock)
    @patch("amelia.tools.git_utils.create_and_checkout_branch", new_callable=AsyncMock)
    @patch("amelia.tools.git_utils.has_uncommitted_changes", new_callable=AsyncMock, return_value=False)
    @patch("amelia.tools.git_utils.get_current_branch", new_callable=AsyncMock, return_value="main")
    async def test_creates_custom_branch_when_specified(
        self,
        mock_get_branch: AsyncMock,
        mock_dirty: AsyncMock,
        mock_create: AsyncMock,
        mock_checkout: AsyncMock,
    ) -> None:
        """When --branch my-branch is passed, creates that branch."""
        result = await OrchestratorService._setup_workflow_branch("/repo", "ISSUE-123", "my-feature")
        assert result == "my-feature"
        mock_create.assert_awaited_once_with("/repo", "my-feature")
        mock_checkout.assert_awaited_once_with("/repo", "main")

    @patch("amelia.tools.git_utils.has_uncommitted_changes", new_callable=AsyncMock, return_value=False)
    @patch("amelia.tools.git_utils.get_current_branch", new_callable=AsyncMock, return_value="feat/existing")
    async def test_uses_current_branch_when_empty_string(
        self,
        mock_get_branch: AsyncMock,
        mock_dirty: AsyncMock,
    ) -> None:
        """When --branch '' is passed, uses current branch as-is."""
        result = await OrchestratorService._setup_workflow_branch("/repo", "ISSUE-123", "")
        assert result == "feat/existing"

    @patch("amelia.tools.git_utils.has_uncommitted_changes", new_callable=AsyncMock, return_value=False)
    @patch("amelia.tools.git_utils.get_current_branch", new_callable=AsyncMock, return_value="feat/my-feature")
    async def test_rejects_non_default_branch_without_override(
        self,
        mock_get_branch: AsyncMock,
        mock_dirty: AsyncMock,
    ) -> None:
        """On a non-default branch without --branch, raises ValueError."""
        with pytest.raises(ValueError, match="non-default branch 'feat/my-feature'"):
            await OrchestratorService._setup_workflow_branch("/repo", "ISSUE-123", None)

    @patch("amelia.tools.git_utils.get_current_branch", new_callable=AsyncMock, return_value=None)
    async def test_rejects_detached_head(
        self,
        mock_get_branch: AsyncMock,
    ) -> None:
        """In detached HEAD state, raises ValueError."""
        with pytest.raises(ValueError, match="detached HEAD"):
            await OrchestratorService._setup_workflow_branch("/repo", "ISSUE-123", None)

    @patch("amelia.tools.git_utils.has_uncommitted_changes", new_callable=AsyncMock, return_value=True)
    @patch("amelia.tools.git_utils.get_current_branch", new_callable=AsyncMock, return_value="main")
    async def test_rejects_dirty_working_tree(
        self,
        mock_get_branch: AsyncMock,
        mock_dirty: AsyncMock,
    ) -> None:
        """With uncommitted changes, raises ValueError."""
        with pytest.raises(ValueError, match="uncommitted changes"):
            await OrchestratorService._setup_workflow_branch("/repo", "ISSUE-123", None)

    @patch("amelia.tools.git_utils.checkout_branch", new_callable=AsyncMock)
    @patch("amelia.tools.git_utils.create_and_checkout_branch", new_callable=AsyncMock)
    @patch("amelia.tools.git_utils.has_uncommitted_changes", new_callable=AsyncMock, return_value=False)
    @patch("amelia.tools.git_utils.get_current_branch", new_callable=AsyncMock, return_value="main")
    async def test_branch_already_exists_error(
        self,
        mock_get_branch: AsyncMock,
        mock_dirty: AsyncMock,
        mock_create: AsyncMock,
        mock_checkout: AsyncMock,
    ) -> None:
        """When branch already exists, raises clear error."""
        mock_create.side_effect = ValueError("Branch 'amelia/ISSUE-123' already exists.")
        with pytest.raises(ValueError, match="already exists"):
            await OrchestratorService._setup_workflow_branch("/repo", "ISSUE-123", None)

    @patch("amelia.tools.git_utils.checkout_branch", new_callable=AsyncMock)
    @patch("amelia.tools.git_utils.create_and_checkout_branch", new_callable=AsyncMock)
    @patch("amelia.tools.git_utils.has_uncommitted_changes", new_callable=AsyncMock, return_value=False)
    @patch("amelia.tools.git_utils.get_current_branch", new_callable=AsyncMock, return_value="develop")
    async def test_develop_is_default_branch(
        self,
        mock_get_branch: AsyncMock,
        mock_dirty: AsyncMock,
        mock_create: AsyncMock,
        mock_checkout: AsyncMock,
    ) -> None:
        """'develop' should be treated as a default branch."""
        result = await OrchestratorService._setup_workflow_branch("/repo", "ISSUE-123", None)
        assert result == "amelia/ISSUE-123"
