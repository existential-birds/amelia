"""Unit tests for OrchestratorService.set_workflow_plan."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.server.database.repository import WorkflowRepository
from amelia.server.exceptions import (
    InvalidStateError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.server.models.state import WorkflowStatus
from amelia.server.orchestrator.service import OrchestratorService


class TestSetWorkflowPlan:
    """Tests for set_workflow_plan method."""

    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        """Create mock repository."""
        mock = MagicMock(spec=WorkflowRepository)
        mock.get = AsyncMock()
        mock.update = AsyncMock()
        return mock

    @pytest.fixture
    def mock_orchestrator(self, mock_repository: MagicMock) -> OrchestratorService:
        """Create orchestrator with mocked dependencies."""
        mock_event_bus = MagicMock()
        mock_event_bus.emit = AsyncMock()
        mock_profile_repo = MagicMock()
        mock_profile_repo.get_profile = AsyncMock()

        return OrchestratorService(
            event_bus=mock_event_bus,
            repository=mock_repository,
            profile_repo=mock_profile_repo,
            checkpoint_path="/tmp/checkpoints.db",
        )

    def _create_workflow_mock(
        self,
        workflow_id: str = "wf-001",
        workflow_status: WorkflowStatus = WorkflowStatus.PENDING,
        has_plan: bool = False,
    ) -> MagicMock:
        """Create mock workflow."""
        # Create mock execution state
        mock_execution_state = MagicMock()
        mock_execution_state.profile_id = "test"
        mock_execution_state.plan_markdown = "# Existing plan" if has_plan else None
        mock_execution_state.goal = "Existing goal" if has_plan else None
        mock_execution_state.model_copy = MagicMock(return_value=MagicMock())

        # Create mock workflow
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.issue_id = "TEST-001"
        mock_workflow.worktree_path = "/tmp/worktree"
        mock_workflow.workflow_status = workflow_status
        mock_workflow.execution_state = mock_execution_state
        mock_workflow.model_copy = MagicMock(return_value=MagicMock())

        return mock_workflow

    async def test_set_plan_on_pending_workflow(
        self,
        mock_orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Setting plan on pending workflow succeeds."""
        workflow = self._create_workflow_mock(workflow_status=WorkflowStatus.PENDING)
        mock_repository.get.return_value = workflow

        # Mock profile with required plan_path_pattern
        mock_profile = MagicMock()
        mock_profile.plan_path_pattern = "docs/{issue_key}/plan.md"
        mock_profile.working_dir = str(tmp_path)

        with (
            patch(
                "amelia.server.orchestrator.service.import_external_plan"
            ) as mock_import,
            patch.object(
                mock_orchestrator, "_get_profile_or_fail", new_callable=AsyncMock
            ) as mock_get_profile,
            patch.object(
                mock_orchestrator, "_update_profile_working_dir"
            ) as mock_update_profile,
            patch.object(mock_orchestrator, "_emit", new_callable=AsyncMock),
        ):
            mock_plan_result = MagicMock()
            mock_plan_result.goal = "New goal"
            mock_plan_result.plan_markdown = "# New plan"
            mock_plan_result.plan_path = tmp_path / "plan.md"
            mock_plan_result.key_files = ["file.py"]
            mock_plan_result.total_tasks = 2
            mock_import.return_value = mock_plan_result
            mock_get_profile.return_value = mock_profile
            mock_update_profile.return_value = mock_profile

            result = await mock_orchestrator.set_workflow_plan(
                workflow_id="wf-001",
                plan_content="# New plan",
            )

        assert result["goal"] == "New goal"
        assert result["total_tasks"] == 2
        mock_repository.update.assert_called_once()

    async def test_set_plan_on_planning_workflow(
        self,
        mock_orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Setting plan on planning workflow succeeds and transitions to pending."""
        workflow = self._create_workflow_mock(workflow_status=WorkflowStatus.PLANNING)
        mock_repository.get.return_value = workflow

        mock_profile = MagicMock()
        mock_profile.plan_path_pattern = "docs/{issue_key}/plan.md"
        mock_profile.working_dir = str(tmp_path)

        with (
            patch(
                "amelia.server.orchestrator.service.import_external_plan"
            ) as mock_import,
            patch.object(
                mock_orchestrator, "_get_profile_or_fail", new_callable=AsyncMock
            ) as mock_get_profile,
            patch.object(
                mock_orchestrator, "_update_profile_working_dir"
            ) as mock_update_profile,
            patch.object(mock_orchestrator, "_emit", new_callable=AsyncMock),
        ):
            mock_plan_result = MagicMock()
            mock_plan_result.goal = "New goal"
            mock_plan_result.plan_markdown = "# New plan"
            mock_plan_result.plan_path = tmp_path / "plan.md"
            mock_plan_result.key_files = ["file.py"]
            mock_plan_result.total_tasks = 2
            mock_import.return_value = mock_plan_result
            mock_get_profile.return_value = mock_profile
            mock_update_profile.return_value = mock_profile

            result = await mock_orchestrator.set_workflow_plan(
                workflow_id="wf-001",
                plan_content="# New plan",
            )

        assert result["goal"] == "New goal"
        # Check that model_copy was called with status change
        workflow.model_copy.assert_called()
        call_kwargs = workflow.model_copy.call_args.kwargs
        assert call_kwargs["update"]["workflow_status"] == WorkflowStatus.PENDING

    async def test_set_plan_on_running_workflow_fails(
        self, mock_orchestrator: OrchestratorService, mock_repository: MagicMock
    ) -> None:
        """Setting plan on running workflow raises InvalidStateError."""
        workflow = self._create_workflow_mock(workflow_status=WorkflowStatus.IN_PROGRESS)
        mock_repository.get.return_value = workflow

        with pytest.raises(InvalidStateError, match="pending or planning"):
            await mock_orchestrator.set_workflow_plan(
                workflow_id="wf-001",
                plan_content="# Plan",
            )

    async def test_set_plan_without_force_when_plan_exists_fails(
        self, mock_orchestrator: OrchestratorService, mock_repository: MagicMock
    ) -> None:
        """Setting plan without force when plan exists raises WorkflowConflictError."""
        workflow = self._create_workflow_mock(
            workflow_status=WorkflowStatus.PENDING, has_plan=True
        )
        mock_repository.get.return_value = workflow

        with pytest.raises(WorkflowConflictError, match="Plan already exists"):
            await mock_orchestrator.set_workflow_plan(
                workflow_id="wf-001",
                plan_content="# New plan",
                force=False,
            )

    async def test_set_plan_with_force_overwrites_existing(
        self,
        mock_orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Setting plan with force=True overwrites existing plan."""
        workflow = self._create_workflow_mock(
            workflow_status=WorkflowStatus.PENDING, has_plan=True
        )
        mock_repository.get.return_value = workflow

        mock_profile = MagicMock()
        mock_profile.plan_path_pattern = "docs/{issue_key}/plan.md"
        mock_profile.working_dir = str(tmp_path)

        with (
            patch(
                "amelia.server.orchestrator.service.import_external_plan"
            ) as mock_import,
            patch.object(
                mock_orchestrator, "_get_profile_or_fail", new_callable=AsyncMock
            ) as mock_get_profile,
            patch.object(
                mock_orchestrator, "_update_profile_working_dir"
            ) as mock_update_profile,
            patch.object(mock_orchestrator, "_emit", new_callable=AsyncMock),
        ):
            mock_plan_result = MagicMock()
            mock_plan_result.goal = "New goal"
            mock_plan_result.plan_markdown = "# New plan"
            mock_plan_result.plan_path = tmp_path / "plan.md"
            mock_plan_result.key_files = ["file.py"]
            mock_plan_result.total_tasks = 3
            mock_import.return_value = mock_plan_result
            mock_get_profile.return_value = mock_profile
            mock_update_profile.return_value = mock_profile

            result = await mock_orchestrator.set_workflow_plan(
                workflow_id="wf-001",
                plan_content="# New plan",
                force=True,
            )

        assert result["goal"] == "New goal"
        assert result["total_tasks"] == 3
        mock_repository.update.assert_called_once()

    async def test_set_plan_on_nonexistent_workflow_fails(
        self, mock_orchestrator: OrchestratorService, mock_repository: MagicMock
    ) -> None:
        """Setting plan on nonexistent workflow raises WorkflowNotFoundError."""
        mock_repository.get.return_value = None

        with pytest.raises(WorkflowNotFoundError):
            await mock_orchestrator.set_workflow_plan(
                workflow_id="wf-nonexistent",
                plan_content="# Plan",
            )

    async def test_set_plan_while_architect_running_fails(
        self,
        mock_orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """Setting plan while architect is running raises WorkflowConflictError."""
        workflow = self._create_workflow_mock(workflow_status=WorkflowStatus.PLANNING)
        mock_repository.get.return_value = workflow

        # Simulate an active planning task
        mock_orchestrator._planning_tasks["wf-001"] = MagicMock()

        with pytest.raises(WorkflowConflictError, match="Architect is currently running"):
            await mock_orchestrator.set_workflow_plan(
                workflow_id="wf-001",
                plan_content="# Plan",
            )

    async def test_set_plan_on_blocked_workflow_fails(
        self, mock_orchestrator: OrchestratorService, mock_repository: MagicMock
    ) -> None:
        """Setting plan on blocked workflow raises InvalidStateError."""
        workflow = self._create_workflow_mock(workflow_status=WorkflowStatus.BLOCKED)
        mock_repository.get.return_value = workflow

        with pytest.raises(InvalidStateError, match="pending or planning"):
            await mock_orchestrator.set_workflow_plan(
                workflow_id="wf-001",
                plan_content="# Plan",
            )
