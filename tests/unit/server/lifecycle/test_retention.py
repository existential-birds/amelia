"""Unit tests for LogRetentionService."""
from unittest.mock import AsyncMock

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
def config() -> MockConfig:
    """Create config."""
    return MockConfig()


@pytest.fixture
def retention_service(mock_db: AsyncMock, config: MockConfig) -> LogRetentionService:
    """Create retention service."""
    return LogRetentionService(db=mock_db, config=config)


async def test_cleanup_on_shutdown(
    retention_service: LogRetentionService,
    mock_db: AsyncMock,
) -> None:
    """Should delete old events and workflows."""
    # events deleted, workflows deleted
    mock_db.execute.side_effect = [50, 5]

    result = await retention_service.cleanup_on_shutdown()

    assert result.events_deleted == 50
    assert result.workflows_deleted == 5
    assert result.checkpoints_deleted == 0  # No finished workflows
    assert mock_db.execute.call_count == 2


async def test_cleanup_checkpoints_no_finished_workflows(
    mock_db: AsyncMock,
    config: MockConfig,
) -> None:
    """Should return 0 when no finished workflows exist."""
    service = LogRetentionService(db=mock_db, config=config)
    # events deleted, workflows deleted
    mock_db.execute.side_effect = [0, 0]
    mock_db.fetch_all.return_value = []  # No finished workflows

    result = await service.cleanup_on_shutdown()

    assert result.checkpoints_deleted == 0


async def test_cleanup_checkpoints_deletes_finished_workflows(
    mock_db: AsyncMock,
    config: MockConfig,
) -> None:
    """Should delete checkpoints for finished workflows via shared database pool."""
    service = LogRetentionService(db=mock_db, config=config)
    # events deleted, workflows deleted, then checkpoint deletes
    mock_db.execute.side_effect = [0, 0, 2, 1, 1, 0]
    mock_db.fetch_all.return_value = [
        {"id": "completed-workflow-1"},
        {"id": "completed-workflow-2"},
    ]

    result = await service.cleanup_on_shutdown()

    # 2 + 1 + 1 + 0 = 4 total checkpoint/write rows deleted
    assert result.checkpoints_deleted == 4


async def test_cleanup_checkpoints_disabled_with_negative_retention(
    mock_db: AsyncMock,
) -> None:
    """Should skip checkpoint cleanup when retention_days is -1."""
    config = MockConfig(checkpoint_retention_days=-1)
    service = LogRetentionService(db=mock_db, config=config)
    # events deleted, workflows deleted
    mock_db.execute.side_effect = [0, 0]

    result = await service.cleanup_on_shutdown()

    # No checkpoints deleted because cleanup is disabled
    assert result.checkpoints_deleted == 0


async def test_cleanup_checkpoints_respects_retention_days(
    mock_db: AsyncMock,
) -> None:
    """Should only delete checkpoints for workflows older than retention_days."""
    config = MockConfig(checkpoint_retention_days=7)
    service = LogRetentionService(db=mock_db, config=config)
    # events deleted, workflows deleted, then checkpoint deletes
    mock_db.execute.side_effect = [0, 0, 1, 0]
    mock_db.fetch_all.return_value = [{"id": "old-workflow"}]

    result = await service.cleanup_on_shutdown()

    assert result.checkpoints_deleted == 1


async def test_cleanup_checkpoints_retention_query_includes_date(
    mock_db: AsyncMock,
) -> None:
    """Should include date filter in query when retention_days > 0."""
    config = MockConfig(checkpoint_retention_days=7)
    service = LogRetentionService(db=mock_db, config=config)
    # events deleted, workflows deleted
    mock_db.execute.side_effect = [0, 0]
    mock_db.fetch_all.return_value = []

    await service.cleanup_on_shutdown()

    # Verify fetch_all was called with positional args (PostgreSQL $1 style)
    fetch_call = mock_db.fetch_all.call_args
    assert fetch_call is not None
    args = fetch_call.args
    query = args[0]
    assert "completed_at < $1" in query
    # The cutoff datetime is passed as a positional arg
    assert len(args) == 2  # query + cutoff datetime
