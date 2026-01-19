"""Usage response models for the /api/usage endpoint."""

from pydantic import BaseModel


class UsageSummary(BaseModel):
    """Aggregated usage statistics for a time period."""

    total_cost_usd: float
    total_workflows: int
    total_tokens: int
    total_duration_ms: int
    cache_hit_rate: float | None = None
    cache_savings_usd: float | None = None
    previous_period_cost_usd: float | None = None  # For period-over-period comparison
    successful_workflows: int | None = None  # Workflows not cancelled or failed
    success_rate: float | None = None  # 0-1, successful_workflows / total_workflows


class UsageTrendPoint(BaseModel):
    """Single data point for the trend chart."""

    date: str  # ISO date YYYY-MM-DD
    cost_usd: float
    workflows: int
    by_model: dict[str, float] | None = None  # Per-model cost breakdown


class UsageByModel(BaseModel):
    """Usage breakdown for a single model."""

    model: str
    workflows: int
    tokens: int
    cost_usd: float
    cache_hit_rate: float | None = None
    cache_savings_usd: float | None = None
    trend: list[float] | None = None  # Daily costs array for sparkline
    successful_workflows: int | None = None  # Workflows not cancelled or failed
    success_rate: float | None = None  # 0-1, successful_workflows / workflows


class UsageResponse(BaseModel):
    """Complete response for GET /api/usage."""

    summary: UsageSummary
    trend: list[UsageTrendPoint]
    by_model: list[UsageByModel]
