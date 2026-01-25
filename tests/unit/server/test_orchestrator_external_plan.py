"""Unit tests for OrchestratorService external plan handling."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.orchestrator.service import OrchestratorService


class TestQueueWorkflowWithExternalPlan:
    """Tests for queue_workflow with external plan parameters."""

    @pytest.fixture
    def mock_orchestrator(self) -> OrchestratorService:
        """Create orchestrator with mocked dependencies."""
        mock_event_bus = MagicMock()
        mock_event_bus.emit = AsyncMock()
        mock_repository = MagicMock()
        mock_repository.create = AsyncMock()
        mock_repository.add_event = AsyncMock()
        mock_repository.get_max_event_sequence = AsyncMock(return_value=0)
        mock_repository.save_event = AsyncMock()
        mock_profile_repo = MagicMock()

        return OrchestratorService(
            event_bus=mock_event_bus,
            repository=mock_repository,
            profile_repo=mock_profile_repo,
            checkpoint_path="/tmp/checkpoints.db",
        )

    async def test_queue_workflow_with_plan_content_sets_external_flag(
        self, mock_orchestrator: OrchestratorService, tmp_path: Path
    ) -> None:
        """queue_workflow should set external_plan=True when plan_content provided."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / ".git").mkdir()

        request = CreateWorkflowRequest(
            issue_id="TEST-001",
            worktree_path=str(worktree),
            plan_content="# Test Plan\n\n### Task 1: Do thing",
            start=False,
            task_title="Test task",
        )

        with (
            patch.object(
                mock_orchestrator, "_validate_worktree_path", return_value=worktree
            ),
            patch.object(
                mock_orchestrator,
                "_prepare_workflow_state",
            ) as mock_prepare,
            patch(
                "amelia.server.orchestrator.service.import_external_plan"
            ) as mock_import,
            patch(
                "amelia.server.orchestrator.service.ServerExecutionState"
            ) as mock_server_state,
        ):
            mock_state = MagicMock()
            mock_state.external_plan = False
            mock_updated_state = MagicMock(external_plan=True)
            mock_state.model_copy = MagicMock(return_value=mock_updated_state)
            mock_profile = MagicMock()
            mock_profile.plan_path_pattern = "docs/plans/{issue_key}.md"
            mock_profile.working_dir = str(worktree)
            mock_prepare.return_value = (str(worktree), mock_profile, mock_state)
            mock_plan_result = MagicMock()
            mock_plan_result.goal = "Do thing"
            mock_plan_result.plan_markdown = "# Test Plan"
            mock_plan_result.plan_path = tmp_path / "plan.md"
            mock_plan_result.key_files = []
            mock_plan_result.total_tasks = 1
            mock_import.return_value = mock_plan_result
            mock_server_state.return_value = MagicMock()

            await mock_orchestrator.queue_workflow(request)

            mock_import.assert_called_once()
            # Verify import_external_plan was called with expected arguments
            call_kwargs = mock_import.call_args.kwargs
            assert call_kwargs["plan_content"] == "# Test Plan\n\n### Task 1: Do thing"
            assert call_kwargs["plan_file"] is None
            assert call_kwargs["profile"] == mock_profile

            # Verify external_plan flag was set
            mock_state.model_copy.assert_called_once()
            update_kwargs = mock_state.model_copy.call_args.kwargs["update"]
            assert update_kwargs["external_plan"] is True

    async def test_queue_workflow_with_plan_file_calls_import(
        self, mock_orchestrator: OrchestratorService, tmp_path: Path
    ) -> None:
        """queue_workflow should call import_external_plan when plan_file provided."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / ".git").mkdir()

        request = CreateWorkflowRequest(
            issue_id="TEST-002",
            worktree_path=str(worktree),
            plan_file="external-plan.md",
            start=False,
            task_title="Test task",
        )

        with (
            patch.object(
                mock_orchestrator, "_validate_worktree_path", return_value=worktree
            ),
            patch.object(
                mock_orchestrator,
                "_prepare_workflow_state",
            ) as mock_prepare,
            patch(
                "amelia.server.orchestrator.service.import_external_plan"
            ) as mock_import,
            patch(
                "amelia.server.orchestrator.service.ServerExecutionState"
            ) as mock_server_state,
        ):
            mock_state = MagicMock()
            mock_state.external_plan = False
            mock_updated_state = MagicMock(external_plan=True)
            mock_state.model_copy = MagicMock(return_value=mock_updated_state)
            mock_profile = MagicMock()
            mock_profile.plan_path_pattern = "docs/plans/{issue_key}.md"
            mock_profile.working_dir = str(worktree)
            mock_prepare.return_value = (str(worktree), mock_profile, mock_state)
            mock_plan_result = MagicMock()
            mock_plan_result.goal = "Do thing"
            mock_plan_result.plan_markdown = "# Test Plan"
            mock_plan_result.plan_path = tmp_path / "plan.md"
            mock_plan_result.key_files = []
            mock_plan_result.total_tasks = 1
            mock_import.return_value = mock_plan_result
            mock_server_state.return_value = MagicMock()

            await mock_orchestrator.queue_workflow(request)

            mock_import.assert_called_once()
            call_kwargs = mock_import.call_args.kwargs
            assert call_kwargs["plan_file"] == "external-plan.md"
            assert call_kwargs["plan_content"] is None

    async def test_queue_workflow_without_plan_does_not_call_import(
        self, mock_orchestrator: OrchestratorService, tmp_path: Path
    ) -> None:
        """queue_workflow should not call import_external_plan when no plan provided."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / ".git").mkdir()

        request = CreateWorkflowRequest(
            issue_id="TEST-003",
            worktree_path=str(worktree),
            start=False,
            task_title="Test task",
        )

        with (
            patch.object(
                mock_orchestrator, "_validate_worktree_path", return_value=worktree
            ),
            patch.object(
                mock_orchestrator,
                "_prepare_workflow_state",
            ) as mock_prepare,
            patch(
                "amelia.server.orchestrator.service.import_external_plan"
            ) as mock_import,
            patch(
                "amelia.server.orchestrator.service.ServerExecutionState"
            ) as mock_server_state,
        ):
            mock_state = MagicMock()
            mock_state.external_plan = False
            mock_profile = MagicMock()
            mock_profile.plan_path_pattern = "docs/plans/{issue_key}.md"
            mock_profile.working_dir = str(worktree)
            mock_prepare.return_value = (str(worktree), mock_profile, mock_state)
            mock_server_state.return_value = MagicMock()

            await mock_orchestrator.queue_workflow(request)

            # import_external_plan should NOT be called when no plan is provided
            mock_import.assert_not_called()
            # model_copy should NOT be called (state unchanged)
            mock_state.model_copy.assert_not_called()
