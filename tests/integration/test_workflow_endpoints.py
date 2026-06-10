"""Integration tests for workflow API endpoints.

Tests the HTTP layer with real route handlers, real OrchestratorService,
and real WorkflowRepository (PostgreSQL test database). Only mocks at the
LangGraph checkpoint/resume boundary.

Mock boundaries:
- Mock checkpointer: Prevents actual graph execution
- create_implementation_graph: Returns mock graph for approve/reject/cancel

Real components:
- FastAPI route handlers
- OrchestratorService
- WorkflowRepository with PostgreSQL test database
- Request/Response model validation
- Exception handlers
"""

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from fastapi import status

from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverUsage
from amelia.server.database.repository import WorkflowRepository
from amelia.server.models.state import WorkflowStatus
from amelia.trajectory import WorkflowTrajectoryRecorder
from tests.integration.conftest import create_test_workflow


@pytest.fixture
def test_client(orchestrator_test_client: httpx.AsyncClient) -> httpx.AsyncClient:
    """Alias shared orchestrator_test_client fixture for local use."""
    return orchestrator_test_client


@pytest.mark.integration
class TestApproveWorkflowEndpoint:
    """Tests for POST /api/workflows/{id}/approve endpoint.

    Uses real OrchestratorService with mocked LangGraph checkpoint/resume.
    """

    async def test_approve_workflow_returns_200(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        langgraph_mock_factory: Any,
    ) -> None:
        """Successful approval returns 200 with ActionResponse."""
        # Create workflow in "blocked" state (awaiting approval)
        workflow = await create_test_workflow(
            test_repository,
            workflow_status="blocked",
        )

        # Mock LangGraph to prevent actual graph execution
        mocks = langgraph_mock_factory(astream_items=[])
        with patch(
            "amelia.server.orchestrator.runner.create_implementation_graph"
        ) as mock_create_graph:
            mock_create_graph.return_value = mocks.graph

            response = await test_client.post(f"/api/workflows/{workflow.id}/approve")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "approved"
        assert data["workflow_id"] == str(workflow.id)

    async def test_approve_workflow_not_found_returns_404(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Approving non-existent workflow returns 404."""
        fake_id = uuid4()
        response = await test_client.post(f"/api/workflows/{fake_id}/approve")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["code"] == "NOT_FOUND"

    async def test_approve_workflow_invalid_state_returns_422(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Approving workflow not in blocked state returns 422."""
        # Create workflow in "in_progress" state (not awaiting approval)
        workflow = await create_test_workflow(
            test_repository,
            workflow_status="in_progress",
        )

        response = await test_client.post(f"/api/workflows/{workflow.id}/approve")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        assert data["code"] == "INVALID_STATE"
        assert data["details"]["workflow_id"] == str(workflow.id)
        assert data["details"]["current_status"] == "in_progress"


@pytest.mark.integration
class TestRejectWorkflowEndpoint:
    """Tests for POST /api/workflows/{id}/reject endpoint.

    Uses real OrchestratorService with mocked LangGraph checkpoint/resume.
    """

    async def test_reject_workflow_returns_200(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Successful rejection returns 200 with ActionResponse."""
        # Create workflow in "blocked" state
        workflow = await create_test_workflow(
            test_repository,
            workflow_status="blocked",
        )

        response = await test_client.post(
            f"/api/workflows/{workflow.id}/reject",
            json={"feedback": "Please add more tests"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "rejected"
        assert data["workflow_id"] == str(workflow.id)

        # Verify workflow status was updated to failed
        updated = await test_repository.get(workflow.id)
        assert updated is not None
        assert updated.workflow_status == "failed"
        assert updated.failure_reason == "Please add more tests"

    async def test_reject_workflow_not_found_returns_404(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Rejecting non-existent workflow returns 404."""
        fake_id = uuid4()
        response = await test_client.post(
            f"/api/workflows/{fake_id}/reject",
            json={"feedback": "Rejected"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["code"] == "NOT_FOUND"

    async def test_reject_workflow_invalid_state_returns_422(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Rejecting workflow not in blocked state returns 422."""
        # Create workflow in "completed" state
        workflow = await create_test_workflow(
            test_repository,
            workflow_status="completed",
        )

        response = await test_client.post(
            f"/api/workflows/{workflow.id}/reject",
            json={"feedback": "Changes needed"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        assert data["code"] == "INVALID_STATE"

    async def test_reject_workflow_requires_feedback(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Rejection without feedback returns 422 validation error."""
        workflow = await create_test_workflow(
            test_repository,
            workflow_status="blocked",
        )

        response = await test_client.post(
            f"/api/workflows/{workflow.id}/reject",
            json={},  # Missing feedback
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.integration
class TestCancelWorkflowEndpoint:
    """Tests for POST /api/workflows/{id}/cancel endpoint.

    Uses real OrchestratorService with real repository.
    """

    async def test_cancel_workflow_returns_200(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Successful cancellation returns 200 with ActionResponse."""
        # Create workflow in "in_progress" state (cancellable)
        workflow = await create_test_workflow(
            test_repository,
            workflow_status="in_progress",
        )

        response = await test_client.post(f"/api/workflows/{workflow.id}/cancel")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "cancelled"
        assert data["workflow_id"] == str(workflow.id)

        # Verify workflow status was updated
        updated = await test_repository.get(workflow.id)
        assert updated is not None
        assert updated.workflow_status == "cancelled"

    async def test_cancel_workflow_not_found_returns_404(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Cancelling non-existent workflow returns 404."""
        fake_id = uuid4()
        response = await test_client.post(f"/api/workflows/{fake_id}/cancel")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["code"] == "NOT_FOUND"

    @pytest.mark.parametrize(
        "workflow_status",
        ["completed", "failed", "cancelled"],
    )
    async def test_cancel_workflow_terminal_state_returns_422(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        workflow_status: WorkflowStatus,
    ) -> None:
        """Cancelling workflow in terminal state returns 422."""
        workflow = await create_test_workflow(
            test_repository,
            workflow_status=workflow_status,
        )

        response = await test_client.post(f"/api/workflows/{workflow.id}/cancel")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        assert data["code"] == "INVALID_STATE"


@pytest.mark.integration
class TestListWorkflowsEndpoint:
    """Tests for GET /api/workflows endpoint.

    Uses real WorkflowRepository with PostgreSQL test database.
    No LLM mocking needed - only reads from database.
    """

    async def test_list_workflows_returns_200(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Successful list returns 200 with WorkflowListResponse."""
        # Create sample workflows
        await create_test_workflow(
            test_repository, issue_id="TEST-001", worktree_path="/tmp/repo1", workflow_status="pending"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-002", worktree_path="/tmp/repo2", workflow_status="in_progress"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-003", worktree_path="/tmp/repo3", workflow_status="completed"
        )

        response = await test_client.get("/api/workflows")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "workflows" in data
        assert "total" in data
        assert data["total"] == 3
        assert len(data["workflows"]) == 3

        # Verify workflow summaries have required fields
        wf = data["workflows"][0]
        assert "id" in wf
        assert "issue_id" in wf
        assert "status" in wf

    async def test_list_workflows_with_status_filter(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """List with status filter returns only matching workflows."""
        await create_test_workflow(
            test_repository, issue_id="TEST-P1", worktree_path="/tmp/pending1", workflow_status="pending"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-P2", worktree_path="/tmp/pending2", workflow_status="pending"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-C", worktree_path="/tmp/completed", workflow_status="completed"
        )

        response = await test_client.get("/api/workflows?status=pending")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 2
        assert all(wf["status"] == "pending" for wf in data["workflows"])

    async def test_list_workflows_with_worktree_filter(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """List with worktree filter filters by path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Resolve path to canonical form (e.g., /tmp -> /private/tmp on macOS)
            resolved_path = str(Path(tmp_dir).resolve())
            wf1 = await create_test_workflow(
                test_repository, issue_id="TEST-T1", worktree_path=resolved_path, workflow_status="pending"
            )
            await create_test_workflow(
                test_repository, issue_id="TEST-T2", worktree_path="/other/path", workflow_status="pending"
            )

            response = await test_client.get(f"/api/workflows?worktree={tmp_dir}")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            # Should only return workflow matching the worktree
            assert data["total"] == 1
            assert data["workflows"][0]["id"] == str(wf1.id)

    async def test_list_workflows_with_pagination(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """List with limit returns limited results with has_more indicator."""
        # Create 5 workflows
        for i in range(5):
            await create_test_workflow(
                test_repository,
                issue_id=f"TEST-{i}",
                worktree_path=f"/tmp/page{i}",
                workflow_status="pending",
            )

        response = await test_client.get("/api/workflows?limit=2")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["workflows"]) == 2
        assert data["has_more"] is True
        assert data["cursor"] is not None

    async def test_list_workflows_invalid_cursor_returns_400(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Invalid cursor returns 400 error."""
        response = await test_client.get("/api/workflows?cursor=invalid-base64!")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    async def test_list_workflows_empty_returns_empty_list(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """List with no workflows returns empty list."""
        response = await test_client.get("/api/workflows")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["workflows"] == []
        assert data["total"] == 0


@pytest.mark.integration
class TestListActiveWorkflowsEndpoint:
    """Tests for GET /api/workflows/active endpoint.

    Uses real WorkflowRepository with PostgreSQL test database.
    """

    async def test_list_active_returns_200(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Successful list returns 200 with only active workflows."""
        # Create mix of active and terminal workflows
        await create_test_workflow(
            test_repository, issue_id="TEST-A1", worktree_path="/tmp/a1", workflow_status="pending"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-A2", worktree_path="/tmp/a2", workflow_status="in_progress"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-A3", worktree_path="/tmp/a3", workflow_status="blocked"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-D", worktree_path="/tmp/done", workflow_status="completed"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-E", worktree_path="/tmp/err", workflow_status="failed"
        )

        response = await test_client.get("/api/workflows/active")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "workflows" in data
        assert "total" in data
        assert data["total"] == 3  # Only active workflows
        # Verify only active statuses
        statuses = {wf["status"] for wf in data["workflows"]}
        assert statuses <= {"pending", "in_progress", "blocked"}

    async def test_list_active_with_worktree_filter(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """List active with worktree filter filters by path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Resolve path to canonical form (e.g., /tmp -> /private/tmp on macOS)
            resolved_path = str(Path(tmp_dir).resolve())
            wf1 = await create_test_workflow(
                test_repository, issue_id="TEST-WT1", worktree_path=resolved_path, workflow_status="in_progress"
            )
            await create_test_workflow(
                test_repository, issue_id="TEST-WT2", worktree_path="/other/path", workflow_status="pending"
            )

            response = await test_client.get(f"/api/workflows/active?worktree={tmp_dir}")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total"] == 1
            assert data["workflows"][0]["id"] == str(wf1.id)

    async def test_list_active_empty_returns_empty_list(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """List active with no active workflows returns empty list."""
        # Create only terminal workflows
        await create_test_workflow(
            test_repository, issue_id="TEST-C1", worktree_path="/tmp/c1", workflow_status="completed"
        )
        await create_test_workflow(
            test_repository, issue_id="TEST-C2", worktree_path="/tmp/c2", workflow_status="cancelled"
        )

        response = await test_client.get("/api/workflows/active")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["workflows"] == []
        assert data["total"] == 0
        assert data["has_more"] is False


@pytest.mark.integration
class TestGetWorkflowDetailEndpoint:
    """Tests for GET /api/workflows/{id} serving history from trajectories.

    Seeds a real trajectory file plus the trajectory_path index column and
    asserts the detail response projects events/tokens from that file.
    """

    async def test_detail_serves_history_and_tokens_from_trajectory_file(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        tmp_path: Path,
    ) -> None:
        """recent_events and token_usage are projected from the seeded file."""
        workflow = await create_test_workflow(
            test_repository, issue_id="TEST-TRAJ-1", workflow_status="completed"
        )

        recorder = WorkflowTrajectoryRecorder(
            workflow_id=workflow.id,
            trajectory_dir=tmp_path,
            profile_snapshot={"profile_id": "test", "issue_id": "TEST-TRAJ-1"},
        )
        inv = recorder.begin_invocation("developer", model="claude-x")
        inv.record_prompt(instructions="You are the developer.", prompt="Fix the bug.")
        inv.record_messages([
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="write_file",
                tool_input={"path": "a.py", "content": "print('hi')"},
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
        inv.close(
            usage=DriverUsage(input_tokens=10, output_tokens=5), cost_usd=0.01
        )
        path = await recorder.finalize(status="completed")
        await test_repository.set_trajectory_index(
            workflow.id, path, recorder.final_metrics
        )

        response = await test_client.get(f"/api/workflows/{workflow.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        events = data["recent_events"]
        assert events, "history must be projected from the trajectory file"
        event_types = [e["event_type"] for e in events]
        assert "claude_tool_call" in event_types
        assert "claude_tool_result" in event_types
        assert "agent_output" in event_types
        tool_event = next(
            e for e in events if e["event_type"] == "claude_tool_call"
        )
        assert tool_event["agent"] == "developer"
        assert tool_event["tool_name"] == "write_file"

        # Token summary matches the file's subagent final metrics.
        file_data = json.loads(Path(path).read_text())
        file_metrics = file_data["subagent_trajectories"][0]["final_metrics"]
        token_usage = data["token_usage"]
        assert token_usage is not None
        assert token_usage["total_input_tokens"] == file_metrics["total_prompt_tokens"]
        assert token_usage["total_output_tokens"] == file_metrics["total_completion_tokens"]
        assert token_usage["total_cost_usd"] == pytest.approx(
            file_metrics["total_cost_usd"], rel=1e-9
        )
        assert [u["agent"] for u in token_usage["breakdown"]] == ["developer"]

    async def test_detail_with_missing_trajectory_file_returns_500(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        tmp_path: Path,
    ) -> None:
        """A non-null trajectory_path pointing nowhere is a 500 naming the path."""
        workflow = await create_test_workflow(
            test_repository, issue_id="TEST-TRAJ-2", workflow_status="completed"
        )
        missing = tmp_path / str(workflow.id) / "trajectory.json"
        await test_repository.set_trajectory_index(workflow.id, missing, None)

        response = await test_client.get(f"/api/workflows/{workflow.id}")

        assert response.status_code == 500
        assert str(missing) in response.json()["detail"]

    async def test_detail_with_null_trajectory_path_returns_empty_history(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
    ) -> None:
        """Rows without a trajectory yield empty events and no token summary."""
        workflow = await create_test_workflow(
            test_repository, issue_id="TEST-TRAJ-3", workflow_status="completed"
        )

        response = await test_client.get(f"/api/workflows/{workflow.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["recent_events"] == []
        assert data["token_usage"] is None


@pytest.mark.integration
class TestUsageEndpoint:
    """Tests for GET /api/usage aggregating from real trajectory files.

    Exercises the real SQL date filter (``completed_at`` + non-null
    ``trajectory_path``) and the file-based aggregation in one pass.
    """

    @staticmethod
    async def _seed_finished_workflow(
        repository: WorkflowRepository,
        trajectory_dir: Path,
        *,
        issue_id: str,
        completed_at: datetime,
        cost: float,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Create a completed workflow with a finalized trajectory file."""
        workflow = await create_test_workflow(
            repository, issue_id=issue_id, workflow_status="completed"
        )
        workflow.started_at = completed_at - timedelta(minutes=5)
        workflow.completed_at = completed_at
        await repository.update(workflow)

        recorder = WorkflowTrajectoryRecorder(
            workflow_id=workflow.id,
            trajectory_dir=trajectory_dir,
            profile_snapshot={"profile_id": "test", "issue_id": issue_id},
        )
        inv = recorder.begin_invocation("developer", model="claude-x")
        inv.record_prompt(instructions="You are the developer.", prompt="Fix it.")
        inv.record_messages([AgenticMessage(type=AgenticMessageType.RESULT, content="done")])
        inv.close(
            usage=DriverUsage(input_tokens=input_tokens, output_tokens=output_tokens),
            cost_usd=cost,
        )
        path = await recorder.finalize(status="completed")
        await repository.set_trajectory_index(workflow.id, path, recorder.final_metrics)

    async def test_usage_totals_from_trajectory_files_with_date_filter(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        tmp_path: Path,
    ) -> None:
        """Two in-range workflows are summed; out-of-range ones are excluded."""
        await self._seed_finished_workflow(
            test_repository, tmp_path, issue_id="TEST-USAGE-1",
            completed_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            cost=1.0, input_tokens=10, output_tokens=5,
        )
        await self._seed_finished_workflow(
            test_repository, tmp_path, issue_id="TEST-USAGE-2",
            completed_at=datetime(2026, 6, 2, 12, 0, tzinfo=UTC),
            cost=2.0, input_tokens=20, output_tokens=10,
        )
        # In the previous window: feeds the comparison, not the totals.
        await self._seed_finished_workflow(
            test_repository, tmp_path, issue_id="TEST-USAGE-3",
            completed_at=datetime(2026, 5, 29, 12, 0, tzinfo=UTC),
            cost=4.0, input_tokens=40, output_tokens=20,
        )
        # Far outside range and previous window: contributes nothing.
        await self._seed_finished_workflow(
            test_repository, tmp_path, issue_id="TEST-USAGE-4",
            completed_at=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
            cost=8.0, input_tokens=80, output_tokens=40,
        )

        response = await test_client.get("/api/usage?start=2026-06-01&end=2026-06-05")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        summary = data["summary"]
        assert summary["total_cost_usd"] == pytest.approx(3.0)
        assert summary["total_workflows"] == 2
        assert summary["total_tokens"] == 45
        assert summary["total_duration_ms"] == 600_000  # 2 × 5 minutes
        assert summary["previous_period_cost_usd"] == pytest.approx(4.0)
        assert summary["successful_workflows"] == 2
        assert summary["success_rate"] == 1.0

        assert [p["date"] for p in data["trend"]] == ["2026-06-01", "2026-06-02"]
        assert [p["cost_usd"] for p in data["trend"]] == [pytest.approx(1.0), pytest.approx(2.0)]

        assert [m["model"] for m in data["by_model"]] == ["claude-x"]
        assert data["by_model"][0]["workflows"] == 2
        assert data["by_model"][0]["cost_usd"] == pytest.approx(3.0)
        assert data["by_model"][0]["tokens"] == 45
