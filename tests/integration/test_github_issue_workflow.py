"""Integration tests for creating workflows with GitHub tracker profiles.

Verifies that:
- Omitting task_title fetches the issue from GitHub via the tracker
- Providing task_title skips the tracker fetch (used when the frontend
  already has the issue data from the combobox selection)

Mock boundaries:
- create_tracker: Returns mock tracker that returns Issue (no real GitHub calls)
- create_implementation_graph: Returns mock graph (no real LLM calls)

Real components:
- FastAPI route handlers
- OrchestratorService (including _prepare_workflow_state)
- WorkflowRepository with PostgreSQL test database
- Request/Response model validation
- Profile resolution
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import status

from amelia.core.types import AgentConfig, Issue, Profile
from amelia.server.database.profile_repository import ProfileRepository
from amelia.server.database.repository import WorkflowRepository


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def github_worktree(tmp_path: Path) -> str:
    """Create a valid git worktree with a GitHub tracker profile."""
    worktree = tmp_path / "github-worktree"
    worktree.mkdir()
    (worktree / ".git").mkdir()

    settings_content = """
active_profile: github-project
profiles:
  github-project:
    name: github-project
    driver: claude
    model: sonnet
    validator_model: sonnet
    tracker: github
    strategy: single
"""
    (worktree / "settings.amelia.yaml").write_text(settings_content)
    return str(worktree)


@pytest.fixture
async def active_github_profile(
    test_profile_repository: ProfileRepository,
    github_worktree: str,
) -> Profile:
    """Create and activate a GitHub tracker profile in the database."""
    agent_config = AgentConfig(driver="claude", model="sonnet")
    profile = Profile(
        name="github-project",
        tracker="github",
        repo_root=github_worktree,
        agents={
            "architect": agent_config,
            "developer": agent_config,
            "reviewer": agent_config,
            "plan_validator": agent_config,
            "evaluator": agent_config,
            "task_reviewer": agent_config,
        },
    )
    await test_profile_repository.create_profile(profile)
    await test_profile_repository.set_active("github-project")
    return profile


@pytest.fixture
def test_client(orchestrator_test_client: httpx.AsyncClient) -> httpx.AsyncClient:
    """Alias shared orchestrator_test_client fixture for local use."""
    return orchestrator_test_client


@contextmanager
def mock_github_tracker(
    issue_id: str = "42",
    issue_title: str = "Add logout button to navbar",
    issue_description: str = "Users need a way to log out from the navbar.",
):
    """Mock create_tracker to return a tracker that returns a GitHub issue.

    Mocks at the external boundary: the tracker factory. The real
    OrchestratorService, profile resolution, and state preparation all run.
    """
    mock_tracker = MagicMock()
    mock_tracker.get_issue.return_value = Issue(
        id=issue_id,
        title=issue_title,
        description=issue_description,
        status="open",
    )

    with patch(
        "amelia.server.orchestrator.service.create_tracker",
        return_value=mock_tracker,
    ):
        yield mock_tracker


@contextmanager
def mock_graph(langgraph_mock_factory: Any):
    """Patch create_implementation_graph to return a mock graph."""
    mocks = langgraph_mock_factory(astream_items=[])
    with patch(
        "amelia.server.orchestrator.service.create_implementation_graph"
    ) as mock_create_graph:
        mock_create_graph.return_value = mocks.graph
        yield mocks


# =============================================================================
# Tests
# =============================================================================


@pytest.mark.integration
class TestGitHubIssueWorkflowCreation:
    """Tests for creating workflows when profile uses GitHub tracker.

    Verifies both paths: tracker fetch (no task_title) and direct title
    passthrough (task_title provided by the frontend from issue selection).
    """

    async def test_queue_workflow_with_github_tracker_without_task_title(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        active_github_profile: Profile,
        github_worktree: str,
    ) -> None:
        """Queuing a workflow without task_title fetches from GitHub tracker."""
        with mock_github_tracker(issue_id="42") as tracker:
            response = await test_client.post(
                "/api/workflows",
                json={
                    "issue_id": "42",
                    "worktree_path": github_worktree,
                    "profile": "github-project",
                    "start": False,
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        workflow_id = data["id"]

        # Verify the tracker was called to fetch the issue
        tracker.get_issue.assert_called_once_with("42", cwd=github_worktree)

        # Verify workflow was created with the issue from GitHub
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.workflow_status == "pending"
        assert workflow.issue_id == "42"
        assert workflow.issue_cache is not None
        assert workflow.issue_cache["title"] == "Add logout button to navbar"

    async def test_start_workflow_with_github_tracker_without_task_title(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        active_github_profile: Profile,
        github_worktree: str,
        langgraph_mock_factory: Any,
    ) -> None:
        """Starting a workflow immediately without task_title fetches from tracker."""
        with (
            mock_github_tracker(issue_id="99") as tracker,
            mock_graph(langgraph_mock_factory),
        ):
            response = await test_client.post(
                "/api/workflows",
                json={
                    "issue_id": "99",
                    "worktree_path": github_worktree,
                    "profile": "github-project",
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        tracker.get_issue.assert_called_once_with("99", cwd=github_worktree)

    async def test_github_tracker_with_task_title_skips_fetch(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        active_github_profile: Profile,
        github_worktree: str,
    ) -> None:
        """Sending task_title with a GitHub tracker skips the tracker fetch.

        When the frontend already has the issue data (from the combobox),
        it sends task_title/task_description to avoid a redundant server-side fetch.
        """
        with mock_github_tracker(issue_id="42") as tracker:
            response = await test_client.post(
                "/api/workflows",
                json={
                    "issue_id": "42",
                    "worktree_path": github_worktree,
                    "profile": "github-project",
                    "task_title": "Fix login bug",
                    "task_description": "The login page crashes on submit",
                    "start": False,
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        # Tracker should NOT have been called — title was provided directly
        tracker.get_issue.assert_not_called()

        # Verify the workflow uses the provided title/description
        workflow_id = response.json()["id"]
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.issue_cache is not None
        assert workflow.issue_cache["title"] == "Fix login bug"
        assert workflow.issue_cache["description"] == "The login page crashes on submit"

    async def test_github_tracker_with_task_title_only_uses_title_as_description(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        active_github_profile: Profile,
        github_worktree: str,
    ) -> None:
        """When task_description is omitted, description defaults to task_title."""
        with mock_github_tracker() as tracker:
            response = await test_client.post(
                "/api/workflows",
                json={
                    "issue_id": "42",
                    "worktree_path": github_worktree,
                    "profile": "github-project",
                    "task_title": "Add dark mode",
                    "start": False,
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        tracker.get_issue.assert_not_called()

        workflow_id = response.json()["id"]
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.issue_cache is not None
        assert workflow.issue_cache["description"] == "Add dark mode"
