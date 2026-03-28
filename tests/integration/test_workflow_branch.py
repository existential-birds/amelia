"""Integration tests for workflow branch creation feature.

Tests exercise real service boundaries (API -> Orchestrator -> Repository -> PostgreSQL).
Only external boundaries are mocked: LLM driver, issue tracker, and git operations.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from amelia.core.types import (
    AgentConfig,
    SandboxConfig,
    SandboxMode,
)
from amelia.server.database.profile_repository import ProfileRepository
from amelia.server.database.repository import WorkflowRepository
from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.orchestrator.service import OrchestratorService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def git_mocks():
    """Patch git functions to simulate git state without touching the real tree.

    Returns a dict of mocks keyed by function name. Tests configure return values
    to simulate different git states.
    """
    with (
        patch(
            "amelia.tools.git_utils.get_current_branch",
            new_callable=AsyncMock,
        ) as mock_get_branch,
        patch(
            "amelia.tools.git_utils.create_and_checkout_branch",
            new_callable=AsyncMock,
        ) as mock_create_branch,
        patch(
            "amelia.tools.git_utils.has_uncommitted_changes",
            new_callable=AsyncMock,
        ) as mock_uncommitted,
        patch(
            "amelia.server.orchestrator.service.get_git_head",
            new_callable=AsyncMock,
            return_value="abc123",
        ),
    ):
        # Defaults: on main, clean tree, branch creation succeeds
        mock_get_branch.return_value = "main"
        mock_uncommitted.return_value = False
        mock_create_branch.return_value = None

        yield {
            "get_current_branch": mock_get_branch,
            "create_and_checkout_branch": mock_create_branch,
            "has_uncommitted_changes": mock_uncommitted,
        }


@pytest.fixture
def mock_graph():
    """Mock LangGraph so workflows don't execute the full graph."""
    mock = MagicMock()
    mock.astream = MagicMock(return_value=AsyncMock())
    mock.aget_state = AsyncMock(return_value=MagicMock(values={}, next=[]))
    with patch.object(
        OrchestratorService, "_create_server_graph", return_value=mock
    ):
        yield mock


# =============================================================================
# Orchestrator-level tests
# =============================================================================


