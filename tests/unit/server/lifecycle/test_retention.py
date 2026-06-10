"""Unit tests for LogRetentionService."""
from pathlib import Path
from unittest.mock import AsyncMock

import asyncpg
import pytest
from pydantic import BaseModel

from amelia.server.lifecycle.retention import LogRetentionService


class MockConfig(BaseModel):
    """Mock server config."""

    log_retention_days: int = 30
    checkpoint_retention_days: int = 0  # Default: immediate cleanup


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create mock database."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=0)
    db.fetch_all = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_checkpointer() -> AsyncMock:
    """Create mock checkpointer."""
    checkpointer = AsyncMock()
    checkpointer.adelete_thread = AsyncMock()
    return checkpointer


@pytest.fixture
def config() -> MockConfig:
    """Create config."""
    return MockConfig()


def _make_trajectory_file(tmp_path: Path, name: str) -> Path:
    """Create an on-disk trajectory file under a per-workflow directory."""
    path = tmp_path / name / "trajectory.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    return path


class TestTrajectorySweep:
    """Trajectory-file removal for finished workflows past the cutoff."""

    async def test_removes_file_and_directory_and_nulls_index(
        self, mock_db: AsyncMock, mock_checkpointer: AsyncMock, tmp_path: Path
    ) -> None:
        """Sweeps the trajectory file + directory and NULLs index columns."""
        path = _make_trajectory_file(tmp_path, "wf-old")
        service = LogRetentionService(
            db=mock_db,
            config=MockConfig(checkpoint_retention_days=-1),
            checkpointer=mock_checkpointer,
        )
        mock_db.fetch_all.return_value = [
            {"id": "wf-old", "trajectory_path": str(path)},
        ]
        mock_db.execute.return_value = 1

        result = await service.cleanup_on_shutdown()

        assert result.trajectories_deleted == 1
        assert not path.exists()
        assert not path.parent.exists()
        # First execute call is the UPDATE; second is the DELETE
        update_query = mock_db.execute.call_args_list[0].args[0]
        assert "trajectory_path = NULL" in update_query
        assert "total_cost_usd = NULL" in update_query
        assert "total_tokens = NULL" in update_query
        assert "total_duration_ms = NULL" in update_query

    async def test_missing_file_is_not_an_error(
        self, mock_db: AsyncMock, mock_checkpointer: AsyncMock, tmp_path: Path
    ) -> None:
        """A row whose file is already gone still gets its index NULLed."""
        service = LogRetentionService(
            db=mock_db,
            config=MockConfig(checkpoint_retention_days=-1),
            checkpointer=mock_checkpointer,
        )
        mock_db.fetch_all.return_value = [
            {"id": "wf-gone", "trajectory_path": str(tmp_path / "missing" / "trajectory.json")},
        ]
        mock_db.execute.return_value = 1

        result = await service.cleanup_on_shutdown()

        assert result.trajectories_deleted == 1
        # Two execute calls: UPDATE to NULL index columns, then DELETE old rows
        assert mock_db.execute.call_count == 2

    async def test_rmtree_failure_keeps_index_for_retry(
        self,
        mock_db: AsyncMock,
        mock_checkpointer: AsyncMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A directory that can't be removed keeps its index — no orphan.

        Clearing the index for a workflow whose directory deletion failed would
        strand that directory on disk with no row pointing at it, so no future
        sweep could ever find or delete it. Only successfully-removed rows get
        their index NULLed.
        """
        ok_path = _make_trajectory_file(tmp_path, "wf-ok")
        stuck_path = _make_trajectory_file(tmp_path, "wf-stuck")
        service = LogRetentionService(
            db=mock_db,
            config=MockConfig(checkpoint_retention_days=-1),
            checkpointer=mock_checkpointer,
        )
        mock_db.fetch_all.return_value = [
            {"id": "wf-ok", "trajectory_path": str(ok_path)},
            {"id": "wf-stuck", "trajectory_path": str(stuck_path)},
        ]
        mock_db.execute.return_value = 1

        import shutil

        real_rmtree = shutil.rmtree

        def flaky_rmtree(path: object, *args: object, **kwargs: object) -> None:
            if "wf-stuck" in str(path):
                raise OSError("device or resource busy")
            real_rmtree(path)  # type: ignore[arg-type]

        monkeypatch.setattr(
            "amelia.server.lifecycle.retention.shutil.rmtree", flaky_rmtree
        )

        result = await service.cleanup_on_shutdown()

        # The deletable row was swept; the stuck directory survives on disk.
        assert result.trajectories_deleted == 1
        assert not ok_path.exists()
        assert stuck_path.exists()
        # The UPDATE clears only the successfully-removed row's index.
        update_call = next(
            c for c in mock_db.execute.call_args_list if "UPDATE" in c.args[0]
        )
        assert update_call.args[1] == ["wf-ok"]

    async def test_no_old_trajectories_skips_update(
        self, mock_db: AsyncMock, mock_checkpointer: AsyncMock
    ) -> None:
        """No rows past the cutoff means no UPDATE is issued (only DELETE runs)."""
        service = LogRetentionService(
            db=mock_db,
            config=MockConfig(checkpoint_retention_days=-1),
            checkpointer=mock_checkpointer,
        )

        result = await service.cleanup_on_shutdown()

        assert result.trajectories_deleted == 0
        # No UPDATE is issued; only the DELETE for already-swept rows is called
        update_calls = [
            c for c in mock_db.execute.call_args_list
            if "UPDATE" in c.args[0]
        ]
        assert update_calls == []


class TestWorkflowRowDeletion:
    """Workflow row deletion for swept finished workflows past the cutoff."""

    async def test_deletes_rows_with_null_trajectory(
        self, mock_db: AsyncMock, mock_checkpointer: AsyncMock
    ) -> None:
        """Issues DELETE for finished rows whose trajectory_path is already NULL."""
        service = LogRetentionService(
            db=mock_db,
            config=MockConfig(checkpoint_retention_days=-1),
            checkpointer=mock_checkpointer,
        )
        # No rows need trajectory sweep; one row is ready for deletion
        mock_db.fetch_all.return_value = []
        mock_db.execute.return_value = 1

        result = await service.cleanup_on_shutdown()

        assert result.workflows_deleted == 1
        delete_call = mock_db.execute.call_args_list[0]
        query = delete_call.args[0]
        assert "DELETE FROM workflows" in query
        assert "trajectory_path IS NULL" in query

    async def test_no_rows_to_delete(
        self, mock_db: AsyncMock, mock_checkpointer: AsyncMock
    ) -> None:
        """Returns 0 when DELETE matches no rows."""
        service = LogRetentionService(
            db=mock_db,
            config=MockConfig(checkpoint_retention_days=-1),
            checkpointer=mock_checkpointer,
        )
        mock_db.fetch_all.return_value = []
        mock_db.execute.return_value = 0

        result = await service.cleanup_on_shutdown()

        assert result.workflows_deleted == 0

    async def test_sweep_and_delete_same_cycle(
        self, mock_db: AsyncMock, mock_checkpointer: AsyncMock, tmp_path: Path
    ) -> None:
        """Both UPDATE (sweep) and DELETE (row removal) run in the same cycle."""
        path = _make_trajectory_file(tmp_path, "wf-old")
        service = LogRetentionService(
            db=mock_db,
            config=MockConfig(checkpoint_retention_days=-1),
            checkpointer=mock_checkpointer,
        )
        mock_db.fetch_all.return_value = [
            {"id": "wf-old", "trajectory_path": str(path)},
        ]
        # UPDATE returns 1 swept, DELETE returns 1 deleted (a previously-swept row)
        mock_db.execute.side_effect = [1, 1]

        result = await service.cleanup_on_shutdown()

        assert result.trajectories_deleted == 1
        assert result.workflows_deleted == 1
        assert mock_db.execute.call_count == 2
        update_query = mock_db.execute.call_args_list[0].args[0]
        assert "trajectory_path = NULL" in update_query
        delete_query = mock_db.execute.call_args_list[1].args[0]
        assert "DELETE FROM workflows" in delete_query


class TestCheckpointCleanup:
    """LangGraph checkpoint cleanup behavior."""

    async def test_no_finished_workflows(
        self,
        mock_db: AsyncMock,
        config: MockConfig,
        mock_checkpointer: AsyncMock,
    ) -> None:
        """Should return 0 when no finished workflows exist."""
        service = LogRetentionService(
            db=mock_db, config=config, checkpointer=mock_checkpointer
        )
        # trajectory sweep rows, then finished workflows
        mock_db.fetch_all.side_effect = [[], []]

        result = await service.cleanup_on_shutdown()

        assert result.checkpoints_deleted == 0
        mock_checkpointer.adelete_thread.assert_not_called()

    async def test_deletes_finished_workflows(
        self,
        mock_db: AsyncMock,
        config: MockConfig,
        mock_checkpointer: AsyncMock,
    ) -> None:
        """Should delete checkpoints for finished workflows via adelete_thread."""
        service = LogRetentionService(
            db=mock_db, config=config, checkpointer=mock_checkpointer
        )
        # trajectory sweep rows, then finished workflows
        mock_db.fetch_all.side_effect = [
            [],
            [{"id": "completed-workflow-1"}, {"id": "completed-workflow-2"}],
        ]

        result = await service.cleanup_on_shutdown()

        # 2 workflows cleaned up via adelete_thread
        assert result.checkpoints_deleted == 2
        assert mock_checkpointer.adelete_thread.call_count == 2
        mock_checkpointer.adelete_thread.assert_any_call("completed-workflow-1")
        mock_checkpointer.adelete_thread.assert_any_call("completed-workflow-2")

    async def test_disabled_with_negative_retention(
        self,
        mock_db: AsyncMock,
        mock_checkpointer: AsyncMock,
    ) -> None:
        """Should skip checkpoint cleanup when retention_days is -1."""
        config = MockConfig(checkpoint_retention_days=-1)
        service = LogRetentionService(
            db=mock_db, config=config, checkpointer=mock_checkpointer
        )

        result = await service.cleanup_on_shutdown()

        # No checkpoints deleted because cleanup is disabled
        assert result.checkpoints_deleted == 0
        mock_checkpointer.adelete_thread.assert_not_called()

    async def test_respects_retention_days(
        self,
        mock_db: AsyncMock,
        mock_checkpointer: AsyncMock,
    ) -> None:
        """Should only delete checkpoints for workflows older than retention_days."""
        config = MockConfig(checkpoint_retention_days=7)
        service = LogRetentionService(
            db=mock_db, config=config, checkpointer=mock_checkpointer
        )
        # trajectory sweep rows, then finished workflows
        mock_db.fetch_all.side_effect = [[], [{"id": "old-workflow"}]]

        result = await service.cleanup_on_shutdown()

        # 1 workflow cleaned up via adelete_thread
        assert result.checkpoints_deleted == 1
        mock_checkpointer.adelete_thread.assert_called_once_with("old-workflow")

    async def test_retention_query_includes_date(
        self,
        mock_db: AsyncMock,
        mock_checkpointer: AsyncMock,
    ) -> None:
        """Should include date filter in query when retention_days > 0."""
        config = MockConfig(checkpoint_retention_days=7)
        service = LogRetentionService(
            db=mock_db, config=config, checkpointer=mock_checkpointer
        )
        mock_db.fetch_all.side_effect = [[], []]

        await service.cleanup_on_shutdown()

        # Second fetch_all call is the checkpoint query (PostgreSQL $1 style)
        fetch_call = mock_db.fetch_all.call_args
        assert fetch_call is not None
        args = fetch_call.args
        query = args[0]
        assert "completed_at < $1" in query
        # The cutoff datetime is passed as a positional arg
        assert len(args) == 2  # query + cutoff datetime

    async def test_no_checkpointer(
        self,
        mock_db: AsyncMock,
    ) -> None:
        """Should return 0 when no checkpointer is configured."""
        config = MockConfig(checkpoint_retention_days=0)
        service = LogRetentionService(db=mock_db, config=config, checkpointer=None)

        result = await service.cleanup_on_shutdown()

        # No checkpoints deleted because no checkpointer
        assert result.checkpoints_deleted == 0

    async def test_handles_individual_failures(
        self,
        mock_db: AsyncMock,
        mock_checkpointer: AsyncMock,
    ) -> None:
        """Should continue cleanup if one workflow fails and log warning."""
        config = MockConfig(checkpoint_retention_days=0)
        service = LogRetentionService(
            db=mock_db, config=config, checkpointer=mock_checkpointer
        )
        # trajectory sweep rows, then finished workflows
        mock_db.fetch_all.side_effect = [
            [],
            [{"id": "workflow-1"}, {"id": "workflow-2"}, {"id": "workflow-3"}],
        ]
        # First and third succeed, second fails with PostgresError
        mock_checkpointer.adelete_thread.side_effect = [
            None,
            asyncpg.PostgresError("Database error"),
            None,
        ]

        result = await service.cleanup_on_shutdown()

        # Only 2 out of 3 succeeded
        assert result.checkpoints_deleted == 2
        assert mock_checkpointer.adelete_thread.call_count == 3
