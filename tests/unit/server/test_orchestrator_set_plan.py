"""Unit tests for OrchestratorService.set_workflow_plan."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

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
        mock.update_plan_cache = AsyncMock()
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
        )

    def _create_workflow_mock(
        self,
        workflow_id: str = "wf-001",
        workflow_status: WorkflowStatus = WorkflowStatus.PENDING,
        has_plan: bool = False,
    ) -> MagicMock:
        """Create mock workflow."""
        # Create mock plan_cache if has_plan is True
        mock_plan_cache = None
        if has_plan:
            mock_plan_cache = MagicMock()
            mock_plan_cache.plan_markdown = "# Existing plan"
            mock_plan_cache.goal = "Existing goal"

        # Create mock workflow
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.issue_id = "TEST-001"
        mock_workflow.profile_id = "test"
        mock_workflow.worktree_path = "/tmp/worktree"
        mock_workflow.workflow_status = workflow_status
        mock_workflow.plan_cache = mock_plan_cache
        mock_workflow.model_copy = MagicMock(return_value=MagicMock())

        return mock_workflow

    async def test_set_plan_returns_validating_status(
        self,
        mock_orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Setting plan on pending workflow returns validating status with task count."""
        workflow = self._create_workflow_mock(workflow_status=WorkflowStatus.PENDING)
        mock_repository.get.return_value = workflow

        # Mock profile with required plan_path_pattern
        mock_profile = MagicMock()
        mock_profile.plan_path_pattern = "docs/{issue_key}/plan.md"
        mock_profile.repo_root = str(tmp_path)

        plan_content = "# Plan\n\n### Task 1: Do A\n\n### Task 2: Do B"

        with (
            patch(
                "amelia.server.orchestrator.service.read_plan_content",
                new_callable=AsyncMock,
            ) as mock_read,
            patch(
                "amelia.server.orchestrator.service.write_plan_to_target",
                new_callable=AsyncMock,
            ),
            patch(
                "amelia.server.orchestrator.service.extract_task_count",
                return_value=2,
            ),
            patch.object(
                mock_orchestrator, "_get_profile_or_fail", new_callable=AsyncMock
            ) as mock_get_profile,
            patch.object(
                mock_orchestrator, "_update_profile_repo_root"
            ) as mock_update_profile,
            patch.object(mock_orchestrator, "_emit", new_callable=AsyncMock),
            patch("asyncio.create_task") as mock_create_task,
        ):
            mock_read.return_value = plan_content
            mock_get_profile.return_value = mock_profile
            mock_update_profile.return_value = mock_profile

            result = await mock_orchestrator.set_workflow_plan(
                workflow_id=uuid4(),
                plan_content=plan_content,
            )

        assert result["status"] == "validating"
        assert result["total_tasks"] == 2
        assert "goal" not in result
        mock_repository.update_plan_cache.assert_called_once()
        # Verify background task was created
        mock_create_task.assert_called_once()

    async def test_set_plan_saves_plan_cache_with_null_goal(
        self,
        mock_orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Setting plan saves PlanCache with goal=None (validating state)."""
        workflow = self._create_workflow_mock(workflow_status=WorkflowStatus.PENDING)
        mock_repository.get.return_value = workflow

        mock_profile = MagicMock()
        mock_profile.plan_path_pattern = "docs/{issue_key}/plan.md"
        mock_profile.repo_root = str(tmp_path)

        plan_content = "# Plan\n\n### Task 1: Do A"

        with (
            patch(
                "amelia.server.orchestrator.service.read_plan_content",
                new_callable=AsyncMock,
            ) as mock_read,
            patch(
                "amelia.server.orchestrator.service.write_plan_to_target",
                new_callable=AsyncMock,
            ),
            patch(
                "amelia.server.orchestrator.service.extract_task_count",
                return_value=1,
            ),
            patch.object(
                mock_orchestrator, "_get_profile_or_fail", new_callable=AsyncMock
            ) as mock_get_profile,
            patch.object(
                mock_orchestrator, "_update_profile_repo_root"
            ) as mock_update_profile,
            patch.object(mock_orchestrator, "_emit", new_callable=AsyncMock),
            patch("asyncio.create_task"),
        ):
            mock_read.return_value = plan_content
            mock_get_profile.return_value = mock_profile
            mock_update_profile.return_value = mock_profile

            await mock_orchestrator.set_workflow_plan(
                workflow_id=uuid4(),
                plan_content=plan_content,
            )

        # Verify plan_cache was saved with goal=None
        call_args = mock_repository.update_plan_cache.call_args
        plan_cache = call_args[0][1]  # second positional arg
        assert plan_cache.goal is None
        assert plan_cache.total_tasks == 1

    async def test_set_plan_on_running_workflow_fails(
        self, mock_orchestrator: OrchestratorService, mock_repository: MagicMock
    ) -> None:
        """Setting plan on running workflow raises InvalidStateError."""
        workflow = self._create_workflow_mock(workflow_status=WorkflowStatus.IN_PROGRESS)
        mock_repository.get.return_value = workflow

        with pytest.raises(InvalidStateError, match="pending"):
            await mock_orchestrator.set_workflow_plan(
                workflow_id=uuid4(),
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
                workflow_id=uuid4(),
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
        mock_profile.repo_root = str(tmp_path)

        plan_content = "# New plan\n\n### Task 1: A\n\n### Task 2: B\n\n### Task 3: C"

        with (
            patch(
                "amelia.server.orchestrator.service.read_plan_content",
                new_callable=AsyncMock,
            ) as mock_read,
            patch(
                "amelia.server.orchestrator.service.write_plan_to_target",
                new_callable=AsyncMock,
            ),
            patch(
                "amelia.server.orchestrator.service.extract_task_count",
                return_value=3,
            ),
            patch.object(
                mock_orchestrator, "_get_profile_or_fail", new_callable=AsyncMock
            ) as mock_get_profile,
            patch.object(
                mock_orchestrator, "_update_profile_repo_root"
            ) as mock_update_profile,
            patch.object(mock_orchestrator, "_emit", new_callable=AsyncMock),
            patch("asyncio.create_task"),
        ):
            mock_read.return_value = plan_content
            mock_get_profile.return_value = mock_profile
            mock_update_profile.return_value = mock_profile

            result = await mock_orchestrator.set_workflow_plan(
                workflow_id=uuid4(),
                plan_content=plan_content,
                force=True,
            )

        assert result["status"] == "validating"
        assert result["total_tasks"] == 3
        mock_repository.update_plan_cache.assert_called_once()

    async def test_set_plan_on_nonexistent_workflow_fails(
        self, mock_orchestrator: OrchestratorService, mock_repository: MagicMock
    ) -> None:
        """Setting plan on nonexistent workflow raises WorkflowNotFoundError."""
        mock_repository.get.return_value = None

        with pytest.raises(WorkflowNotFoundError):
            await mock_orchestrator.set_workflow_plan(
                workflow_id=uuid4(),
                plan_content="# Plan",
            )

    async def test_set_plan_while_architect_running_fails(
        self,
        mock_orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """Setting plan while architect is running raises WorkflowConflictError."""
        workflow = self._create_workflow_mock(workflow_status=WorkflowStatus.PENDING)
        mock_repository.get.return_value = workflow

        # Simulate an active planning task
        wf_id = uuid4()
        mock_orchestrator._planning_tasks[wf_id] = MagicMock()

        with pytest.raises(WorkflowConflictError, match="Architect is currently running"):
            await mock_orchestrator.set_workflow_plan(
                workflow_id=wf_id,
                plan_content="# Plan",
            )

    async def test_set_plan_on_blocked_workflow_fails(
        self, mock_orchestrator: OrchestratorService, mock_repository: MagicMock
    ) -> None:
        """Setting plan on blocked workflow raises InvalidStateError."""
        workflow = self._create_workflow_mock(workflow_status=WorkflowStatus.BLOCKED)
        mock_repository.get.return_value = workflow

        with pytest.raises(InvalidStateError, match="pending"):
            await mock_orchestrator.set_workflow_plan(
                workflow_id=uuid4(),
                plan_content="# Plan",
            )
