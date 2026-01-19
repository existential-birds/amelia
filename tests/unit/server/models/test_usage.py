"""Tests for usage response models."""


from amelia.server.models.usage import (
    UsageByModel,
    UsageResponse,
    UsageSummary,
    UsageTrendPoint,
)


def test_usage_summary_required_fields() -> None:
    """UsageSummary requires core fields."""
    summary = UsageSummary(
        total_cost_usd=127.43,
        total_workflows=24,
        total_tokens=1_200_000,
        total_duration_ms=2_820_000,
    )
    assert summary.total_cost_usd == 127.43
    assert summary.total_workflows == 24
    assert summary.cache_hit_rate is None  # Optional


def test_usage_summary_with_efficiency_metrics() -> None:
    """UsageSummary accepts optional efficiency metrics."""
    summary = UsageSummary(
        total_cost_usd=127.43,
        total_workflows=24,
        total_tokens=1_200_000,
        total_duration_ms=2_820_000,
        cache_hit_rate=0.65,
        cache_savings_usd=42.50,
    )
    assert summary.cache_hit_rate == 0.65
    assert summary.cache_savings_usd == 42.50


def test_usage_trend_point() -> None:
    """UsageTrendPoint has date, cost, and workflows."""
    point = UsageTrendPoint(
        date="2026-01-15",
        cost_usd=12.34,
        workflows=3,
    )
    assert point.date == "2026-01-15"
    assert point.cost_usd == 12.34
    assert point.workflows == 3


def test_usage_by_model() -> None:
    """UsageByModel has model breakdown fields."""
    model = UsageByModel(
        model="claude-sonnet-4",
        workflows=18,
        tokens=892_000,
        cost_usd=42.17,
    )
    assert model.model == "claude-sonnet-4"
    assert model.tokens == 892_000


def test_usage_trend_point_with_by_model() -> None:
    """UsageTrendPoint should include optional by_model breakdown."""
    point = UsageTrendPoint(
        date="2026-01-15",
        cost_usd=10.50,
        workflows=5,
        by_model={"claude-sonnet-4": 6.30, "gpt-4o": 4.20},
    )

    assert point.by_model == {"claude-sonnet-4": 6.30, "gpt-4o": 4.20}


def test_usage_trend_point_by_model_defaults_to_none() -> None:
    """UsageTrendPoint.by_model should default to None for backwards compat."""
    point = UsageTrendPoint(
        date="2026-01-15",
        cost_usd=10.50,
        workflows=5,
    )

    assert point.by_model is None


def test_usage_by_model_with_trend_and_success() -> None:
    """UsageByModel should include trend data and success metrics."""
    model_usage = UsageByModel(
        model="claude-sonnet-4",
        workflows=18,
        tokens=892000,
        cost_usd=42.17,
        trend=[10.5, 12.3, 8.7, 10.67],
        successful_workflows=16,
        success_rate=0.889,
    )

    assert model_usage.trend == [10.5, 12.3, 8.7, 10.67]
    assert model_usage.successful_workflows == 16
    assert model_usage.success_rate == 0.889


def test_usage_by_model_new_fields_default_to_none() -> None:
    """New UsageByModel fields should default to None for backwards compat."""
    model_usage = UsageByModel(
        model="claude-sonnet-4",
        workflows=18,
        tokens=892000,
        cost_usd=42.17,
    )

    assert model_usage.trend is None
    assert model_usage.successful_workflows is None
    assert model_usage.success_rate is None


def test_usage_response_complete() -> None:
    """UsageResponse combines all components."""
    response = UsageResponse(
        summary=UsageSummary(
            total_cost_usd=127.43,
            total_workflows=24,
            total_tokens=1_200_000,
            total_duration_ms=2_820_000,
        ),
        trend=[
            UsageTrendPoint(date="2026-01-15", cost_usd=12.34, workflows=3),
        ],
        by_model=[
            UsageByModel(model="claude-sonnet-4", workflows=18, tokens=892_000, cost_usd=42.17),
        ],
    )
    assert len(response.trend) == 1
    assert len(response.by_model) == 1


def test_usage_summary_with_comparison_and_success() -> None:
    """UsageSummary should include period comparison and success metrics."""
    summary = UsageSummary(
        total_cost_usd=127.50,
        total_workflows=24,
        total_tokens=1200000,
        total_duration_ms=2820000,
        previous_period_cost_usd=100.00,
        successful_workflows=20,
        success_rate=0.833,
    )

    assert summary.previous_period_cost_usd == 100.00
    assert summary.successful_workflows == 20
    assert summary.success_rate == 0.833


def test_usage_summary_new_fields_default_to_none() -> None:
    """New UsageSummary fields should default to None for backwards compat."""
    summary = UsageSummary(
        total_cost_usd=127.50,
        total_workflows=24,
        total_tokens=1200000,
        total_duration_ms=2820000,
    )

    assert summary.previous_period_cost_usd is None
    assert summary.successful_workflows is None
    assert summary.success_rate is None
