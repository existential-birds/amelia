"""Tests for usage response models."""

import pytest
from pydantic import ValidationError

from amelia.server.models.usage import (
    UsageSummary,
    UsageTrendPoint,
    UsageByModel,
    UsageResponse,
)


def test_usage_summary_required_fields():
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


def test_usage_summary_with_efficiency_metrics():
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


def test_usage_trend_point():
    """UsageTrendPoint has date, cost, and workflows."""
    point = UsageTrendPoint(
        date="2026-01-15",
        cost_usd=12.34,
        workflows=3,
    )
    assert point.date == "2026-01-15"
    assert point.cost_usd == 12.34
    assert point.workflows == 3


def test_usage_by_model():
    """UsageByModel has model breakdown fields."""
    model = UsageByModel(
        model="claude-sonnet-4",
        workflows=18,
        tokens=892_000,
        cost_usd=42.17,
    )
    assert model.model == "claude-sonnet-4"
    assert model.tokens == 892_000


def test_usage_response_complete():
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
