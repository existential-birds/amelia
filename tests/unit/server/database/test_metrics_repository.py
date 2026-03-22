"""Tests for MetricsRepository -- metrics persistence and aggregation."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from amelia.server.database.metrics_repository import MetricsRepository
from amelia.server.models.metrics import (
    AggressivenessBreakdown,
    ClassificationRecord,
    ClassificationsResponse,
    PRAutoFixDailyBucket,
    PRAutoFixMetricsResponse,
    PRAutoFixMetricsSummary,
)


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock Database with async methods."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=1)
    db.fetch_one = AsyncMock(return_value=None)
    db.fetch_all = AsyncMock(return_value=[])
    db.fetch_scalar = AsyncMock(return_value=0)
    return db


@pytest.fixture
def repo(mock_db: MagicMock) -> MetricsRepository:
    """Create MetricsRepository with mock DB."""
    return MetricsRepository(mock_db)


class TestSaveRunMetrics:
    """Tests for save_run_metrics."""

    async def test_calls_execute_with_correct_params(
        self, repo: MetricsRepository, mock_db: MagicMock,
    ) -> None:
        run_id = uuid4()
        workflow_id = uuid4()
        await repo.save_run_metrics(
            run_id=run_id,
            workflow_id=workflow_id,
            profile_id="default",
            pr_number=42,
            aggressiveness_level="standard",
            comments_processed=5,
            fixes_applied=3,
            fixes_failed=1,
            fixes_skipped=1,
            commits_pushed=1,
            threads_resolved=3,
            duration_seconds=12.5,
            prompt_hash="abc123def456",
        )
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        sql = call_args[0][0]
        assert "pr_autofix_runs" in sql
        assert "INSERT" in sql.upper()
        # Verify key positional params
        assert call_args[0][1] == run_id
        assert call_args[0][2] == workflow_id
        assert call_args[0][3] == "default"
        assert call_args[0][4] == 42


class TestSaveClassifications:
    """Tests for save_classifications."""

    async def test_batch_insert_multiple_classifications(
        self, repo: MetricsRepository, mock_db: MagicMock,
    ) -> None:
        run_id = uuid4()
        classifications = [
            {
                "comment_id": 100,
                "body_snippet": "Fix the null check",
                "category": "bug",
                "confidence": 0.95,
                "actionable": True,
                "aggressiveness_level": "standard",
                "prompt_hash": "abc123",
            },
            {
                "comment_id": 200,
                "body_snippet": "Nice work!",
                "category": "praise",
                "confidence": 0.9,
                "actionable": False,
                "aggressiveness_level": "standard",
                "prompt_hash": "abc123",
            },
        ]
        await repo.save_classifications(run_id, classifications)
        # Should call execute for each classification
        assert mock_db.execute.call_count == 2

    async def test_empty_classifications_no_calls(
        self, repo: MetricsRepository, mock_db: MagicMock,
    ) -> None:
        await repo.save_classifications(uuid4(), [])
        mock_db.execute.assert_not_called()


class TestGetMetricsSummary:
    """Tests for get_metrics_summary."""

    async def test_returns_response_model_structure(
        self, repo: MetricsRepository, mock_db: MagicMock,
    ) -> None:
        # Mock summary query result
        summary_row = MagicMock()
        summary_row.__getitem__ = lambda self, key: {
            "total_runs": 10,
            "total_comments_processed": 50,
            "total_fixed": 30,
            "total_failed": 10,
            "total_skipped": 10,
            "avg_latency_seconds": 15.5,
        }[key]

        # Mock daily buckets
        daily_row = MagicMock()
        daily_row.__getitem__ = lambda self, key: {
            "date": date(2026, 3, 1),
            "total_runs": 5,
            "fixed": 15,
            "failed": 5,
            "skipped": 5,
            "avg_latency_s": 14.0,
        }[key]

        # Mock aggressiveness breakdown
        agg_row = MagicMock()
        agg_row.__getitem__ = lambda self, key: {
            "aggressiveness_level": "standard",
            "runs": 8,
            "fixed": 25,
            "failed": 8,
            "skipped": 7,
        }[key]

        mock_db.fetch_one.return_value = summary_row
        mock_db.fetch_all.side_effect = [[daily_row], [agg_row]]

        result = await repo.get_metrics_summary(
            start=date(2026, 3, 1), end=date(2026, 3, 14),
        )

        assert isinstance(result, PRAutoFixMetricsResponse)
        assert isinstance(result.summary, PRAutoFixMetricsSummary)
        assert result.summary.total_runs == 10
        assert result.summary.fix_rate == pytest.approx(0.6)  # 30 / 50
        assert len(result.daily) == 1
        assert isinstance(result.daily[0], PRAutoFixDailyBucket)
        assert len(result.by_aggressiveness) == 1
        assert isinstance(result.by_aggressiveness[0], AggressivenessBreakdown)

    async def test_empty_data_returns_zero_summary(
        self, repo: MetricsRepository, mock_db: MagicMock,
    ) -> None:
        mock_db.fetch_one.return_value = None
        mock_db.fetch_all.return_value = []

        result = await repo.get_metrics_summary(
            start=date(2026, 3, 1), end=date(2026, 3, 14),
        )

        assert isinstance(result, PRAutoFixMetricsResponse)
        assert result.summary.total_runs == 0
        assert result.summary.fix_rate == 0.0
        assert result.daily == []
        assert result.by_aggressiveness == []

    async def test_profile_filter_passed_to_queries(
        self, repo: MetricsRepository, mock_db: MagicMock,
    ) -> None:
        mock_db.fetch_one.return_value = None
        mock_db.fetch_all.return_value = []

        await repo.get_metrics_summary(
            start=date(2026, 3, 1), end=date(2026, 3, 14),
            profile_id="my-profile",
        )

        # All three queries should include profile_id param
        for call in mock_db.fetch_one.call_args_list:
            assert "profile_id" in call[0][0]
        for call in mock_db.fetch_all.call_args_list:
            assert "profile_id" in call[0][0]

    async def test_aggressiveness_filter_passed_to_queries(
        self, repo: MetricsRepository, mock_db: MagicMock,
    ) -> None:
        mock_db.fetch_one.return_value = None
        mock_db.fetch_all.return_value = []

        await repo.get_metrics_summary(
            start=date(2026, 3, 1), end=date(2026, 3, 14),
            aggressiveness="critical",
        )

        # All three queries should include aggressiveness_level param
        for call in mock_db.fetch_one.call_args_list:
            assert "aggressiveness_level" in call[0][0]
        for call in mock_db.fetch_all.call_args_list:
            assert "aggressiveness_level" in call[0][0]


class TestGetClassifications:
    """Tests for get_classifications."""

    async def test_returns_paginated_response(
        self, repo: MetricsRepository, mock_db: MagicMock,
    ) -> None:
        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "comment_id": 123,
            "body_snippet": "Fix this",
            "category": "bug",
            "confidence": 0.9,
            "actionable": True,
            "aggressiveness_level": "standard",
            "prompt_hash": "abc123",
            "created_at": "2026-03-14T10:00:00Z",
        }[key]

        mock_db.fetch_scalar.return_value = 25
        mock_db.fetch_all.return_value = [row]

        result = await repo.get_classifications(
            start=date(2026, 3, 1), end=date(2026, 3, 14),
            limit=10, offset=0,
        )

        assert isinstance(result, ClassificationsResponse)
        assert result.total == 25
        assert len(result.classifications) == 1
        assert isinstance(result.classifications[0], ClassificationRecord)
        assert result.classifications[0].comment_id == 123
