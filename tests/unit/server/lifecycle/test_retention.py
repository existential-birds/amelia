"""Unit tests for LogRetentionService."""
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from amelia.server.lifecycle.retention import LogRetentionService


class MockConfig(BaseModel):
    """Mock server config."""
    log_retention_days: int = 30
    log_retention_max_events: int = 100_000


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create mock database."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=0)
    return db


@pytest.fixture
def config() -> MockConfig:
    """Create config."""
    return MockConfig()


@pytest.fixture
def retention_service(mock_db: AsyncMock, config: MockConfig) -> LogRetentionService:
    """Create retention service."""
    return LogRetentionService(db=mock_db, config=config)


@pytest.mark.asyncio
async def test_cleanup_on_shutdown(
    retention_service: LogRetentionService,
    mock_db: AsyncMock,
):
    """Should delete old events and workflows."""
    mock_db.execute.side_effect = [50, 5]  # events deleted, workflows deleted

    result = await retention_service.cleanup_on_shutdown()

    assert result.events_deleted == 50
    assert result.workflows_deleted == 5
    assert mock_db.execute.call_count == 2
