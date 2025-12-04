"""Unit tests for WorktreeHealthChecker."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.server.lifecycle.health_checker import WorktreeHealthChecker
from amelia.server.models import ServerExecutionState


@pytest.fixture
def mock_orchestrator() -> AsyncMock:
    """Create mock orchestrator."""
    orch = AsyncMock()
    orch.get_active_workflows = MagicMock(return_value=[])
    orch.get_workflow_by_worktree = AsyncMock(return_value=None)
    orch.cancel_workflow = AsyncMock()
    return orch


@pytest.fixture
def health_checker(mock_orchestrator: AsyncMock) -> WorktreeHealthChecker:
    """Create health checker."""
    return WorktreeHealthChecker(
        orchestrator=mock_orchestrator,
        check_interval=0.1,  # Short interval for tests
    )


@pytest.mark.asyncio
async def test_start_and_stop(health_checker: WorktreeHealthChecker) -> None:
    """Should start and stop check loop."""
    await health_checker.start()
    assert health_checker._task is not None
    assert not health_checker._task.done()

    await health_checker.stop()
    assert health_checker._task.cancelled() or health_checker._task.done()


@pytest.mark.asyncio
async def test_check_healthy_worktree(
    health_checker: WorktreeHealthChecker,
    mock_orchestrator: AsyncMock,
    tmp_path: Path,
) -> None:
    """Healthy worktree should not trigger cancellation."""
    # Create fake worktree
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()
    (worktree_path / ".git").touch()

    mock_orchestrator.get_active_workflows.return_value = [str(worktree_path)]

    await health_checker._check_all_worktrees()

    # Should not cancel
    mock_orchestrator.cancel_workflow.assert_not_called()


@pytest.mark.asyncio
async def test_check_deleted_worktree(
    health_checker: WorktreeHealthChecker,
    mock_orchestrator: AsyncMock,
) -> None:
    """Deleted worktree should trigger cancellation."""
    # Mock workflow
    mock_workflow = ServerExecutionState(
        id="wf-1",
        issue_id="ISSUE-123",
        worktree_path="/nonexistent/path",
        worktree_name="deleted",
        workflow_status="in_progress",
        started_at=datetime.now(UTC),
    )
    mock_orchestrator.get_active_workflows.return_value = ["/nonexistent/path"]
    mock_orchestrator.get_workflow_by_worktree.return_value = mock_workflow

    await health_checker._check_all_worktrees()

    # Should cancel workflow
    mock_orchestrator.cancel_workflow.assert_called_once()
    call_args = mock_orchestrator.cancel_workflow.call_args
    assert call_args[0][0] == "wf-1"


@pytest.mark.asyncio
async def test_is_worktree_healthy_directory_exists(
    health_checker: WorktreeHealthChecker,
    tmp_path: Path,
) -> None:
    """Should return True for valid worktree directory."""
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()
    (worktree_path / ".git").touch()

    is_healthy = await health_checker._is_worktree_healthy(str(worktree_path))
    assert is_healthy is True


@pytest.mark.asyncio
async def test_is_worktree_healthy_no_directory(
    health_checker: WorktreeHealthChecker,
) -> None:
    """Should return False for nonexistent directory."""
    is_healthy = await health_checker._is_worktree_healthy("/nonexistent")
    assert is_healthy is False


@pytest.mark.asyncio
async def test_is_worktree_healthy_no_git(
    health_checker: WorktreeHealthChecker,
    tmp_path: Path,
) -> None:
    """Should return False if .git missing."""
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()
    # No .git file/dir

    is_healthy = await health_checker._is_worktree_healthy(str(worktree_path))
    assert is_healthy is False


@pytest.mark.asyncio
async def test_is_worktree_healthy_git_directory(
    health_checker: WorktreeHealthChecker,
    tmp_path: Path,
) -> None:
    """Should return True for main repo with .git directory."""
    worktree_path = tmp_path / "main"
    worktree_path.mkdir()
    (worktree_path / ".git").mkdir()

    is_healthy = await health_checker._is_worktree_healthy(str(worktree_path))
    assert is_healthy is True
