"""Tests for workflow REST endpoints serving history/tokens from trajectories.

These are unit tests that mock the repository/orchestrator to test the route
handlers in isolation. Integration tests with real database are in
tests/integration/.
"""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverUsage
from amelia.server.database.repository import WorkflowRepository
from amelia.server.dependencies import get_orchestrator, get_repository
from amelia.server.main import create_app
from amelia.server.models.state import ServerExecutionState
from amelia.trajectory import WorkflowTrajectoryRecorder

from .conftest import patch_lifespan


@pytest.fixture
def mock_repository() -> MagicMock:
    """Create a mock WorkflowRepository with common methods stubbed."""
    repo = MagicMock(spec=WorkflowRepository)
    repo.get = AsyncMock()
    repo.list_workflows = AsyncMock()
    repo.count_workflows = AsyncMock()
    repo.list_active = AsyncMock()
    return repo


@pytest.fixture
def mock_orchestrator() -> MagicMock:
    """Create a mock OrchestratorService with no live recorder registered."""
    orch = MagicMock()
    orch.get_recorder.return_value = None
    return orch


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
    issue_id: str = "TEST-001",
    status: str = "in_progress",
    worktree_path: str | None = None,
    trajectory_path: str | None = None,
    total_cost_usd: float | None = None,
    total_tokens: int | None = None,
    total_duration_ms: int | None = None,
) -> ServerExecutionState:
    """Create a test workflow with sensible defaults."""
    wf_uuid = uuid4()
    return ServerExecutionState(
        id=wf_uuid,
        issue_id=issue_id,
        worktree_path=worktree_path or f"/tmp/{wf_uuid}",
        workflow_status=status,
        started_at=datetime.now(UTC),
        trajectory_path=trajectory_path,
        total_cost_usd=total_cost_usd,
        total_tokens=total_tokens,
        total_duration_ms=total_duration_ms,
    )


def make_recorder_with_invocation(
    workflow: ServerExecutionState, trajectory_dir: Path
) -> WorkflowTrajectoryRecorder:
    """Create a recorder holding one closed developer invocation."""
    recorder = WorkflowTrajectoryRecorder(
        workflow_id=workflow.id,
        trajectory_dir=trajectory_dir,
        profile_snapshot={"profile_id": "test"},
    )
    inv = recorder.begin_invocation("developer", model="claude-x")
    inv.record_prompt(instructions="You are the developer.", prompt="Fix the bug.")
    inv.record_messages([
        AgenticMessage(
            type=AgenticMessageType.TOOL_CALL,
            tool_name="write_file",
            tool_input={"path": "a.py"},
            tool_call_id="c1",
        ),
        AgenticMessage(
            type=AgenticMessageType.TOOL_RESULT,
            tool_name="write_file",
            tool_output="ok",
            tool_call_id="c1",
        ),
        AgenticMessage(type=AgenticMessageType.RESULT, content="fixed"),
    ])
    inv.close(usage=DriverUsage(input_tokens=10, output_tokens=5), cost_usd=0.01)
    return recorder


