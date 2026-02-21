"""Integration tests for external plan import flow.

Tests the complete external plan lifecycle with real components,
mocking only at the external HTTP boundary (LLM API calls).

Mock boundaries:
- extract_structured: Prevents actual LLM API calls for plan extraction

Real components:
- FastAPI route handlers
- OrchestratorService
- WorkflowRepository with PostgreSQL test database
- ProfileRepository with test profile in database
- Request/Response model validation
- import_external_plan function (except LLM extraction)
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from amelia.agents.schemas.architect import MarkdownPlanOutput
from amelia.core.types import AgentConfig, DriverType, Profile, TrackerType
from amelia.server.database.profile_repository import ProfileRepository
from amelia.server.database.repository import WorkflowRepository
from amelia.server.dependencies import get_orchestrator, get_repository
from amelia.server.main import create_app
from amelia.server.orchestrator.service import OrchestratorService


# =============================================================================
# Fixtures
# =============================================================================

# test_db, test_repository, test_profile_repository, and test_event_bus
# fixtures are inherited from tests/integration/conftest.py


@pytest.fixture
async def setup_test_profile(test_profile_repository: ProfileRepository) -> Profile:
    """Create and activate a test profile in the database.

    This fixture creates a profile with the necessary agent configuration
    for external plan import tests.
    """
    profile = Profile(
        name="test",
        tracker=TrackerType.NOOP,
        repo_root="/tmp/test",  # Will be overridden by worktree_path
        agents={
            "architect": AgentConfig(driver=DriverType.CLI, model="sonnet"),
            "developer": AgentConfig(driver=DriverType.CLI, model="sonnet"),
            "reviewer": AgentConfig(driver=DriverType.CLI, model="sonnet"),
            "plan_validator": AgentConfig(driver=DriverType.CLI, model="haiku"),
        },
    )
    created_profile = await test_profile_repository.create_profile(profile)
    await test_profile_repository.set_active(profile.name)
    return created_profile


@pytest.fixture
def test_client(
    test_orchestrator: OrchestratorService,
    test_repository: WorkflowRepository,
) -> TestClient:
    """Create test client with real dependencies."""
    app = create_app()

    # Create a no-op lifespan that doesn't initialize database/orchestrator
    @asynccontextmanager
    async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
        yield

    app.router.lifespan_context = noop_lifespan
    app.dependency_overrides[get_orchestrator] = lambda: test_orchestrator
    app.dependency_overrides[get_repository] = lambda: test_repository

    # Don't raise server exceptions - let the exception handlers return proper responses
    return TestClient(app, raise_server_exceptions=False)


def create_mock_plan_output(
    goal: str = "Test goal",
    plan_markdown: str = "# Plan\n\n### Task 1: Do thing\n\nDo it.",
    key_files: list[str] | None = None,
) -> MarkdownPlanOutput:
    """Create a mock MarkdownPlanOutput for testing.

    Returns a real Pydantic model instance to match production behavior.
    """
    return MarkdownPlanOutput(
        goal=goal,
        plan_markdown=plan_markdown,
        key_files=key_files or [],
    )


# =============================================================================
# Test Classes
# =============================================================================


@pytest.mark.integration
class TestExternalPlanAtCreation:
    """Tests for external plan at workflow creation time.

    Tests the flow where plan_content is provided in CreateWorkflowRequest.
    """

    async def test_create_workflow_with_plan_content_sets_external_flag(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        setup_test_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Creating workflow with plan_content sets external_plan=True."""
        # Initialize a git repo
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()
        resolved_path = str(git_dir.resolve())

        plan_content = "# Implementation Plan\n\n### Task 1: Do thing\n\nDo it."

        with patch(
            "amelia.pipelines.implementation.external_plan.extract_structured"
        ) as mock_extract:
            mock_extract.return_value = create_mock_plan_output(
                goal="Do thing",
                plan_markdown=plan_content,
                key_files=["test.py"],
            )

            response = test_client.post(
                "/api/workflows",
                json={
                    "issue_id": "TEST-EXT-001",
                    "worktree_path": resolved_path,
                    "start": False,
                    "task_title": "Test task",
                    "plan_content": plan_content,
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        workflow_id = response.json()["id"]

        # Verify workflow was created with external plan flag
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.execution_state is not None
        assert workflow.execution_state.external_plan is True
        assert workflow.execution_state.goal == "Do thing"
        assert workflow.execution_state.plan_markdown == plan_content

    async def test_create_workflow_with_plan_file_sets_external_flag(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        setup_test_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Creating workflow with plan_file reads file and sets external_plan=True."""
        # Initialize a git repo
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()
        resolved_path = str(git_dir.resolve())

        # Create plan file in the git repo
        plan_content = "# Implementation Plan\n\n### Task 1: Create module\n\nCreate it."
        docs_dir = git_dir / "docs"
        docs_dir.mkdir()
        plan_file = docs_dir / "plan.md"
        plan_file.write_text(plan_content)

        with patch(
            "amelia.pipelines.implementation.external_plan.extract_structured"
        ) as mock_extract:
            mock_extract.return_value = create_mock_plan_output(
                goal="Create module",
                plan_markdown=plan_content,
                key_files=["module.py"],
            )

            response = test_client.post(
                "/api/workflows",
                json={
                    "issue_id": "TEST-FILE-001",
                    "worktree_path": resolved_path,
                    "start": False,
                    "task_title": "Test task",
                    "plan_file": "docs/plan.md",  # Relative path
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        workflow_id = response.json()["id"]

        # Verify workflow was created with external plan flag
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.execution_state is not None
        assert workflow.execution_state.external_plan is True
        assert workflow.execution_state.goal == "Create module"

    async def test_create_workflow_without_plan_has_external_flag_false(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        setup_test_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Creating workflow without plan leaves external_plan=False."""
        # Initialize a git repo
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()
        resolved_path = str(git_dir.resolve())

        response = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-NOPLAN-001",
                "worktree_path": resolved_path,
                "start": False,
                "task_title": "Test task",
                # No plan_file or plan_content
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        workflow_id = response.json()["id"]

        # Verify workflow was created without external plan flag
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.execution_state is not None
        assert workflow.execution_state.external_plan is False

    async def test_create_workflow_with_both_plan_file_and_content_returns_422(
        self,
        test_client: TestClient,
        tmp_path: Path,
    ) -> None:
        """Creating workflow with both plan_file and plan_content returns 422."""
        # Initialize a git repo
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()
        resolved_path = str(git_dir.resolve())

        response = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-BOTH-001",
                "worktree_path": resolved_path,
                "start": False,
                "task_title": "Test task",
                "plan_file": "plan.md",
                "plan_content": "# Plan",
            },
        )

        # Request validation should fail
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.integration
class TestSetPlanEndpoint:
    """Tests for POST /api/workflows/{id}/plan endpoint.

    Tests the flow where a plan is set on a queued workflow after creation.
    """

    async def test_set_plan_on_pending_workflow_succeeds(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        setup_test_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Setting plan on pending workflow succeeds and sets external_plan=True."""
        # Initialize a git repo
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()
        resolved_path = str(git_dir.resolve())

        # Create workflow without plan
        response = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-SETPLAN-001",
                "worktree_path": resolved_path,
                "start": False,
                "task_title": "Test task",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        workflow_id = response.json()["id"]

        # Verify workflow starts without external plan
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.execution_state is not None
        assert workflow.execution_state.external_plan is False

        # Now set the plan
        plan_content = "# Plan\n\n### Task 1: Implement feature\n\nDo it."

        with patch(
            "amelia.pipelines.implementation.external_plan.extract_structured"
        ) as mock_extract:
            mock_extract.return_value = create_mock_plan_output(
                goal="Implement feature",
                plan_markdown=plan_content,
                key_files=["feature.py"],
            )

            response = test_client.post(
                f"/api/workflows/{workflow_id}/plan",
                json={"plan_content": plan_content},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["goal"] == "Implement feature"
        assert data["key_files"] == ["feature.py"]
        assert data["total_tasks"] == 1

        # Verify workflow now has external plan
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.execution_state is not None
        assert workflow.execution_state.external_plan is True
        assert workflow.execution_state.goal == "Implement feature"

    async def test_set_plan_on_nonexistent_workflow_returns_404(
        self,
        test_client: TestClient,
    ) -> None:
        """Setting plan on non-existent workflow returns 404."""
        response = test_client.post(
            "/api/workflows/wf-nonexistent/plan",
            json={"plan_content": "# Plan"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_set_plan_without_content_or_file_returns_422(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        setup_test_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Setting plan without plan_content or plan_file returns 422."""
        # Initialize a git repo
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()
        resolved_path = str(git_dir.resolve())

        # Create workflow
        response = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-EMPTY-001",
                "worktree_path": resolved_path,
                "start": False,
                "task_title": "Test task",
            },
        )
        workflow_id = response.json()["id"]

        # Try to set plan with empty body
        response = test_client.post(
            f"/api/workflows/{workflow_id}/plan",
            json={},  # Missing both plan_file and plan_content
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_set_plan_requires_force_when_plan_exists(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        setup_test_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Setting plan on workflow that already has a plan requires force=True."""
        # Initialize a git repo
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()
        resolved_path = str(git_dir.resolve())

        # Create workflow with initial plan
        plan_content = "# Initial Plan\n\n### Task 1: First thing"

        with patch(
            "amelia.pipelines.implementation.external_plan.extract_structured"
        ) as mock_extract:
            mock_extract.return_value = create_mock_plan_output(
                goal="First thing",
                plan_markdown=plan_content,
            )

            response = test_client.post(
                "/api/workflows",
                json={
                    "issue_id": "TEST-FORCE-001",
                    "worktree_path": resolved_path,
                    "start": False,
                    "task_title": "Test task",
                    "plan_content": plan_content,
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        workflow_id = response.json()["id"]

        # Try to set a new plan without force - should fail
        new_plan_content = "# New Plan\n\n### Task 1: Second thing"
        response = test_client.post(
            f"/api/workflows/{workflow_id}/plan",
            json={"plan_content": new_plan_content},  # force defaults to False
        )

        assert response.status_code == status.HTTP_409_CONFLICT

        # Now try with force=True - should succeed
        with patch(
            "amelia.pipelines.implementation.external_plan.extract_structured"
        ) as mock_extract:
            mock_extract.return_value = create_mock_plan_output(
                goal="Second thing",
                plan_markdown=new_plan_content,
            )

            response = test_client.post(
                f"/api/workflows/{workflow_id}/plan",
                json={"plan_content": new_plan_content, "force": True},
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["goal"] == "Second thing"

        # Verify plan was updated
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.execution_state is not None
        assert workflow.execution_state.goal == "Second thing"


@pytest.mark.integration
class TestExternalPlanValidation:
    """Tests for external plan validation and error handling."""

    async def test_set_plan_with_empty_content_returns_error(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        setup_test_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Setting plan with empty content returns validation error."""
        # Initialize a git repo
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()
        resolved_path = str(git_dir.resolve())

        # Create workflow
        response = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-EMPTY-002",
                "worktree_path": resolved_path,
                "start": False,
                "task_title": "Test task",
            },
        )
        workflow_id = response.json()["id"]

        # Try to set plan with whitespace-only content
        response = test_client.post(
            f"/api/workflows/{workflow_id}/plan",
            json={"plan_content": "   \n\n   "},
        )

        # Should fail validation (empty plan) with 400 Bad Request
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    async def test_set_plan_with_nonexistent_file_returns_error(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        setup_test_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Setting plan with non-existent file path returns error."""
        # Initialize a git repo
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()
        resolved_path = str(git_dir.resolve())

        # Create workflow
        response = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-NOFILE-001",
                "worktree_path": resolved_path,
                "start": False,
                "task_title": "Test task",
            },
        )
        workflow_id = response.json()["id"]

        # Try to set plan with non-existent file
        response = test_client.post(
            f"/api/workflows/{workflow_id}/plan",
            json={"plan_file": "nonexistent/plan.md"},
        )

        # Should fail because file doesn't exist with 404 Not Found
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.integration
class TestExternalPlanTaskCount:
    """Tests for task count extraction from external plans."""

    async def test_plan_with_multiple_tasks_counts_correctly(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        setup_test_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """External plan with multiple tasks has correct total_tasks count."""
        # Initialize a git repo
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()
        resolved_path = str(git_dir.resolve())

        # Plan with 3 tasks
        plan_content = """# Implementation Plan

### Task 1: Create models

Create the data models.

### Task 2: Add routes

Add the API routes.

### Task 3: Write tests

Write unit tests.
"""

        with patch(
            "amelia.pipelines.implementation.external_plan.extract_structured"
        ) as mock_extract:
            mock_extract.return_value = create_mock_plan_output(
                goal="Implement feature with models, routes, and tests",
                plan_markdown=plan_content,
                key_files=["models.py", "routes.py", "test_feature.py"],
            )

            response = test_client.post(
                "/api/workflows",
                json={
                    "issue_id": "TEST-TASKS-001",
                    "worktree_path": resolved_path,
                    "start": False,
                    "task_title": "Test task",
                    "plan_content": plan_content,
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        workflow_id = response.json()["id"]

        # Verify task count
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.execution_state is not None
        assert workflow.execution_state.total_tasks == 3
