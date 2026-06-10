"""Integration tests for LogRetentionService trajectory-file sweeping.

Retention no longer deletes ``workflow_log`` rows (the table is gone) — it
removes trajectory files for finished workflows past the cutoff and NULLs the
thin index columns on ``workflows``.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from amelia.server.database.connection import Database
from amelia.server.database.repository import WorkflowRepository
from amelia.server.lifecycle.retention import LogRetentionService
from amelia.server.models.state import ServerExecutionState


pytestmark = pytest.mark.integration


class _RetentionConfig(BaseModel):
    log_retention_days: int = 30
    checkpoint_retention_days: int = -1  # checkpoints out of scope here


async def _create_finished_workflow(
    test_db: Database,
    repository: WorkflowRepository,
    trajectory_dir: Path,
    completed_at: datetime,
) -> tuple[UUID, Path]:
    """Create a completed workflow with a trajectory file on disk."""
    workflow_id = uuid4()
    state = ServerExecutionState(
        id=workflow_id,
        issue_id=f"ISSUE-{workflow_id.hex[:8]}",
        worktree_path=f"/tmp/worktree-{workflow_id.hex[:8]}",
        workflow_status="completed",
        started_at=completed_at - timedelta(hours=1),
        completed_at=completed_at,
    )
    await repository.create(state)

    path = trajectory_dir / str(workflow_id) / "trajectory.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema_version": "ATIF-v1.7"}))

    await test_db.execute(
        """
        UPDATE workflows SET
            trajectory_path = $1,
            total_cost_usd = 1.25,
            total_tokens = 1000,
            total_duration_ms = 60000
        WHERE id = $2
        """,
        str(path),
        workflow_id,
    )
    return workflow_id, path


async def test_retention_sweeps_old_trajectory_and_nulls_index(
    test_db: Database,
    test_repository: WorkflowRepository,
    tmp_path: Path,
) -> None:
    """Old finished workflow: file + directory gone, index columns NULLed."""
    old_id, old_path = await _create_finished_workflow(
        test_db,
        test_repository,
        tmp_path,
        completed_at=datetime.now(UTC) - timedelta(days=45),
    )
    recent_id, recent_path = await _create_finished_workflow(
        test_db,
        test_repository,
        tmp_path,
        completed_at=datetime.now(UTC) - timedelta(days=1),
    )

    service = LogRetentionService(db=test_db, config=_RetentionConfig())
    result = await service.cleanup_on_shutdown()

    assert result.trajectories_deleted == 1

    # Old workflow: file and its directory are gone, index columns NULLed
    assert not old_path.exists()
    assert not old_path.parent.exists()
    old_row = await test_db.fetch_one(
        "SELECT trajectory_path, total_cost_usd, total_tokens, total_duration_ms "
        "FROM workflows WHERE id = $1",
        old_id,
    )
    assert old_row is not None
    assert old_row["trajectory_path"] is None
    assert old_row["total_cost_usd"] is None
    assert old_row["total_tokens"] is None
    assert old_row["total_duration_ms"] is None

    # Recent workflow: file survives, index intact
    assert recent_path.exists()
    recent_row = await test_db.fetch_one(
        "SELECT trajectory_path FROM workflows WHERE id = $1",
        recent_id,
    )
    assert recent_row is not None
    assert recent_row["trajectory_path"] == str(recent_path)


async def test_retention_missing_file_is_not_an_error(
    test_db: Database,
    test_repository: WorkflowRepository,
    tmp_path: Path,
) -> None:
    """A NULLed index row must result even when the file is already gone."""
    old_id, old_path = await _create_finished_workflow(
        test_db,
        test_repository,
        tmp_path,
        completed_at=datetime.now(UTC) - timedelta(days=45),
    )
    old_path.unlink()
    old_path.parent.rmdir()

    service = LogRetentionService(db=test_db, config=_RetentionConfig())
    result = await service.cleanup_on_shutdown()

    assert result.trajectories_deleted == 1
    row = await test_db.fetch_one(
        "SELECT trajectory_path FROM workflows WHERE id = $1", old_id
    )
    assert row is not None
    assert row["trajectory_path"] is None
