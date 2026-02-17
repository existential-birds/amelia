"""Tests for workflow recovery and resume functionality."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI

from amelia.server.exceptions import InvalidStateError, WorkflowNotFoundError
from amelia.server.models.events import EventType
from amelia.server.models.state import (
    VALID_TRANSITIONS,
    InvalidStateTransitionError,
    WorkflowStatus,
    validate_transition,
)
from amelia.server.orchestrator.service import OrchestratorService


class TestValidTransitions:
    """Tests for FAILED -> IN_PROGRESS state transition."""

    def test_valid_transitions_includes_failed_to_in_progress(self) -> None:
        """FAILED -> IN_PROGRESS should be a valid transition for resume."""
        assert WorkflowStatus.IN_PROGRESS in VALID_TRANSITIONS[WorkflowStatus.FAILED]

    def test_failed_to_in_progress_does_not_raise(self) -> None:
        """validate_transition should not raise for FAILED -> IN_PROGRESS."""
        validate_transition(WorkflowStatus.FAILED, WorkflowStatus.IN_PROGRESS)

    def test_failed_to_completed_still_invalid(self) -> None:
        """FAILED -> COMPLETED should remain invalid (only IN_PROGRESS is allowed)."""
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(WorkflowStatus.FAILED, WorkflowStatus.COMPLETED)


@pytest.fixture
def event_bus() -> MagicMock:
    bus = MagicMock()
    bus.emit = MagicMock()
    return bus


@pytest.fixture
def repository() -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_status = AsyncMock(return_value=[])
    repo.set_status = AsyncMock()
    repo.save_event = AsyncMock()
    repo.get_max_event_sequence = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def service(event_bus: MagicMock, repository: AsyncMock) -> OrchestratorService:
    return OrchestratorService(
        event_bus=event_bus,
        repository=repository,
    )


def _make_workflow(
    workflow_id: uuid.UUID | str | None = None,
    status: WorkflowStatus = WorkflowStatus.PENDING,
    worktree_path: str = "/tmp/test-worktree",
) -> MagicMock:
    """Create a mock ServerExecutionState with the given status."""
    if workflow_id is None:
        wf_id = uuid4()
    elif isinstance(workflow_id, uuid.UUID):
        wf_id = workflow_id
    else:
        wf_id = uuid.UUID(workflow_id)
    wf = MagicMock()
    wf.id = wf_id
    wf.issue_id = f"ISSUE-{wf_id}"
    wf.workflow_status = status
    wf.worktree_path = worktree_path
    return wf


class TestRecoverInterruptedWorkflows:
    """Tests for recover_interrupted_workflows()."""

    async def test_recover_in_progress_marks_failed(
        self,
        service: OrchestratorService,
        repository: AsyncMock,
        event_bus: MagicMock,
    ) -> None:
        """IN_PROGRESS workflow should be marked FAILED with recoverable flag."""
        wf = _make_workflow(status=WorkflowStatus.IN_PROGRESS)
        repository.find_by_status = AsyncMock(
            side_effect=lambda statuses: [wf] if WorkflowStatus.IN_PROGRESS in statuses else []
        )

        await service.recover_interrupted_workflows()

        repository.set_status.assert_called_once_with(
            wf.id,
            WorkflowStatus.FAILED,
            failure_reason="Server restarted while workflow was running",
        )
        # Check WORKFLOW_FAILED event was emitted with recoverable=True
        repository.save_event.assert_called()
        saved_event = repository.save_event.call_args[0][0]
        assert saved_event.event_type == EventType.WORKFLOW_FAILED
        assert saved_event.data["recoverable"] is True

    async def test_recover_blocked_restores_approval(
        self,
        service: OrchestratorService,
        repository: AsyncMock,
        event_bus: MagicMock,
    ) -> None:
        """BLOCKED workflow should stay BLOCKED with APPROVAL_REQUIRED re-emitted."""
        wf = _make_workflow(status=WorkflowStatus.BLOCKED)
        repository.find_by_status = AsyncMock(
            side_effect=lambda statuses: [wf] if WorkflowStatus.BLOCKED in statuses else []
        )

        await service.recover_interrupted_workflows()

        # Status should NOT change — no set_status call for BLOCKED
        repository.set_status.assert_not_called()
        # APPROVAL_REQUIRED event should be emitted
        repository.save_event.assert_called()
        saved_event = repository.save_event.call_args[0][0]
        assert saved_event.event_type == EventType.APPROVAL_REQUIRED

    async def test_recover_pending_unchanged(
        self,
        service: OrchestratorService,
        repository: AsyncMock,
    ) -> None:
        """PENDING workflows should not be touched."""
        repository.find_by_status = AsyncMock(return_value=[])

        await service.recover_interrupted_workflows()

        repository.set_status.assert_not_called()

    async def test_recover_no_active_workflows(
        self,
        service: OrchestratorService,
        repository: AsyncMock,
    ) -> None:
        """With no interrupted workflows, just log summary."""
        repository.find_by_status = AsyncMock(return_value=[])

        await service.recover_interrupted_workflows()

        repository.set_status.assert_not_called()
        repository.save_event.assert_not_called()


class TestResumeWorkflow:
    """Tests for resume_workflow()."""

    async def test_resume_validates_failed_status(
        self,
        service: OrchestratorService,
        repository: AsyncMock,
    ) -> None:
        """Resuming a non-FAILED workflow should raise InvalidStateError."""
        wf = _make_workflow(status=WorkflowStatus.IN_PROGRESS)
        repository.get = AsyncMock(return_value=wf)

        with pytest.raises(InvalidStateError, match="must be in 'failed' status"):
            await service.resume_workflow(wf.id)

    async def test_resume_validates_workflow_exists(
        self,
        service: OrchestratorService,
        repository: AsyncMock,
    ) -> None:
        """Resuming a non-existent workflow should raise WorkflowNotFoundError."""
        repository.get = AsyncMock(return_value=None)

        with pytest.raises(WorkflowNotFoundError):
            await service.resume_workflow(uuid4())

    async def test_resume_validates_worktree_available(
        self,
        service: OrchestratorService,
        repository: AsyncMock,
    ) -> None:
        """Resuming when worktree is occupied should raise InvalidStateError."""
        wf = _make_workflow(status=WorkflowStatus.FAILED, worktree_path="/tmp/wt")
        wf.execution_state = MagicMock()
        repository.get = AsyncMock(return_value=wf)

        # Simulate occupied worktree
        service._active_tasks["/tmp/wt"] = ("wf-other", MagicMock())

        # Mock checkpoint validation so it passes (worktree check is after checkpoint)
        mock_state = MagicMock()
        mock_state.values = {"some": "state"}

        mock_graph = MagicMock()
        mock_graph.aget_state = AsyncMock(return_value=mock_state)
        service._create_server_graph = MagicMock(return_value=mock_graph)

        with pytest.raises(InvalidStateError, match="worktree.*occupied"):
            await service.resume_workflow(wf.id)

        # Cleanup
        service._active_tasks.clear()

    async def test_resume_transitions_to_in_progress(
        self,
        service: OrchestratorService,
        repository: AsyncMock,
        event_bus: MagicMock,
    ) -> None:
        """Successful resume should clear error fields and set IN_PROGRESS."""
        wf = _make_workflow(status=WorkflowStatus.FAILED)
        wf.failure_reason = "Server restarted"
        wf.completed_at = datetime(2026, 1, 1, tzinfo=UTC)
        wf.execution_state = MagicMock()
        wf.worktree_path = "/tmp/wt-resume"
        repository.get = AsyncMock(return_value=wf)

        # Mock checkpoint validation
        mock_state = MagicMock()
        mock_state.values = {"some": "state"}

        mock_graph = MagicMock()
        mock_graph.aget_state = AsyncMock(return_value=mock_state)
        service._create_server_graph = MagicMock(return_value=mock_graph)

        service._run_workflow_with_retry = AsyncMock()

        await service.resume_workflow(wf.id)

        # Verify error fields cleared
        assert wf.failure_reason is None
        assert wf.completed_at is None
        assert wf.workflow_status == WorkflowStatus.IN_PROGRESS

        # Verify state was updated in DB
        repository.update.assert_called_once_with(wf)

    async def test_resume_emits_started_event(
        self,
        service: OrchestratorService,
        repository: AsyncMock,
        event_bus: MagicMock,
    ) -> None:
        """Successful resume should emit WORKFLOW_STARTED with resumed=True."""
        wf = _make_workflow(status=WorkflowStatus.FAILED)
        wf.failure_reason = "Server restarted"
        wf.completed_at = None
        wf.execution_state = MagicMock()
        wf.worktree_path = "/tmp/wt-event"
        repository.get = AsyncMock(return_value=wf)

        mock_state = MagicMock()
        mock_state.values = {"some": "state"}

        mock_graph = MagicMock()
        mock_graph.aget_state = AsyncMock(return_value=mock_state)
        service._create_server_graph = MagicMock(return_value=mock_graph)
        service._run_workflow_with_retry = AsyncMock()

        await service.resume_workflow(wf.id)

        # Check WORKFLOW_STARTED event with resumed=True
        saved_events = [c[0][0] for c in repository.save_event.call_args_list]
        started_events = [e for e in saved_events if e.event_type == EventType.WORKFLOW_STARTED]
        assert len(started_events) == 1
        assert started_events[0].data["resumed"] is True


class TestResumeEndpoint:
    """Tests for POST /api/workflows/{id}/resume endpoint."""

    def _get_test_app(self) -> FastAPI:
        """Create a test app with mocked dependencies."""
        from amelia.server.routes.workflows import configure_exception_handlers, router

        app = FastAPI()
        app.include_router(router, prefix="/api")
        configure_exception_handlers(app)

        return app

    async def test_resume_endpoint_success(self) -> None:
        """POST /resume should return 200 with resumed status."""
        from fastapi.testclient import TestClient

        from amelia.server.dependencies import get_orchestrator

        app = self._get_test_app()

        wf_id = uuid4()
        mock_orchestrator = AsyncMock()
        mock_workflow = MagicMock()
        mock_workflow.id = wf_id
        mock_orchestrator.resume_workflow = AsyncMock(return_value=mock_workflow)

        app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator

        client = TestClient(app)
        response = client.post(f"/api/workflows/{wf_id}/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "resumed"
        assert data["workflow_id"] == str(wf_id)

    async def test_resume_endpoint_not_found(self) -> None:
        """POST /resume for missing workflow should return 404."""
        from fastapi.testclient import TestClient

        from amelia.server.dependencies import get_orchestrator

        app = self._get_test_app()

        wf_id = uuid4()
        mock_orchestrator = AsyncMock()
        mock_orchestrator.resume_workflow = AsyncMock(
            side_effect=WorkflowNotFoundError(str(wf_id))
        )

        app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator

        client = TestClient(app)
        response = client.post(f"/api/workflows/{wf_id}/resume")

        assert response.status_code == 404

    async def test_resume_endpoint_conflict(self) -> None:
        """POST /resume for non-FAILED workflow should return 422."""
        from fastapi.testclient import TestClient

        from amelia.server.dependencies import get_orchestrator

        app = self._get_test_app()

        mock_orchestrator = AsyncMock()
        mock_orchestrator.resume_workflow = AsyncMock(
            side_effect=InvalidStateError(
                "Cannot resume",
                workflow_id=uuid4(),
                current_status=WorkflowStatus.IN_PROGRESS,
            )
        )

        app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator

        wf_id = uuid4()
        client = TestClient(app)
        response = client.post(f"/api/workflows/{wf_id}/resume")

        assert response.status_code == 422