@pytest.mark.integration
class TestBranchCreationHappyPath:
    """Tests for successful branch creation during workflow start."""

    async def test_start_workflow_on_main_creates_amelia_branch(
        self,
        test_orchestrator: OrchestratorService,
        active_test_profile,
        valid_worktree: str,
        git_mocks: dict,
        mock_graph,
    ):
        """Starting a workflow on main auto-creates amelia/<issue-id> branch."""
        workflow_id = await test_orchestrator.start_workflow(
            issue_id="ISSUE-42",
            worktree_path=valid_worktree,
            task_title="Test task",
            branch=None,
        )

        git_mocks["create_and_checkout_branch"].assert_called_once_with(
            valid_worktree, "amelia/ISSUE-42"
        )

        # Verify branch persisted in DB
        state = await test_orchestrator._repository.get(workflow_id)
        assert state is not None
        assert state.branch == "amelia/ISSUE-42"

    async def test_queue_workflow_creates_branch_and_persists(
        self,
        test_orchestrator: OrchestratorService,
        active_test_profile,
        valid_worktree: str,
        git_mocks: dict,
    ):
        """queue_workflow also creates branch and persists it in DB."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-77",
            worktree_path=valid_worktree,
            task_title="Queued task",
            start=False,
        )

        workflow_id = await test_orchestrator.queue_workflow(request)

        git_mocks["create_and_checkout_branch"].assert_called_once_with(
            valid_worktree, "amelia/ISSUE-77"
        )

        state = await test_orchestrator._repository.get(workflow_id)
        assert state is not None
        assert state.branch == "amelia/ISSUE-77"


@pytest.mark.integration
class TestBranchOverrides:
    """Tests for --branch flag overrides."""

    async def test_empty_branch_uses_current_branch(
        self,
        test_orchestrator: OrchestratorService,
        active_test_profile,
        valid_worktree: str,
        git_mocks: dict,
        mock_graph,
    ):
        """--branch '' uses current branch as-is, no new branch created."""
        git_mocks["get_current_branch"].return_value = "feat/existing"

        workflow_id = await test_orchestrator.start_workflow(
            issue_id="ISSUE-50",
            worktree_path=valid_worktree,
            task_title="Test task",
            branch="",
        )

        git_mocks["create_and_checkout_branch"].assert_not_called()

        state = await test_orchestrator._repository.get(workflow_id)
        assert state is not None
        assert state.branch == "feat/existing"

    async def test_custom_branch_name(
        self,
        test_orchestrator: OrchestratorService,
        active_test_profile,
        valid_worktree: str,
        git_mocks: dict,
        mock_graph,
    ):
        """--branch 'custom-name' creates that branch instead of auto-generated."""
        workflow_id = await test_orchestrator.start_workflow(
            issue_id="ISSUE-60",
            worktree_path=valid_worktree,
            task_title="Test task",
            branch="custom-name",
        )

        git_mocks["create_and_checkout_branch"].assert_called_once_with(
            valid_worktree, "custom-name"
        )

        state = await test_orchestrator._repository.get(workflow_id)
        assert state is not None
        assert state.branch == "custom-name"


@pytest.mark.integration
class TestBranchValidationErrors:
    """Tests for branch validation failures."""

    async def test_rejects_non_default_branch_without_override(
        self,
        test_orchestrator: OrchestratorService,
        active_test_profile,
        valid_worktree: str,
        git_mocks: dict,
    ):
        """Raises ValueError when on non-default branch without --branch."""
        git_mocks["get_current_branch"].return_value = "feat/something"

        with pytest.raises(ValueError, match="non-default branch"):
            await test_orchestrator.start_workflow(
                issue_id="ISSUE-70",
                worktree_path=valid_worktree,
                task_title="Test task",
                branch=None,
            )

        git_mocks["create_and_checkout_branch"].assert_not_called()

    async def test_rejects_dirty_working_tree(
        self,
        test_orchestrator: OrchestratorService,
        active_test_profile,
        valid_worktree: str,
        git_mocks: dict,
    ):
        """Raises ValueError when working tree has uncommitted changes."""
        git_mocks["has_uncommitted_changes"].return_value = True

        with pytest.raises(ValueError, match="uncommitted changes"):
            await test_orchestrator.start_workflow(
                issue_id="ISSUE-80",
                worktree_path=valid_worktree,
                task_title="Test task",
                branch=None,
            )

    async def test_rejects_detached_head(
        self,
        test_orchestrator: OrchestratorService,
        active_test_profile,
        valid_worktree: str,
        git_mocks: dict,
    ):
        """Raises ValueError when in detached HEAD state."""
        git_mocks["get_current_branch"].return_value = None

        with pytest.raises(ValueError, match="detached HEAD"):
            await test_orchestrator.start_workflow(
                issue_id="ISSUE-90",
                worktree_path=valid_worktree,
                task_title="Test task",
                branch=None,
            )

    async def test_branch_already_exists_error(
        self,
        test_orchestrator: OrchestratorService,
        active_test_profile,
        valid_worktree: str,
        git_mocks: dict,
    ):
        """Raises ValueError when branch already exists."""
        git_mocks["create_and_checkout_branch"].side_effect = ValueError(
            "Branch 'amelia/ISSUE-42' already exists"
        )

        with pytest.raises(ValueError, match="already exists"):
            await test_orchestrator.start_workflow(
                issue_id="ISSUE-42",
                worktree_path=valid_worktree,
                task_title="Test task",
                branch=None,
            )


@pytest.mark.integration
class TestSandboxSkipsBranch:
    """Tests that sandbox profiles skip branch creation."""

    async def test_daytona_sandbox_skips_branch_creation(
        self,
        test_orchestrator: OrchestratorService,
        test_profile_repository: ProfileRepository,
        valid_worktree: str,
        git_mocks: dict,
        mock_graph,
    ):
        """Sandbox profiles (daytona) skip branch creation entirely."""
        from amelia.core.types import Profile  # noqa: PLC0415

        agent_config = AgentConfig(driver="claude", model="sonnet")
        sandbox_profile = Profile(
            name="test",
            tracker="noop",
            repo_root=valid_worktree,
            sandbox=SandboxConfig(
                mode=SandboxMode.DAYTONA,
                repo_url="https://github.com/test/repo.git",
                network_allowlist_enabled=False,
            ),
            agents={
                "architect": agent_config,
                "developer": agent_config,
                "reviewer": agent_config,
                "plan_validator": agent_config,
                "evaluator": agent_config,
                "task_reviewer": agent_config,
            },
        )
        await test_profile_repository.create_profile(sandbox_profile)
        await test_profile_repository.set_active("test")

        workflow_id = await test_orchestrator.start_workflow(
            issue_id="ISSUE-SANDBOX",
            worktree_path=valid_worktree,
            task_title="Sandbox task",
            branch=None,
        )

        # None of the git functions should have been called
        git_mocks["get_current_branch"].assert_not_called()
        git_mocks["create_and_checkout_branch"].assert_not_called()
        git_mocks["has_uncommitted_changes"].assert_not_called()

        state = await test_orchestrator._repository.get(workflow_id)
        assert state is not None
        assert state.branch is None


# =============================================================================
# API endpoint test
# =============================================================================


@pytest.mark.integration
class TestBranchAPIEndpoint:
    """Tests that the API endpoint passes branch through to orchestrator and DB."""

    async def test_post_workflow_with_branch_persists(
        self,
        orchestrator_test_client: httpx.AsyncClient,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        active_test_profile,
        valid_worktree: str,
        git_mocks: dict,
        mock_graph,
    ):
        """POST /api/workflows with branch passes it through to DB."""
        response = await orchestrator_test_client.post(
            "/api/workflows",
            json={
                "issue_id": "ISSUE-99",
                "worktree_path": valid_worktree,
                "task_title": "API test task",
                "start": True,
                "branch": "custom-branch",
            },
        )

        assert response.status_code == 201
        data = response.json()
        workflow_id = uuid.UUID(data["id"])

        git_mocks["create_and_checkout_branch"].assert_called_once_with(
            valid_worktree, "custom-branch"
        )

        state = await test_repository.get(workflow_id)
        assert state is not None
        assert state.branch == "custom-branch"
