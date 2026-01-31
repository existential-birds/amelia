"""Tests for WorkflowRepository usage trend methods."""

from datetime import UTC, date, datetime

import pytest

from amelia.server.database.connection import Database
from amelia.server.database.repository import WorkflowRepository
from amelia.server.models.state import ServerExecutionState
from amelia.server.models.tokens import TokenUsage


class TestUsageTrend:
    """Tests for get_usage_trend with per-model breakdown."""

    @pytest.fixture
    async def db_with_token_usage(
        self, db_with_schema: Database
    ) -> Database:
        """Create database with token usage data across multiple days and models.

        Creates test data with:
        - 3 days of data (Jan 15-17, 2026)
        - Multiple models per day
        - Multiple workflows

        Returns:
            Database with token usage records.
        """
        repo = WorkflowRepository(db_with_schema)

        # Create workflows
        wf1 = ServerExecutionState(
            id="wf-usage-1",
            issue_id="ISSUE-1",
            worktree_path="/tmp/test-usage-1",
            workflow_status="completed",
            started_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
        )
        wf2 = ServerExecutionState(
            id="wf-usage-2",
            issue_id="ISSUE-2",
            worktree_path="/tmp/test-usage-2",
            workflow_status="completed",
            started_at=datetime(2026, 1, 16, 10, 0, 0, tzinfo=UTC),
        )
        wf3 = ServerExecutionState(
            id="wf-usage-3",
            issue_id="ISSUE-3",
            worktree_path="/tmp/test-usage-3",
            workflow_status="completed",
            started_at=datetime(2026, 1, 17, 10, 0, 0, tzinfo=UTC),
        )
        await repo.create(wf1)
        await repo.create(wf2)
        await repo.create(wf3)

        # Day 1 (Jan 15): wf1 with sonnet and opus
        await repo.save_token_usage(
            TokenUsage(
                workflow_id="wf-usage-1",
                agent="architect",
                model="claude-sonnet-4-20250514",
                input_tokens=1000,
                output_tokens=500,
                cost_usd=0.01,
                duration_ms=5000,
                num_turns=3,
                timestamp=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
            )
        )
        await repo.save_token_usage(
            TokenUsage(
                workflow_id="wf-usage-1",
                agent="developer",
                model="claude-opus-4-20250514",
                input_tokens=2000,
                output_tokens=1000,
                cost_usd=0.05,
                duration_ms=10000,
                num_turns=5,
                timestamp=datetime(2026, 1, 15, 11, 0, 0, tzinfo=UTC),
            )
        )

        # Day 2 (Jan 16): wf2 with sonnet only
        await repo.save_token_usage(
            TokenUsage(
                workflow_id="wf-usage-2",
                agent="architect",
                model="claude-sonnet-4-20250514",
                input_tokens=1500,
                output_tokens=700,
                cost_usd=0.015,
                duration_ms=6000,
                num_turns=4,
                timestamp=datetime(2026, 1, 16, 10, 0, 0, tzinfo=UTC),
            )
        )
        await repo.save_token_usage(
            TokenUsage(
                workflow_id="wf-usage-2",
                agent="developer",
                model="claude-sonnet-4-20250514",
                input_tokens=2500,
                output_tokens=1200,
                cost_usd=0.025,
                duration_ms=12000,
                num_turns=6,
                timestamp=datetime(2026, 1, 16, 11, 0, 0, tzinfo=UTC),
            )
        )

        # Day 3 (Jan 17): wf3 with opus only
        await repo.save_token_usage(
            TokenUsage(
                workflow_id="wf-usage-3",
                agent="architect",
                model="claude-opus-4-20250514",
                input_tokens=3000,
                output_tokens=1500,
                cost_usd=0.08,
                duration_ms=15000,
                num_turns=7,
                timestamp=datetime(2026, 1, 17, 10, 0, 0, tzinfo=UTC),
            )
        )

        return db_with_schema

    async def test_get_usage_trend_includes_by_model(
        self, db_with_token_usage: Database
    ) -> None:
        """get_usage_trend should include per-model breakdown."""
        repo = WorkflowRepository(db_with_token_usage)

        trend = await repo.get_usage_trend(
            start_date=date(2026, 1, 15),
            end_date=date(2026, 1, 17),
        )

        # Check that by_model is included
        for point in trend:
            assert "by_model" in point
            assert isinstance(point["by_model"], dict)

    async def test_get_usage_trend_by_model_has_correct_costs(
        self, db_with_token_usage: Database
    ) -> None:
        """by_model breakdown should have correct per-model costs."""
        repo = WorkflowRepository(db_with_token_usage)

        trend = await repo.get_usage_trend(
            start_date=date(2026, 1, 15),
            end_date=date(2026, 1, 17),
        )

        # Find Jan 15 data point (has both sonnet and opus)
        jan15 = next(p for p in trend if p["date"] == "2026-01-15")
        assert "claude-sonnet-4-20250514" in jan15["by_model"]
        assert "claude-opus-4-20250514" in jan15["by_model"]
        assert jan15["by_model"]["claude-sonnet-4-20250514"] == pytest.approx(
            0.01, rel=1e-6
        )
        assert jan15["by_model"]["claude-opus-4-20250514"] == pytest.approx(
            0.05, rel=1e-6
        )

        # Find Jan 16 data point (sonnet only)
        jan16 = next(p for p in trend if p["date"] == "2026-01-16")
        assert "claude-sonnet-4-20250514" in jan16["by_model"]
        assert "claude-opus-4-20250514" not in jan16["by_model"]
        assert jan16["by_model"]["claude-sonnet-4-20250514"] == pytest.approx(
            0.04, rel=1e-6  # 0.015 + 0.025
        )

        # Find Jan 17 data point (opus only)
        jan17 = next(p for p in trend if p["date"] == "2026-01-17")
        assert "claude-opus-4-20250514" in jan17["by_model"]
        assert "claude-sonnet-4-20250514" not in jan17["by_model"]
        assert jan17["by_model"]["claude-opus-4-20250514"] == pytest.approx(
            0.08, rel=1e-6
        )

    async def test_get_usage_trend_by_model_empty_for_no_data(
        self, db_with_schema: Database
    ) -> None:
        """by_model should be empty dict when no usage data exists."""
        repo = WorkflowRepository(db_with_schema)

        trend = await repo.get_usage_trend(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 5),
        )

        # Should return empty list since no data exists
        assert trend == []

    async def test_get_usage_trend_totals_still_correct(
        self, db_with_token_usage: Database
    ) -> None:
        """Adding by_model should not change existing cost_usd totals."""
        repo = WorkflowRepository(db_with_token_usage)

        trend = await repo.get_usage_trend(
            start_date=date(2026, 1, 15),
            end_date=date(2026, 1, 17),
        )

        # Verify original fields still present and correct
        jan15 = next(p for p in trend if p["date"] == "2026-01-15")
        assert jan15["cost_usd"] == pytest.approx(0.06, rel=1e-6)  # 0.01 + 0.05
        assert jan15["workflows"] == 1

        jan16 = next(p for p in trend if p["date"] == "2026-01-16")
        assert jan16["cost_usd"] == pytest.approx(0.04, rel=1e-6)  # 0.015 + 0.025
        assert jan16["workflows"] == 1

        jan17 = next(p for p in trend if p["date"] == "2026-01-17")
        assert jan17["cost_usd"] == pytest.approx(0.08, rel=1e-6)
        assert jan17["workflows"] == 1


