"""Tests for workflow REST endpoints with token usage data.

These are unit tests that mock the repository to test the route handlers
in isolation. Integration tests with real database are in tests/integration/.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from amelia.pipelines.implementation.state import ImplementationState
from amelia.server.database.repository import WorkflowRepository
from amelia.server.dependencies import get_orchestrator, get_repository
from amelia.server.main import create_app
from amelia.server.models.state import ServerExecutionState
from amelia.server.models.tokens import TokenSummary, TokenUsage

from .conftest import patch_lifespan


# =============================================================================
# Module-level fixtures and helpers
# =============================================================================


@pytest.fixture
def mock_repository() -> MagicMock:
    """Create a mock WorkflowRepository with common methods stubbed."""
    repo = MagicMock(spec=WorkflowRepository)
    repo.get = AsyncMock()
    repo.get_token_summary = AsyncMock()
    repo.get_recent_events = AsyncMock(return_value=[])
    repo.list_workflows = AsyncMock()
    repo.count_workflows = AsyncMock()
    repo.get_token_summaries_batch = AsyncMock()
    repo.list_active = AsyncMock()
    return repo


@pytest.fixture
def mock_orchestrator() -> MagicMock:
    """Create a mock OrchestratorService."""
    return MagicMock()


@pytest.fixture
def test_client(
    mock_repository: MagicMock,
    mock_orchestrator: MagicMock,
) -> TestClient:
    """Create test client with mocked dependencies."""
    app = patch_lifespan(create_app())
    app.dependency_overrides[get_repository] = lambda: mock_repository
    app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator

    return TestClient(app)


def make_workflow(
    workflow_id: str,
    issue_id: str = "TEST-001",
    status: str = "in_progress",
    worktree_path: str | None = None,
) -> ServerExecutionState:
    """Create a test workflow with sensible defaults."""
    return ServerExecutionState(
        id=workflow_id,
        issue_id=issue_id,
        worktree_path=worktree_path or f"/tmp/{workflow_id}",
        workflow_status=status,
        started_at=datetime.now(UTC),
        execution_state=ImplementationState(workflow_id=workflow_id, created_at=datetime.now(UTC), status="running", profile_id="test"),
    )


def make_token_usage(
    workflow_id: str,
    agent: str = "architect",
    input_tokens: int = 1000,
    output_tokens: int = 500,
    cost_usd: float = 0.01,
    duration_ms: int = 5000,
) -> TokenUsage:
    """Create a test TokenUsage record."""
    return TokenUsage(
        workflow_id=workflow_id,
        agent=agent,
        model="claude-sonnet-4-20250514",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=200,
        cache_creation_tokens=0,
        cost_usd=cost_usd,
        duration_ms=duration_ms,
        num_turns=3,
        timestamp=datetime.now(UTC),
    )


# =============================================================================
# Test Classes
# =============================================================================


class TestGetWorkflowTokenUsage:
    """Tests for GET /workflows/{workflow_id} token usage data."""

    async def test_get_workflow_includes_token_summary(
        self,
        test_client: TestClient,
        mock_repository: MagicMock,
    ) -> None:
        """GET /workflows/{id} should include token_usage when data exists."""
        workflow = make_workflow("wf-with-tokens")
        mock_repository.get.return_value = workflow

        # Create token summary
        token_usages = [
            make_token_usage("wf-with-tokens", "architect", 500, 200, 0.005, 3000),
            make_token_usage("wf-with-tokens", "developer", 2000, 1000, 0.025, 10000),
        ]
        token_summary = TokenSummary(
            total_input_tokens=2500,
            total_output_tokens=1200,
            total_cache_read_tokens=400,
            total_cost_usd=0.03,
            total_duration_ms=13000,
            total_turns=6,
            breakdown=token_usages,
        )
        mock_repository.get_token_summary.return_value = token_summary

        response = test_client.get("/api/workflows/wf-with-tokens")

        assert response.status_code == 200
        data = response.json()

        # Verify token_usage is present
        assert "token_usage" in data
        assert data["token_usage"] is not None

        # Verify summary fields
        token_usage = data["token_usage"]
        assert token_usage["total_input_tokens"] == 2500
        assert token_usage["total_output_tokens"] == 1200
        assert token_usage["total_cache_read_tokens"] == 400
        assert token_usage["total_cost_usd"] == pytest.approx(0.03, rel=1e-6)
        assert token_usage["total_duration_ms"] == 13000
        assert token_usage["total_turns"] == 6

        # Verify breakdown is present
        assert "breakdown" in token_usage
        assert len(token_usage["breakdown"]) == 2

        # Verify repository was called correctly
        mock_repository.get_token_summary.assert_awaited_once_with("wf-with-tokens")

    async def test_get_workflow_token_usage_is_none_when_no_data(
        self,
        test_client: TestClient,
        mock_repository: MagicMock,
    ) -> None:
        """GET /workflows/{id} should return null token_usage when no data exists."""
        workflow = make_workflow("wf-no-tokens")
        mock_repository.get.return_value = workflow
        mock_repository.get_token_summary.return_value = None

        response = test_client.get("/api/workflows/wf-no-tokens")

        assert response.status_code == 200
        data = response.json()

        # token_usage should be null when no data
        assert "token_usage" in data
        assert data["token_usage"] is None

    async def test_get_workflow_not_found(
        self,
        test_client: TestClient,
        mock_repository: MagicMock,
    ) -> None:
        """GET /workflows/{id} should return 404 when workflow not found."""
        mock_repository.get.return_value = None

        response = test_client.get("/api/workflows/wf-nonexistent")

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "NOT_FOUND"


class TestListWorkflowsTokenData:
    """Tests for GET /workflows endpoint token data in summaries."""

    async def test_list_workflows_includes_token_data(
        self,
        test_client: TestClient,
        mock_repository: MagicMock,
    ) -> None:
        """GET /workflows should include token data in workflow summaries."""
        # Setup workflows
        workflows = [
            make_workflow("wf-001", "TEST-001", "completed"),
            make_workflow("wf-002", "TEST-002", "completed"),
        ]
        mock_repository.list_workflows.return_value = workflows
        mock_repository.count_workflows.return_value = 2

        # Setup batch token summaries
        mock_repository.get_token_summaries_batch.return_value = {
            "wf-001": TokenSummary(
                total_input_tokens=1000,
                total_output_tokens=500,
                total_cache_read_tokens=200,
                total_cost_usd=0.015,
                total_duration_ms=5000,
                total_turns=3,
                breakdown=[],
            ),
            "wf-002": TokenSummary(
                total_input_tokens=2000,
                total_output_tokens=800,
                total_cache_read_tokens=300,
                total_cost_usd=0.028,
                total_duration_ms=8000,
                total_turns=5,
                breakdown=[],
            ),
        }

        response = test_client.get("/api/workflows")

        assert response.status_code == 200
        data = response.json()

        # Verify workflows have token data
        assert len(data["workflows"]) == 2

        wf1 = data["workflows"][0]
        assert wf1["total_cost_usd"] == pytest.approx(0.015, rel=1e-6)
        assert wf1["total_tokens"] == 1500  # input + output
        assert wf1["total_duration_ms"] == 5000

        wf2 = data["workflows"][1]
        assert wf2["total_cost_usd"] == pytest.approx(0.028, rel=1e-6)
        assert wf2["total_tokens"] == 2800  # input + output
        assert wf2["total_duration_ms"] == 8000

        # Verify batch method was called with correct workflow IDs
        mock_repository.get_token_summaries_batch.assert_awaited_once_with(
            ["wf-001", "wf-002"]
        )

    async def test_list_workflows_handles_missing_token_data(
        self,
        test_client: TestClient,
        mock_repository: MagicMock,
    ) -> None:
        """GET /workflows should handle workflows without token data."""
        workflows = [
            make_workflow("wf-with-data", status="completed"),
            make_workflow("wf-no-data", status="completed"),
        ]
        mock_repository.list_workflows.return_value = workflows
        mock_repository.count_workflows.return_value = 2

        # Setup batch token summaries - one with data, one without
        mock_repository.get_token_summaries_batch.return_value = {
            "wf-with-data": TokenSummary(
                total_input_tokens=1000,
                total_output_tokens=500,
                total_cache_read_tokens=200,
                total_cost_usd=0.015,
                total_duration_ms=5000,
                total_turns=3,
                breakdown=[],
            ),
            "wf-no-data": None,  # No token data for this workflow
        }

        response = test_client.get("/api/workflows")

        assert response.status_code == 200
        data = response.json()

        # Workflow with data should have values
        wf_with_data = next(wf for wf in data["workflows"] if wf["id"] == "wf-with-data")
        assert wf_with_data["total_cost_usd"] == pytest.approx(0.015, rel=1e-6)
        assert wf_with_data["total_tokens"] == 1500
        assert wf_with_data["total_duration_ms"] == 5000

        # Workflow without data should have null values
        wf_no_data = next(wf for wf in data["workflows"] if wf["id"] == "wf-no-data")
        assert wf_no_data["total_cost_usd"] is None
        assert wf_no_data["total_tokens"] is None
        assert wf_no_data["total_duration_ms"] is None

    async def test_list_workflows_empty_list(
        self,
        test_client: TestClient,
        mock_repository: MagicMock,
    ) -> None:
        """GET /workflows with no workflows should return empty list."""
        mock_repository.list_workflows.return_value = []
        mock_repository.count_workflows.return_value = 0
        mock_repository.get_token_summaries_batch.return_value = {}

        response = test_client.get("/api/workflows")

        assert response.status_code == 200
        data = response.json()
        assert data["workflows"] == []
        assert data["total"] == 0


class TestListActiveWorkflowsTokenData:
    """Tests for GET /workflows/active endpoint token data."""

    async def test_list_active_includes_token_data(
        self,
        test_client: TestClient,
        mock_repository: MagicMock,
    ) -> None:
        """GET /workflows/active should include token data in summaries."""
        workflows = [
            make_workflow("wf-active-001", status="in_progress"),
        ]
        mock_repository.list_active.return_value = workflows

        # Setup batch token summaries
        mock_repository.get_token_summaries_batch.return_value = {
            "wf-active-001": TokenSummary(
                total_input_tokens=1500,
                total_output_tokens=700,
                total_cache_read_tokens=300,
                total_cost_usd=0.022,
                total_duration_ms=7000,
                total_turns=4,
                breakdown=[],
            ),
        }

        response = test_client.get("/api/workflows/active")

        assert response.status_code == 200
        data = response.json()

        assert len(data["workflows"]) == 1
        wf = data["workflows"][0]
        assert wf["total_cost_usd"] == pytest.approx(0.022, rel=1e-6)
        assert wf["total_tokens"] == 2200  # 1500 + 700
        assert wf["total_duration_ms"] == 7000

        # Verify batch method was called with correct workflow IDs
        mock_repository.get_token_summaries_batch.assert_awaited_once_with(
            ["wf-active-001"]
        )
