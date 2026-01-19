"""Tests for usage repository methods."""

from datetime import date

import pytest

from amelia.server.database import WorkflowRepository
from amelia.server.database.connection import Database


@pytest.fixture
async def seed_data(db_with_schema: Database) -> None:
    """Seed test data for usage queries."""
    # Create two workflows
    await db_with_schema.execute("""
        INSERT INTO workflows (id, issue_id, worktree_path, status, created_at, started_at, state_json)
        VALUES
            ('wf-1', 'ISSUE-1', '/tmp/repo1', 'completed', '2026-01-10T10:00:00Z', '2026-01-10T10:00:00Z', '{}'),
            ('wf-2', 'ISSUE-2', '/tmp/repo2', 'completed', '2026-01-15T10:00:00Z', '2026-01-15T10:00:00Z', '{}')
    """)

    # Create token usage records
    await db_with_schema.execute("""
        INSERT INTO token_usage (id, workflow_id, agent, model, input_tokens, output_tokens, cache_read_tokens, cost_usd, duration_ms, timestamp)
        VALUES
            ('tu-1', 'wf-1', 'architect', 'claude-sonnet-4', 10000, 2000, 5000, 0.50, 30000, '2026-01-10T10:05:00Z'),
            ('tu-2', 'wf-1', 'developer', 'claude-sonnet-4', 20000, 5000, 8000, 1.20, 60000, '2026-01-10T10:10:00Z'),
            ('tu-3', 'wf-2', 'architect', 'claude-opus-4', 15000, 3000, 0, 2.50, 45000, '2026-01-15T10:05:00Z')
    """)


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_get_usage_summary_date_filtering(repository: WorkflowRepository, seed_data: None) -> None:
    """Date filtering excludes out-of-range data."""
    summary = await repository.get_usage_summary(
        start_date=date(2026, 1, 14),
        end_date=date(2026, 1, 16),
    )

    # Only wf-2 is in range
    assert summary["total_workflows"] == 1
    assert summary["total_cost_usd"] == pytest.approx(2.50, rel=0.01)
