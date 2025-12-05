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
@pytest.mark.parametrize(
    "setup,expected",
    [
        pytest.param("git_file", True, id="valid_worktree_with_git_file"),
        pytest.param("git_dir", True, id="valid_repo_with_git_directory"),
        pytest.param("no_git", False, id="directory_missing_git"),
        pytest.param("nonexistent", False, id="nonexistent_directory"),
    ],
)
async def test_is_worktree_healthy(
    health_checker: WorktreeHealthChecker,
    tmp_path: Path,
    setup: str,
    expected: bool,
) -> None:
    """Worktree health depends on directory existence and .git presence."""
    if setup == "nonexistent":
        path = "/nonexistent"
    else:
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()
        if setup == "git_file":
            (worktree_path / ".git").touch()
        elif setup == "git_dir":
            (worktree_path / ".git").mkdir()
        # setup == "no_git" leaves directory without .git
        path = str(worktree_path)

    is_healthy = await health_checker._is_worktree_healthy(path)
    assert is_healthy is expected