class TestGetWorkflowDetail:
    """Tests for GET /workflows/{workflow_id} history and token projection."""

    async def test_active_workflow_projects_from_live_recorder(
        self,
        test_client: TestClient,
        mock_repository: MagicMock,
        mock_orchestrator: MagicMock,
        tmp_path: Path,
    ) -> None:
        """An active workflow's history comes from the in-memory recorder."""
        workflow = make_workflow()
        mock_repository.get.return_value = workflow
        recorder = make_recorder_with_invocation(workflow, tmp_path)
        mock_orchestrator.get_recorder.return_value = recorder

        response = test_client.get(f"/api/workflows/{workflow.id}")

        assert response.status_code == 200
        data = response.json()

        event_types = [e["event_type"] for e in data["recent_events"]]
        assert "claude_tool_call" in event_types
        assert "claude_tool_result" in event_types
        assert "agent_output" in event_types
        tool_event = next(
            e for e in data["recent_events"] if e["event_type"] == "claude_tool_call"
        )
        assert tool_event["agent"] == "developer"
        assert tool_event["tool_name"] == "write_file"

        token_usage = data["token_usage"]
        assert token_usage["total_input_tokens"] == 10
        assert token_usage["total_output_tokens"] == 5
        assert token_usage["total_cost_usd"] == pytest.approx(0.01, rel=1e-6)
        assert [u["agent"] for u in token_usage["breakdown"]] == ["developer"]

        mock_orchestrator.get_recorder.assert_called_once_with(workflow.id)

    async def test_finished_workflow_projects_from_trajectory_file(
        self,
        test_client: TestClient,
        mock_repository: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Without a live recorder, history is loaded from trajectory_path."""
        workflow = make_workflow(status="completed")
        recorder = make_recorder_with_invocation(workflow, tmp_path)
        path = await recorder.finalize(status="completed")
        workflow.trajectory_path = str(path)
        mock_repository.get.return_value = workflow

        response = test_client.get(f"/api/workflows/{workflow.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["recent_events"], "events must be projected from the file"
        assert data["token_usage"]["total_cost_usd"] == pytest.approx(0.01, rel=1e-6)
        assert data["token_usage"]["breakdown"][0]["agent"] == "developer"

    async def test_null_trajectory_path_returns_empty_history(
        self,
        test_client: TestClient,
        mock_repository: MagicMock,
    ) -> None:
        """Legacy/in-flight rows without a trajectory yield empty history."""
        workflow = make_workflow(status="completed", trajectory_path=None)
        mock_repository.get.return_value = workflow

        response = test_client.get(f"/api/workflows/{workflow.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["recent_events"] == []
        assert data["token_usage"] is None

    async def test_unreadable_trajectory_file_returns_500_generic_detail(
        self,
        test_client: TestClient,
        mock_repository: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A non-null path that cannot be read is a 500, never empty history."""
        missing = tmp_path / "gone" / "trajectory.json"
        workflow = make_workflow(status="completed", trajectory_path=str(missing))
        mock_repository.get.return_value = workflow

        response = test_client.get(f"/api/workflows/{workflow.id}")

        assert response.status_code == 500
        detail = response.json()["detail"]
        assert "trajectory" in detail.lower()
        assert str(missing) not in detail

    async def test_corrupt_trajectory_file_returns_500_generic_detail(
        self,
        test_client: TestClient,
        mock_repository: MagicMock,
        tmp_path: Path,
    ) -> None:
        """An invalid trajectory file is a 500, never fabricated history."""
        corrupt = tmp_path / "trajectory.json"
        corrupt.write_text("{not json")
        workflow = make_workflow(status="completed", trajectory_path=str(corrupt))
        mock_repository.get.return_value = workflow

        response = test_client.get(f"/api/workflows/{workflow.id}")

        assert response.status_code == 500
        detail = response.json()["detail"]
        assert "trajectory" in detail.lower()
        assert str(corrupt) not in detail

    async def test_get_workflow_not_found(
        self,
        test_client: TestClient,
        mock_repository: MagicMock,
    ) -> None:
        """GET /workflows/{id} should return 404 when workflow not found."""
        mock_repository.get.return_value = None

        response = test_client.get(f"/api/workflows/{uuid4()}")

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "NOT_FOUND"


class TestListWorkflowsTokenData:
    """Tests for GET /workflows token data sourced from index columns."""

    async def test_list_workflows_includes_token_data(
        self,
        test_client: TestClient,
        mock_repository: MagicMock,
    ) -> None:
        """GET /workflows serves totals from the workflows index columns."""
        wf1 = make_workflow(
            issue_id="TEST-001",
            status="completed",
            total_cost_usd=0.015,
            total_tokens=1500,
            total_duration_ms=5000,
        )
        wf2 = make_workflow(
            issue_id="TEST-002",
            status="completed",
            total_cost_usd=0.028,
            total_tokens=2800,
            total_duration_ms=8000,
        )
        mock_repository.list_workflows.return_value = [wf1, wf2]
        mock_repository.count_workflows.return_value = 2

        response = test_client.get("/api/workflows")

        assert response.status_code == 200
        data = response.json()
        assert len(data["workflows"]) == 2

        wf1_data = data["workflows"][0]
        assert wf1_data["total_cost_usd"] == pytest.approx(0.015, rel=1e-6)
        assert wf1_data["total_tokens"] == 1500
        assert wf1_data["total_duration_ms"] == 5000

        wf2_data = data["workflows"][1]
        assert wf2_data["total_cost_usd"] == pytest.approx(0.028, rel=1e-6)
        assert wf2_data["total_tokens"] == 2800
        assert wf2_data["total_duration_ms"] == 8000

    async def test_list_workflows_handles_missing_token_data(
        self,
        test_client: TestClient,
        mock_repository: MagicMock,
    ) -> None:
        """Workflows without index data return null totals."""
        wf_with = make_workflow(
            status="completed",
            total_cost_usd=0.015,
            total_tokens=1500,
            total_duration_ms=5000,
        )
        wf_without = make_workflow(status="completed")
        mock_repository.list_workflows.return_value = [wf_with, wf_without]
        mock_repository.count_workflows.return_value = 2

        response = test_client.get("/api/workflows")

        assert response.status_code == 200
        data = response.json()

        wf_with_data = next(
            wf for wf in data["workflows"] if wf["id"] == str(wf_with.id)
        )
        assert wf_with_data["total_cost_usd"] == pytest.approx(0.015, rel=1e-6)
        assert wf_with_data["total_tokens"] == 1500
        assert wf_with_data["total_duration_ms"] == 5000

        wf_no_data = next(
            wf for wf in data["workflows"] if wf["id"] == str(wf_without.id)
        )
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

        response = test_client.get("/api/workflows")

        assert response.status_code == 200
        data = response.json()
        assert data["workflows"] == []
        assert data["total"] == 0


class TestListActiveWorkflowsTokenData:
    """Tests for GET /workflows/active token data from index columns."""

    async def test_list_active_includes_token_data(
        self,
        test_client: TestClient,
        mock_repository: MagicMock,
    ) -> None:
        """GET /workflows/active serves totals from the index columns."""
        active_wf = make_workflow(
            status="in_progress",
            total_cost_usd=0.022,
            total_tokens=2200,
            total_duration_ms=7000,
        )
        mock_repository.list_active.return_value = [active_wf]

        response = test_client.get("/api/workflows/active")

        assert response.status_code == 200
        data = response.json()

        assert len(data["workflows"]) == 1
        wf = data["workflows"][0]
        assert wf["total_cost_usd"] == pytest.approx(0.022, rel=1e-6)
        assert wf["total_tokens"] == 2200
        assert wf["total_duration_ms"] == 7000