class TestUsageSummaryWithSuccessMetrics:
    """Tests for get_usage_summary with success metrics and period comparison."""

    @pytest.fixture
    async def db_with_workflows_and_usage(
        self, db_with_schema: Database
    ) -> Database:
        """Create database with workflows of various statuses and token usage.

        Creates test data with:
        - Previous period (Jan 8-14, 2026): 2 workflows, $0.10 total
        - Current period (Jan 15-21, 2026): 4 workflows (3 completed, 1 failed)

        Returns:
            Database with workflow and token usage records.
        """
        repo = WorkflowRepository(db_with_schema)

        # Previous period workflows (Jan 8-14)
        wf_prev1 = ServerExecutionState(
            id="wf-prev-1",
            issue_id="ISSUE-P1",
            worktree_path="/tmp/test-prev-1",
            workflow_status="completed",
            started_at=datetime(2026, 1, 10, 10, 0, 0, tzinfo=UTC),
            completed_at=datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC),
        )
        wf_prev2 = ServerExecutionState(
            id="wf-prev-2",
            issue_id="ISSUE-P2",
            worktree_path="/tmp/test-prev-2",
            workflow_status="completed",
            started_at=datetime(2026, 1, 12, 10, 0, 0, tzinfo=UTC),
            completed_at=datetime(2026, 1, 12, 12, 0, 0, tzinfo=UTC),
        )
        await repo.create(wf_prev1)
        await repo.create(wf_prev2)

        # Previous period token usage
        await repo.save_token_usage(
            TokenUsage(
                workflow_id="wf-prev-1",
                agent="architect",
                model="claude-sonnet-4-20250514",
                input_tokens=1000,
                output_tokens=500,
                cost_usd=0.04,
                duration_ms=5000,
                num_turns=3,
                timestamp=datetime(2026, 1, 10, 10, 0, 0, tzinfo=UTC),
            )
        )
        await repo.save_token_usage(
            TokenUsage(
                workflow_id="wf-prev-2",
                agent="architect",
                model="claude-sonnet-4-20250514",
                input_tokens=1200,
                output_tokens=600,
                cost_usd=0.06,
                duration_ms=6000,
                num_turns=4,
                timestamp=datetime(2026, 1, 12, 10, 0, 0, tzinfo=UTC),
            )
        )

        # Current period workflows (Jan 15-21): 3 completed, 1 failed
        wf_curr1 = ServerExecutionState(
            id="wf-curr-1",
            issue_id="ISSUE-C1",
            worktree_path="/tmp/test-curr-1",
            workflow_status="completed",
            started_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
            completed_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        )
        wf_curr2 = ServerExecutionState(
            id="wf-curr-2",
            issue_id="ISSUE-C2",
            worktree_path="/tmp/test-curr-2",
            workflow_status="completed",
            started_at=datetime(2026, 1, 16, 10, 0, 0, tzinfo=UTC),
            completed_at=datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC),
        )
        wf_curr3 = ServerExecutionState(
            id="wf-curr-3",
            issue_id="ISSUE-C3",
            worktree_path="/tmp/test-curr-3",
            workflow_status="completed",
            started_at=datetime(2026, 1, 17, 10, 0, 0, tzinfo=UTC),
            completed_at=datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC),
        )
        wf_curr4 = ServerExecutionState(
            id="wf-curr-4",
            issue_id="ISSUE-C4",
            worktree_path="/tmp/test-curr-4",
            workflow_status="failed",
            started_at=datetime(2026, 1, 18, 10, 0, 0, tzinfo=UTC),
            completed_at=datetime(2026, 1, 18, 11, 0, 0, tzinfo=UTC),
            failure_reason="Test failure",
        )
        await repo.create(wf_curr1)
        await repo.create(wf_curr2)
        await repo.create(wf_curr3)
        await repo.create(wf_curr4)

        # Current period token usage (one per workflow)
        await repo.save_token_usage(
            TokenUsage(
                workflow_id="wf-curr-1",
                agent="architect",
                model="claude-sonnet-4-20250514",
                input_tokens=1000,
                output_tokens=500,
                cost_usd=0.03,
                duration_ms=5000,
                num_turns=3,
                timestamp=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
            )
        )
        await repo.save_token_usage(
            TokenUsage(
                workflow_id="wf-curr-2",
                agent="architect",
                model="claude-sonnet-4-20250514",
                input_tokens=1100,
                output_tokens=550,
                cost_usd=0.035,
                duration_ms=5500,
                num_turns=3,
                timestamp=datetime(2026, 1, 16, 10, 0, 0, tzinfo=UTC),
            )
        )
        await repo.save_token_usage(
            TokenUsage(
                workflow_id="wf-curr-3",
                agent="architect",
                model="claude-sonnet-4-20250514",
                input_tokens=1200,
                output_tokens=600,
                cost_usd=0.04,
                duration_ms=6000,
                num_turns=4,
                timestamp=datetime(2026, 1, 17, 10, 0, 0, tzinfo=UTC),
            )
        )
        await repo.save_token_usage(
            TokenUsage(
                workflow_id="wf-curr-4",
                agent="architect",
                model="claude-sonnet-4-20250514",
                input_tokens=500,
                output_tokens=250,
                cost_usd=0.015,
                duration_ms=2500,
                num_turns=2,
                timestamp=datetime(2026, 1, 18, 10, 0, 0, tzinfo=UTC),
            )
        )

        return db_with_schema

    async def test_get_usage_summary_includes_success_metrics(
        self, db_with_workflows_and_usage: Database
    ) -> None:
        """get_usage_summary should include success rate and previous period cost."""
        repo = WorkflowRepository(db_with_workflows_and_usage)

        summary = await repo.get_usage_summary(
            start_date=date(2026, 1, 15),
            end_date=date(2026, 1, 21),
        )

        assert "previous_period_cost_usd" in summary
        assert "successful_workflows" in summary
        assert "success_rate" in summary
        assert isinstance(summary["success_rate"], (int, float))

    async def test_get_usage_summary_previous_period_cost(
        self, db_with_workflows_and_usage: Database
    ) -> None:
        """previous_period_cost_usd should be cost from same-length period before."""
        repo = WorkflowRepository(db_with_workflows_and_usage)

        # Jan 15-21 is 7 days, so previous period is Jan 8-14
        summary = await repo.get_usage_summary(
            start_date=date(2026, 1, 15),
            end_date=date(2026, 1, 21),
        )

        # Previous period cost: $0.04 + $0.06 = $0.10
        assert summary["previous_period_cost_usd"] == pytest.approx(0.10, rel=1e-6)

    async def test_get_usage_summary_successful_workflows(
        self, db_with_workflows_and_usage: Database
    ) -> None:
        """successful_workflows should count only completed workflows."""
        repo = WorkflowRepository(db_with_workflows_and_usage)

        summary = await repo.get_usage_summary(
            start_date=date(2026, 1, 15),
            end_date=date(2026, 1, 21),
        )

        # 3 completed, 1 failed in current period
        assert summary["successful_workflows"] == 3

    async def test_get_usage_summary_success_rate(
        self, db_with_workflows_and_usage: Database
    ) -> None:
        """success_rate should be percentage of completed workflows."""
        repo = WorkflowRepository(db_with_workflows_and_usage)

        summary = await repo.get_usage_summary(
            start_date=date(2026, 1, 15),
            end_date=date(2026, 1, 21),
        )

        # 3 completed out of 4 total = 0.75 (ratio)
        assert summary["success_rate"] == pytest.approx(0.75, rel=1e-6)

    async def test_get_usage_summary_zero_workflows(
        self, db_with_schema: Database
    ) -> None:
        """success_rate should be 0 when no workflows exist."""
        repo = WorkflowRepository(db_with_schema)

        summary = await repo.get_usage_summary(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 7),
        )

        assert summary["successful_workflows"] == 0
        assert summary["success_rate"] == 0.0
        assert summary["previous_period_cost_usd"] == 0.0


