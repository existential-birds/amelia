"""Integration tests for brainstorming handoff to implementation."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.server.database import ProfileRecord
from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.orchestrator.service import OrchestratorService


@pytest.fixture
def mock_profile_repo() -> AsyncMock:
    """Create mock ProfileRepository that returns test profile."""
    repo = AsyncMock()
    profile_record = ProfileRecord(
        id="test",
        driver="cli:claude",
        model="sonnet",
        validator_model="haiku",
        tracker="noop",
        working_dir="/tmp/test",
    )
    repo.get_profile.return_value = profile_record
    repo.get_active_profile.return_value = profile_record
    return repo


class TestHandoffDesignFlow:
    """Test design artifact flows through handoff to implementation."""

    async def test_prepare_workflow_state_loads_design_from_artifact_path(
        self, tmp_path: Path, mock_profile_repo: AsyncMock
    ) -> None:
        """Design is loaded from artifact_path into ImplementationState."""
        # Create a design artifact file
        design_file = tmp_path / "design.md"
        design_file.write_text("# Design\n\nThis is the design content.")

        # Create orchestrator with mocked dependencies
        orchestrator = OrchestratorService.__new__(OrchestratorService)
        orchestrator._event_bus = MagicMock()
        orchestrator._repository = MagicMock()
        orchestrator._profile_repo = mock_profile_repo

        # Patch methods to avoid dependencies
        with patch(
            "amelia.server.orchestrator.service.get_git_head",
            new_callable=AsyncMock,
            return_value="abc123",
        ):
            _, _, state = await orchestrator._prepare_workflow_state(
                workflow_id="wf-123",
                worktree_path=str(tmp_path),
                issue_id="issue-1",
                task_title="Implement design",
                # Use relative path within worktree (leading slash stripped)
                artifact_path="design.md",
            )

        # Verify design was loaded
        assert state.design is not None
        assert state.design.content == "# Design\n\nThis is the design content."
        assert state.design.source == "file"

    async def test_prepare_workflow_state_without_artifact_path(
        self, tmp_path: Path, mock_profile_repo: AsyncMock
    ) -> None:
        """Design is None when no artifact_path provided (backward compatible)."""
        orchestrator = OrchestratorService.__new__(OrchestratorService)
        orchestrator._event_bus = MagicMock()
        orchestrator._repository = MagicMock()
        orchestrator._profile_repo = mock_profile_repo

        with patch(
            "amelia.server.orchestrator.service.get_git_head",
            new_callable=AsyncMock,
            return_value="abc123",
        ):
            _, _, state = await orchestrator._prepare_workflow_state(
                workflow_id="wf-123",
                worktree_path=str(tmp_path),
                issue_id="issue-1",
                task_title="Implement feature",
            )

        # Design should remain None
        assert state.design is None

    async def test_prepare_workflow_state_with_missing_artifact_file(
        self, tmp_path: Path, mock_profile_repo: AsyncMock
    ) -> None:
        """Raises FileNotFoundError when artifact file doesn't exist."""
        orchestrator = OrchestratorService.__new__(OrchestratorService)
        orchestrator._event_bus = MagicMock()
        orchestrator._repository = MagicMock()
        orchestrator._profile_repo = mock_profile_repo

        with (
            patch(
                "amelia.server.orchestrator.service.get_git_head",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            pytest.raises(FileNotFoundError),
        ):
            await orchestrator._prepare_workflow_state(
                workflow_id="wf-123",
                worktree_path=str(tmp_path),
                issue_id="issue-1",
                task_title="Implement design",
                artifact_path="/nonexistent/design.md",
            )

    async def test_prepare_workflow_state_resolves_worktree_relative_artifact_path(
        self, tmp_path: Path, mock_profile_repo: AsyncMock
    ) -> None:
        """Artifact path with leading slash is resolved relative to worktree.

        This tests the real-world scenario where brainstorming creates files
        with paths like /docs/plans/design.md (relative to worktree, not filesystem root).
        """
        # Create nested design artifact file in worktree
        design_dir = tmp_path / "docs" / "plans"
        design_dir.mkdir(parents=True)
        design_file = design_dir / "design.md"
        design_file.write_text("# Design from brainstorm")

        orchestrator = OrchestratorService.__new__(OrchestratorService)
        orchestrator._event_bus = MagicMock()
        orchestrator._repository = MagicMock()
        orchestrator._profile_repo = mock_profile_repo

        with patch(
            "amelia.server.orchestrator.service.get_git_head",
            new_callable=AsyncMock,
            return_value="abc123",
        ):
            # Pass artifact_path with leading slash (worktree-relative)
            _, _, state = await orchestrator._prepare_workflow_state(
                workflow_id="wf-123",
                worktree_path=str(tmp_path),
                issue_id="issue-1",
                task_title="Implement design",
                artifact_path="/docs/plans/design.md",  # Leading slash, worktree-relative
            )

        # Verify design was loaded correctly
        assert state.design is not None
        assert state.design.content == "# Design from brainstorm"
        assert state.design.source == "file"

    async def test_queue_workflow_passes_artifact_path(
        self, tmp_path: Path, mock_profile_repo: AsyncMock
    ) -> None:
        """queue_workflow passes artifact_path through to _prepare_workflow_state."""
        # Create design file
        design_file = tmp_path / "design.md"
        design_file.write_text("# Design Content")

        # Create .git directory to pass validation
        (tmp_path / ".git").mkdir()

        orchestrator = OrchestratorService.__new__(OrchestratorService)
        orchestrator._event_bus = MagicMock()
        orchestrator._repository = MagicMock()
        orchestrator._repository.create = AsyncMock()
        orchestrator._profile_repo = mock_profile_repo

        # Use worktree-relative path (not absolute) for security
        request = CreateWorkflowRequest(
            issue_id="issue-1",
            worktree_path=str(tmp_path),
            task_title="Implement design",
            artifact_path="design.md",  # Relative to worktree
            start=False,
        )

        with (
            patch.object(orchestrator, "_emit", new_callable=AsyncMock),
            patch(
                "amelia.server.orchestrator.service.get_git_head",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
        ):
            await orchestrator.queue_workflow(request)

        # Verify workflow was created with design loaded
        # Check the call to _repository.create to get the state
        assert orchestrator._repository.create.called
        state = orchestrator._repository.create.call_args[0][0]
        assert state.execution_state.design is not None
        assert state.execution_state.design.content == "# Design Content"

    async def test_prepare_workflow_state_rejects_path_traversal(
        self, tmp_path: Path, mock_profile_repo: AsyncMock
    ) -> None:
        """Rejects artifact_path that escapes worktree via .. sequences."""
        orchestrator = OrchestratorService.__new__(OrchestratorService)
        orchestrator._event_bus = MagicMock()
        orchestrator._repository = MagicMock()
        orchestrator._profile_repo = mock_profile_repo

        with (
            patch(
                "amelia.server.orchestrator.service.get_git_head",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            pytest.raises(ValueError, match="resolves outside worktree"),
        ):
            await orchestrator._prepare_workflow_state(
                workflow_id="wf-123",
                worktree_path=str(tmp_path),
                issue_id="issue-1",
                task_title="Implement design",
                artifact_path="../../../etc/passwd",
            )

    async def test_prepare_workflow_state_rejects_absolute_path_outside_worktree(
        self, tmp_path: Path, mock_profile_repo: AsyncMock
    ) -> None:
        """Rejects absolute paths that would escape worktree.

        Even if an absolute path is provided, it gets stripped and treated
        as worktree-relative, so /etc/passwd becomes {worktree}/etc/passwd
        and fails validation since it doesn't exist.
        """
        orchestrator = OrchestratorService.__new__(OrchestratorService)
        orchestrator._event_bus = MagicMock()
        orchestrator._repository = MagicMock()
        orchestrator._profile_repo = mock_profile_repo

        with (
            patch(
                "amelia.server.orchestrator.service.get_git_head",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            # Absolute paths are stripped, so /etc/passwd becomes etc/passwd
            # within the worktree, which won't exist
            pytest.raises(FileNotFoundError),
        ):
            await orchestrator._prepare_workflow_state(
                workflow_id="wf-123",
                worktree_path=str(tmp_path),
                issue_id="issue-1",
                task_title="Implement design",
                artifact_path="/etc/passwd",
            )

    async def test_prepare_workflow_state_rejects_symlink_escape(
        self, tmp_path: Path, mock_profile_repo: AsyncMock
    ) -> None:
        """Rejects artifact_path that escapes via symlinks."""
        # Create a symlink that points outside the worktree
        symlink = tmp_path / "escape_link"
        symlink.symlink_to("/etc")

        orchestrator = OrchestratorService.__new__(OrchestratorService)
        orchestrator._event_bus = MagicMock()
        orchestrator._repository = MagicMock()
        orchestrator._profile_repo = mock_profile_repo

        with (
            patch(
                "amelia.server.orchestrator.service.get_git_head",
                new_callable=AsyncMock,
                return_value="abc123",
            ),
            pytest.raises(ValueError, match="resolves outside worktree"),
        ):
            await orchestrator._prepare_workflow_state(
                workflow_id="wf-123",
                worktree_path=str(tmp_path),
                issue_id="issue-1",
                task_title="Implement design",
                artifact_path="escape_link/passwd",
            )
