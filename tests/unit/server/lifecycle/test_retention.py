"""Unit tests for LogRetentionService."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import aiosqlite
import pytest
from pydantic import BaseModel

from amelia.server.lifecycle.retention import LogRetentionService


class MockConfig(BaseModel):
    """Mock server config."""

    log_retention_days: int = 30
    log_retention_max_events: int = 100_000
    checkpoint_retention_days: int = 0  # Default: immediate cleanup


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create mock database."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=0)
    db.fetch_all = AsyncMock(return_value=[])
    return db


@pytest.fixture
def config() -> MockConfig:
    """Create config."""
    return MockConfig()


@pytest.fixture
def retention_service(mock_db: AsyncMock, config: MockConfig) -> LogRetentionService:
    """Create retention service without checkpoint path."""
    return LogRetentionService(db=mock_db, config=config)


async def test_cleanup_on_shutdown(
    retention_service: LogRetentionService,
    mock_db: AsyncMock,
) -> None:
    """Should delete old events and workflows."""
    mock_db.execute.side_effect = [50, 5]  # events deleted, workflows deleted

    result = await retention_service.cleanup_on_shutdown()

    assert result.events_deleted == 50
    assert result.workflows_deleted == 5
    assert result.checkpoints_deleted == 0  # No checkpoint path configured
    assert mock_db.execute.call_count == 2


async def test_cleanup_checkpoints_no_path_configured(
    mock_db: AsyncMock,
    config: MockConfig,
) -> None:
    """Should skip checkpoint cleanup when no path configured."""
    service = LogRetentionService(db=mock_db, config=config, checkpoint_path=None)
    mock_db.execute.side_effect = [10, 2]

    result = await service.cleanup_on_shutdown()

    assert result.checkpoints_deleted == 0


async def test_cleanup_checkpoints_path_does_not_exist(
    mock_db: AsyncMock,
    config: MockConfig,
    tmp_path: Path,
) -> None:
    """Should skip checkpoint cleanup when database file doesn't exist."""
    nonexistent = tmp_path / "nonexistent.db"
    service = LogRetentionService(
        db=mock_db, config=config, checkpoint_path=str(nonexistent)
    )
    mock_db.execute.side_effect = [10, 2]

    result = await service.cleanup_on_shutdown()

    assert result.checkpoints_deleted == 0


async def test_cleanup_checkpoints_no_finished_workflows(
    mock_db: AsyncMock,
    config: MockConfig,
    tmp_path: Path,
) -> None:
    """Should return 0 when no finished workflows exist."""
    # Create a checkpoint database
    checkpoint_db = tmp_path / "checkpoints.db"
    async with aiosqlite.connect(str(checkpoint_db)) as conn:
        await conn.execute("""
            CREATE TABLE checkpoints (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                parent_checkpoint_id TEXT,
                type TEXT,
                checkpoint BLOB,
                metadata BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE writes (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                channel TEXT NOT NULL,
                type TEXT,
                value BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
            )
        """)
        await conn.commit()

    service = LogRetentionService(
        db=mock_db, config=config, checkpoint_path=str(checkpoint_db)
    )
    mock_db.execute.side_effect = [0, 0]
    mock_db.fetch_all.return_value = []  # No finished workflows

    result = await service.cleanup_on_shutdown()

    assert result.checkpoints_deleted == 0


async def test_cleanup_checkpoints_deletes_finished_workflows(
    mock_db: AsyncMock,
    config: MockConfig,
    tmp_path: Path,
) -> None:
    """Should delete checkpoints for finished workflows."""
    # Create a checkpoint database with test data
    checkpoint_db = tmp_path / "checkpoints.db"
    async with aiosqlite.connect(str(checkpoint_db)) as conn:
        await conn.execute("""
            CREATE TABLE checkpoints (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                parent_checkpoint_id TEXT,
                type TEXT,
                checkpoint BLOB,
                metadata BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE writes (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                channel TEXT NOT NULL,
                type TEXT,
                value BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
            )
        """)
        # Insert checkpoints for completed and in-progress workflows
        await conn.execute(
            "INSERT INTO checkpoints VALUES (?, '', 'cp1', NULL, NULL, NULL, NULL)",
            ("completed-workflow-1",),
        )
        await conn.execute(
            "INSERT INTO checkpoints VALUES (?, '', 'cp2', NULL, NULL, NULL, NULL)",
            ("completed-workflow-2",),
        )
        await conn.execute(
            "INSERT INTO checkpoints VALUES (?, '', 'cp3', NULL, NULL, NULL, NULL)",
            ("active-workflow",),  # Should NOT be deleted
        )
        # Insert writes
        await conn.execute(
            "INSERT INTO writes VALUES (?, '', 'cp1', 'task1', 0, 'ch1', NULL, NULL)",
            ("completed-workflow-1",),
        )
        await conn.commit()

    service = LogRetentionService(
        db=mock_db, config=config, checkpoint_path=str(checkpoint_db)
    )
    mock_db.execute.side_effect = [0, 0]
    mock_db.fetch_all.return_value = [
        {"id": "completed-workflow-1"},
        {"id": "completed-workflow-2"},
    ]

    result = await service.cleanup_on_shutdown()

    # 2 checkpoints + 1 write deleted = 3 total
    assert result.checkpoints_deleted == 3

    # Verify active workflow checkpoint remains
    async with aiosqlite.connect(str(checkpoint_db)) as conn:
        cursor = await conn.execute("SELECT thread_id FROM checkpoints")
        rows = list(await cursor.fetchall())
        assert len(rows) == 1
        assert rows[0][0] == "active-workflow"