class TestUsageByModelWithTrendAndSuccess:
    """Tests for get_usage_by_model with trend array and success metrics."""

    @pytest.fixture
    async def db_with_multi_model_usage(
        self, db_with_schema: Database
    ) -> Database:
        """Create database with multiple models across multiple days.

        Creates test data with:
        - 4 workflows across Jan 15-18, 2026
        - 2 models: claude-sonnet-4-20250514 and claude-opus-4-20250514
        - Mixed success states (3 completed, 1 failed)

        Returns:
            Database with workflow and token usage records.
        """
        repo = WorkflowRepository(db_with_schema)

        # Create workflows with mixed statuses
        wf1 = ServerExecutionState(
            id="wf-model-1",
            issue_id="ISSUE-M1",
            worktree_path="/tmp/test-model-1",
            workflow_status="completed",
            started_at=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
            completed_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        )
        wf2 = ServerExecutionState(
            id="wf-model-2",
            issue_id="ISSUE-M2",
            worktree_path="/tmp/test-model-2",
            workflow_status="completed",
            started_at=datetime(2026, 1, 16, 10, 0, 0, tzinfo=UTC),
            completed_at=datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC),
        )
        wf3 = ServerExecutionState(
            id="wf-model-3",
            issue_id="ISSUE-M3",
            worktree_path="/tmp/test-model-3",
            workflow_status="completed",
            started_at=datetime(2026, 1, 17, 10, 0, 0, tzinfo=UTC),
            completed_at=datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC),
        )
        wf4 = ServerExecutionState(
            id="wf-model-4",
            issue_id="ISSUE-M4",
            worktree_path="/tmp/test-model-4",
            workflow_status="failed",
            started_at=datetime(2026, 1, 18, 10, 0, 0, tzinfo=UTC),
            completed_at=datetime(2026, 1, 18, 11, 0, 0, tzinfo=UTC),
            failure_reason="Test failure",
        )
        await repo.create(wf1)
        await repo.create(wf2)
        await repo.create(wf3)
        await repo.create(wf4)

        # wf1 (Jan 15): uses sonnet only
        await repo.save_token_usage(
            TokenUsage(
                workflow_id="wf-model-1",
                agent="architect",
                model="claude-sonnet-4-20250514",
                input_tokens=1000,
                output_tokens=500,
                cost_usd=0.03,
                duration_ms=5000,
                num_turns=3,
                timestamp=datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
            )
        )

        # wf2 (Jan 16): uses sonnet and opus
        await repo.save_token_usage(
            TokenUsage(
                workflow_id="wf-model-2",
                agent="architect",
                model="claude-sonnet-4-20250514",
                input_tokens=1100,
                output_tokens=550,
                cost_usd=0.035,
                duration_ms=5500,
                num_turns=3,
                timestamp=datetime(2026, 1, 16, 10, 0, 0, tzinfo=UTC),
            )
        )
        await repo.save_token_usage(
            TokenUsage(
                workflow_id="wf-model-2",
                agent="developer",
                model="claude-opus-4-20250514",
                input_tokens=2000,
                output_tokens=1000,
                cost_usd=0.08,
                duration_ms=10000,
                num_turns=5,
                timestamp=datetime(2026, 1, 16, 11, 0, 0, tzinfo=UTC),
            )
        )

        # wf3 (Jan 17): uses opus only
        await repo.save_token_usage(
            TokenUsage(
                workflow_id="wf-model-3",
                agent="architect",
                model="claude-opus-4-20250514",
                input_tokens=2500,
                output_tokens=1200,
                cost_usd=0.10,
                duration_ms=12000,
                num_turns=6,
                timestamp=datetime(2026, 1, 17, 10, 0, 0, tzinfo=UTC),
            )
        )

        # wf4 (Jan 18, failed): uses sonnet
        await repo.save_token_usage(
            TokenUsage(
                workflow_id="wf-model-4",
                agent="architect",
                model="claude-sonnet-4-20250514",
                input_tokens=500,
                output_tokens=250,
                cost_usd=0.015,
                duration_ms=2500,
                num_turns=2,
                timestamp=datetime(2026, 1, 18, 10, 0, 0, tzinfo=UTC),
            )
        )

        return db_with_schema

    async def test_get_usage_by_model_includes_trend_and_success(
        self, db_with_multi_model_usage: Database
    ) -> None:
        """get_usage_by_model should include trend array and success metrics."""
        repo = WorkflowRepository(db_with_multi_model_usage)

        by_model = await repo.get_usage_by_model(
            start_date=date(2026, 1, 15),
            end_date=date(2026, 1, 21),
        )

        for model_data in by_model:
            assert "trend" in model_data
            assert isinstance(model_data["trend"], list)
            assert "successful_workflows" in model_data
            assert "success_rate" in model_data

    async def test_get_usage_by_model_trend_has_correct_daily_costs(
        self, db_with_multi_model_usage: Database
    ) -> None:
        """trend array should contain correct daily costs for each model."""
        repo = WorkflowRepository(db_with_multi_model_usage)

        by_model = await repo.get_usage_by_model(
            start_date=date(2026, 1, 15),
            end_date=date(2026, 1, 21),
        )

        # Find sonnet model data (used on Jan 15, 16, 18)
        sonnet = next(m for m in by_model if m["model"] == "claude-sonnet-4-20250514")
        # Trend should have 7 days worth of data points
        assert len(sonnet["trend"]) == 7

        # Find opus model data (used on Jan 16, 17)
        opus = next(m for m in by_model if m["model"] == "claude-opus-4-20250514")
        assert len(opus["trend"]) == 7

    async def test_get_usage_by_model_success_metrics_per_model(
        self, db_with_multi_model_usage: Database
    ) -> None:
        """success metrics should be calculated per model."""
        repo = WorkflowRepository(db_with_multi_model_usage)

        by_model = await repo.get_usage_by_model(
            start_date=date(2026, 1, 15),
            end_date=date(2026, 1, 21),
        )

        # Sonnet: used by wf1 (completed), wf2 (completed), wf4 (failed) = 2/3 = 0.6667 (ratio)
        sonnet = next(m for m in by_model if m["model"] == "claude-sonnet-4-20250514")
        assert sonnet["successful_workflows"] == 2
        assert sonnet["success_rate"] == pytest.approx(0.6667, rel=0.01)

        # Opus: used by wf2 (completed), wf3 (completed) = 2/2 = 1.0 (ratio)
        opus = next(m for m in by_model if m["model"] == "claude-opus-4-20250514")
        assert opus["successful_workflows"] == 2
        assert opus["success_rate"] == pytest.approx(1.0, rel=0.01)
