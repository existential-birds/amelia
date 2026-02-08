"""Tests for usage repository methods."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from amelia.server.database import WorkflowRepository
from amelia.server.database.connection import Database
from amelia.server.models.state import ServerExecutionState
from amelia.server.models.tokens import TokenUsage


pytestmark = pytest.mark.integration


@pytest.fixture
async def seed_data(db_with_schema: Database, repository: WorkflowRepository) -> None:
    """Seed test data for usage queries."""
    wf1_id = str(uuid4())
    wf2_id = str(uuid4())

    # Create two workflows
    wf1 = ServerExecutionState(
        id=wf1_id,
        issue_id="ISSUE-1",
        worktree_path="/tmp/repo1",
        workflow_status="completed",
        started_at=datetime(2026, 1, 10, 10, 0, 0, tzinfo=UTC),
    )
    wf2 = ServerExecutionState(
        id=wf2_id,
        issue_id="ISSUE-2",
        worktree_path="/tmp/repo2",
        workflow_status="completed",
        started_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
    )
    await repository.create(wf1)
    await repository.create(wf2)

    # Create token usage records
    await repository.save_token_usage(
        TokenUsage(
            workflow_id=wf1_id,
            agent="architect",
            model="claude-sonnet-4",
            input_tokens=10000,
            output_tokens=2000,
            cache_read_tokens=5000,
            cost_usd=0.50,
            duration_ms=30000,
            timestamp=datetime(2026, 1, 10, 10, 5, 0, tzinfo=UTC),
        )
    )
    await repository.save_token_usage(
        TokenUsage(
            workflow_id=wf1_id,
            agent="developer",
            model="claude-sonnet-4",
            input_tokens=20000,
            output_tokens=5000,
            cache_read_tokens=8000,
            cost_usd=1.20,
            duration_ms=60000,
            timestamp=datetime(2026, 1, 10, 10, 10, 0, tzinfo=UTC),
        )
    )
    await repository.save_token_usage(
        TokenUsage(
            workflow_id=wf2_id,
            agent="architect",
            model="claude-opus-4",
            input_tokens=15000,
            output_tokens=3000,
            cache_read_tokens=0,
            cost_usd=2.50,
            duration_ms=45000,
            timestamp=datetime(2026, 1, 15, 10, 5, 0, tzinfo=UTC),
        )
    )


async def test_get_usage_summary(repository: WorkflowRepository, seed_data: None) -> None:
    """get_usage_summary returns aggregated totals."""
    summary = await repository.get_usage_summary(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )

    assert summary["total_cost_usd"] == pytest.approx(4.20, rel=0.01)
    assert summary["total_workflows"] == 2
    assert summary["total_tokens"] == 55000  # 10k+2k+20k+5k+15k+3k
    assert summary["total_duration_ms"] == 135000  # 30k+60k+45k


async def test_get_usage_trend(repository: WorkflowRepository, seed_data: None) -> None:
    """get_usage_trend returns daily aggregates."""
    trend = await repository.get_usage_trend(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )

    # Should have 2 days with data
    assert len(trend) == 2

    # Jan 10 has wf-1 (2 usage records)
    jan10 = next(t for t in trend if t["date"] == "2026-01-10")
    assert jan10["cost_usd"] == pytest.approx(1.70, rel=0.01)
    assert jan10["workflows"] == 1

    # Jan 15 has wf-2 (1 usage record)
    jan15 = next(t for t in trend if t["date"] == "2026-01-15")
    assert jan15["cost_usd"] == pytest.approx(2.50, rel=0.01)
    assert jan15["workflows"] == 1


async def test_get_usage_by_model(repository: WorkflowRepository, seed_data: None) -> None:
    """get_usage_by_model returns model breakdown."""
    by_model = await repository.get_usage_by_model(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )

    assert len(by_model) == 2

    sonnet = next(m for m in by_model if m["model"] == "claude-sonnet-4")
    assert sonnet["workflows"] == 1  # Only wf-1 used sonnet
    assert sonnet["tokens"] == 37000  # 10k+2k+20k+5k
    assert sonnet["cost_usd"] == pytest.approx(1.70, rel=0.01)

    opus = next(m for m in by_model if m["model"] == "claude-opus-4")
    assert opus["workflows"] == 1
    assert opus["tokens"] == 18000  # 15k+3k


async def test_get_usage_summary_date_filtering(repository: WorkflowRepository, seed_data: None) -> None:
    """Date filtering excludes out-of-range data."""
    summary = await repository.get_usage_summary(
        start_date=date(2026, 1, 14),
        end_date=date(2026, 1, 16),
    )

    # Only wf-2 is in range
    assert summary["total_workflows"] == 1
    assert summary["total_cost_usd"] == pytest.approx(2.50, rel=0.01)