async def test_cleanup_checkpoints_disabled_with_negative_retention(
    mock_db: AsyncMock,
    tmp_path: Path,
) -> None:
    """Should skip checkpoint cleanup when retention_days is -1."""
    # Create a checkpoint database with test data
    checkpoint_db = tmp_path / "checkpoints.db"
    async with aiosqlite.connect(str(checkpoint_db)) as conn:
        await conn.execute("""
            CREATE TABLE checkpoints (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                parent_checkpoint_id TEXT,
                type TEXT,
                checkpoint BLOB,
                metadata BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE writes (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                channel TEXT NOT NULL,
                type TEXT,
                value BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
            )
        """)
        await conn.execute(
            "INSERT INTO checkpoints VALUES (?, '', 'cp1', NULL, NULL, NULL, NULL)",
            ("completed-workflow",),
        )
        await conn.commit()

    # Config with -1 disables cleanup
    config = MockConfig(checkpoint_retention_days=-1)
    service = LogRetentionService(
        db=mock_db, config=config, checkpoint_path=str(checkpoint_db)
    )
    mock_db.execute.side_effect = [0, 0]

    result = await service.cleanup_on_shutdown()

    # No checkpoints deleted because cleanup is disabled
    assert result.checkpoints_deleted == 0

    # Verify checkpoint still exists
    async with aiosqlite.connect(str(checkpoint_db)) as conn:
        cursor = await conn.execute("SELECT COUNT(*) FROM checkpoints")
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == 1


async def test_cleanup_checkpoints_respects_retention_days(
    mock_db: AsyncMock,
    tmp_path: Path,
) -> None:
    """Should only delete checkpoints for workflows older than retention_days."""
    # Create a checkpoint database with test data
    checkpoint_db = tmp_path / "checkpoints.db"
    async with aiosqlite.connect(str(checkpoint_db)) as conn:
        await conn.execute("""
            CREATE TABLE checkpoints (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                parent_checkpoint_id TEXT,
                type TEXT,
                checkpoint BLOB,
                metadata BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE writes (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                channel TEXT NOT NULL,
                type TEXT,
                value BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
            )
        """)
        # Old workflow checkpoint (should be deleted)
        await conn.execute(
            "INSERT INTO checkpoints VALUES (?, '', 'cp1', NULL, NULL, NULL, NULL)",
            ("old-workflow",),
        )
        # Recent workflow checkpoint (should remain)
        await conn.execute(
            "INSERT INTO checkpoints VALUES (?, '', 'cp2', NULL, NULL, NULL, NULL)",
            ("recent-workflow",),
        )
        await conn.commit()

    # Config with 7 day retention
    config = MockConfig(checkpoint_retention_days=7)
    service = LogRetentionService(
        db=mock_db, config=config, checkpoint_path=str(checkpoint_db)
    )
    mock_db.execute.side_effect = [0, 0]

    # Mock fetch_all to return only old workflow (completed > 7 days ago)
    # The query includes a date filter, so only old workflows are returned
    mock_db.fetch_all.return_value = [{"id": "old-workflow"}]

    result = await service.cleanup_on_shutdown()

    # Only the old workflow's checkpoint deleted
    assert result.checkpoints_deleted == 1

    # Verify recent workflow checkpoint remains
    async with aiosqlite.connect(str(checkpoint_db)) as conn:
        cursor = await conn.execute("SELECT thread_id FROM checkpoints")
        rows = list(await cursor.fetchall())
        assert len(rows) == 1
        assert rows[0][0] == "recent-workflow"


async def test_cleanup_checkpoints_retention_query_includes_date(
    mock_db: AsyncMock,
    tmp_path: Path,
) -> None:
    """Should include date filter in query when retention_days > 0."""
    checkpoint_db = tmp_path / "checkpoints.db"
    async with aiosqlite.connect(str(checkpoint_db)) as conn:
        await conn.execute("""
            CREATE TABLE checkpoints (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                parent_checkpoint_id TEXT,
                type TEXT,
                checkpoint BLOB,
                metadata BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE writes (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                channel TEXT NOT NULL,
                type TEXT,
                value BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
            )
        """)
        await conn.commit()

    config = MockConfig(checkpoint_retention_days=7)
    service = LogRetentionService(
        db=mock_db, config=config, checkpoint_path=str(checkpoint_db)
    )
    mock_db.execute.side_effect = [0, 0]
    mock_db.fetch_all.return_value = []

    await service.cleanup_on_shutdown()

    # Verify fetch_all was called with a date parameter
    fetch_call = mock_db.fetch_all.call_args
    assert fetch_call is not None
    query, params = fetch_call.args
    assert "completed_at < ?" in query
    assert len(params) == 1
    # Verify the date is approximately 7 days ago
    cutoff = datetime.fromisoformat(params[0])
    expected_cutoff = datetime.now(UTC) - timedelta(days=7)
    # Allow 1 minute tolerance for test execution time
    assert abs((cutoff - expected_cutoff).total_seconds()) < 60
