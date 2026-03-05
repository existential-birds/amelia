"""Unit tests for OrchestratorService.set_workflow_plan."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from amelia.core.types import PlanValidationResult, Severity
from amelia.pipelines.implementation.external_plan import ExternalPlanImportResult
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

    def _make_import_result(
        self,
        goal: str = "Implement feature X",
        plan_markdown: str = "# Plan\n\n### Task 1: Do A\n\n### Task 2: Do B",
        total_tasks: int = 2,
        key_files: list[str] | None = None,
        valid: bool = True,
    ) -> ExternalPlanImportResult:
        """Create a mock ExternalPlanImportResult."""
        return ExternalPlanImportResult(
            goal=goal,
            plan_markdown=plan_markdown,
            plan_path=Path("/tmp/worktree/docs/TEST-001/plan.md"),
            key_files=key_files or [],
            total_tasks=total_tasks,
            validation_result=PlanValidationResult(
                valid=valid,
                issues=[] if valid else ["Missing goal"],
                severity=Severity.NONE if valid else Severity.CRITICAL,
            ),
        )

    async def test_set_plan_returns_ready_status(
        self,
        mock_orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Setting plan on pending workflow returns ready status with goal."""
        workflow = self._create_workflow_mock(workflow_status=WorkflowStatus.PENDING)
        mock_repository.get.return_value = workflow

        mock_profile = MagicMock()
        mock_profile.plan_path_pattern = "docs/{issue_key}/plan.md"
        mock_profile.repo_root = str(tmp_path)

        plan_content = "# Plan\n\n### Task 1: Do A\n\n### Task 2: Do B"
        import_result = self._make_import_result(plan_markdown=plan_content)

        with (
            patch(
                "amelia.server.orchestrator.service.import_external_plan",
                new_callable=AsyncMock,
                return_value=import_result,
            ),
            patch.object(
                mock_orchestrator, "_get_profile_or_fail", new_callable=AsyncMock
            ) as mock_get_profile,
            patch.object(
                mock_orchestrator, "_update_profile_repo_root"
            ) as mock_update_profile,
            patch.object(mock_orchestrator, "_emit", new_callable=AsyncMock),
        ):
            mock_get_profile.return_value = mock_profile
            mock_update_profile.return_value = mock_profile

            result = await mock_orchestrator.set_workflow_plan(
                workflow_id=uuid4(),
                plan_content=plan_content,
            )

        assert result["status"] == "ready"
        assert result["goal"] == "Implement feature X"
        assert result["total_tasks"] == 2
        mock_repository.update_plan_cache.assert_called_once()

    async def test_set_plan_saves_plan_cache_with_goal(
        self,
        mock_orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Setting plan saves PlanCache with goal populated."""
        workflow = self._create_workflow_mock(workflow_status=WorkflowStatus.PENDING)
        mock_repository.get.return_value = workflow

        mock_profile = MagicMock()
        mock_profile.plan_path_pattern = "docs/{issue_key}/plan.md"
        mock_profile.repo_root = str(tmp_path)

        plan_content = "# Plan\n\n### Task 1: Do A"
        import_result = self._make_import_result(
            goal="Do the thing",
            plan_markdown=plan_content,
            total_tasks=1,
        )

        with (
            patch(
                "amelia.server.orchestrator.service.import_external_plan",
                new_callable=AsyncMock,
                return_value=import_result,
            ),
            patch.object(
                mock_orchestrator, "_get_profile_or_fail", new_callable=AsyncMock
            ) as mock_get_profile,
            patch.object(
                mock_orchestrator, "_update_profile_repo_root"
            ) as mock_update_profile,
            patch.object(mock_orchestrator, "_emit", new_callable=AsyncMock),
        ):
            mock_get_profile.return_value = mock_profile
            mock_update_profile.return_value = mock_profile

            await mock_orchestrator.set_workflow_plan(
                workflow_id=uuid4(),
                plan_content=plan_content,
            )

        # Verify plan_cache was saved with goal populated
        call_args = mock_repository.update_plan_cache.call_args
        plan_cache = call_args[0][1]  # second positional arg
        assert plan_cache.goal == "Do the thing"
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
        import_result = self._make_import_result(
            goal="New goal",
            plan_markdown=plan_content,
            total_tasks=3,
        )

        with (
            patch(
                "amelia.server.orchestrator.service.import_external_plan",
                new_callable=AsyncMock,
                return_value=import_result,
            ),
            patch.object(
                mock_orchestrator, "_get_profile_or_fail", new_callable=AsyncMock
            ) as mock_get_profile,
            patch.object(
                mock_orchestrator, "_update_profile_repo_root"
            ) as mock_update_profile,
            patch.object(mock_orchestrator, "_emit", new_callable=AsyncMock),
        ):
            mock_get_profile.return_value = mock_profile
            mock_update_profile.return_value = mock_profile

            result = await mock_orchestrator.set_workflow_plan(
                workflow_id=uuid4(),
                plan_content=plan_content,
                force=True,
            )

        assert result["status"] == "ready"
        assert result["goal"] == "New goal"
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

    async def test_set_plan_emits_validated_event_on_success(
        self,
        mock_orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Setting plan emits PLAN_VALIDATED event when validation passes."""
        workflow = self._create_workflow_mock(workflow_status=WorkflowStatus.PENDING)
        mock_repository.get.return_value = workflow

        mock_profile = MagicMock()
        mock_profile.plan_path_pattern = "docs/{issue_key}/plan.md"
        mock_profile.repo_root = str(tmp_path)

        plan_content = "# Plan\n\n### Task 1: Do A"
        import_result = self._make_import_result(
            plan_markdown=plan_content, total_tasks=1, valid=True
        )

        with (
            patch(
                "amelia.server.orchestrator.service.import_external_plan",
                new_callable=AsyncMock,
                return_value=import_result,
            ),
            patch.object(
                mock_orchestrator, "_get_profile_or_fail", new_callable=AsyncMock
            ) as mock_get_profile,
            patch.object(
                mock_orchestrator, "_update_profile_repo_root"
            ) as mock_update_profile,
            patch.object(
                mock_orchestrator, "_emit", new_callable=AsyncMock
            ) as mock_emit,
        ):
            mock_get_profile.return_value = mock_profile
            mock_update_profile.return_value = mock_profile

            await mock_orchestrator.set_workflow_plan(
                workflow_id=uuid4(),
                plan_content=plan_content,
            )

        # Check that PLAN_VALIDATED was emitted
        from amelia.server.models.events import EventType

        emit_calls = mock_emit.call_args_list
        event_types = [call.args[1] for call in emit_calls]
        assert EventType.PLAN_VALIDATED in event_types

    async def test_set_plan_returns_invalid_status_when_validation_fails(
        self,
        mock_orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Setting plan returns invalid status when validation fails."""
        workflow = self._create_workflow_mock(workflow_status=WorkflowStatus.PENDING)
        mock_repository.get.return_value = workflow

        mock_profile = MagicMock()
        mock_profile.plan_path_pattern = "docs/{issue_key}/plan.md"
        mock_profile.repo_root = str(tmp_path)

        plan_content = "# Plan\n\n### Task 1: Do A"
        import_result = self._make_import_result(
            plan_markdown=plan_content, total_tasks=1, valid=False
        )

        with (
            patch(
                "amelia.server.orchestrator.service.import_external_plan",
                new_callable=AsyncMock,
                return_value=import_result,
            ),
            patch.object(
                mock_orchestrator, "_get_profile_or_fail", new_callable=AsyncMock
            ) as mock_get_profile,
            patch.object(
                mock_orchestrator, "_update_profile_repo_root"
            ) as mock_update_profile,
            patch.object(mock_orchestrator, "_emit", new_callable=AsyncMock),
        ):
            mock_get_profile.return_value = mock_profile
            mock_update_profile.return_value = mock_profile

            result = await mock_orchestrator.set_workflow_plan(
                workflow_id=uuid4(),
                plan_content=plan_content,
            )

        assert result["status"] == "invalid"
        assert "Missing goal" in result["validation_issues"]

    async def test_set_plan_emits_validation_failed_event(
        self,
        mock_orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Setting plan emits PLAN_VALIDATION_FAILED when validation fails."""
        workflow = self._create_workflow_mock(workflow_status=WorkflowStatus.PENDING)
        mock_repository.get.return_value = workflow

        mock_profile = MagicMock()
        mock_profile.plan_path_pattern = "docs/{issue_key}/plan.md"
        mock_profile.repo_root = str(tmp_path)

        plan_content = "# Plan\n\n### Task 1: Do A"
        import_result = self._make_import_result(
            plan_markdown=plan_content, total_tasks=1, valid=False
        )

        with (
            patch(
                "amelia.server.orchestrator.service.import_external_plan",
                new_callable=AsyncMock,
                return_value=import_result,
            ),
            patch.object(
                mock_orchestrator, "_get_profile_or_fail", new_callable=AsyncMock
            ) as mock_get_profile,
            patch.object(
                mock_orchestrator, "_update_profile_repo_root"
            ) as mock_update_profile,
            patch.object(
                mock_orchestrator, "_emit", new_callable=AsyncMock
            ) as mock_emit,
        ):
            mock_get_profile.return_value = mock_profile
            mock_update_profile.return_value = mock_profile

            await mock_orchestrator.set_workflow_plan(
                workflow_id=uuid4(),
                plan_content=plan_content,
            )

        from amelia.server.models.events import EventType

        emit_calls = mock_emit.call_args_list
        event_types = [call.args[1] for call in emit_calls]
        assert EventType.PLAN_VALIDATION_FAILED in event_types
