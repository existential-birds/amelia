"""Response models for PR auto-fix metrics and classification audit endpoints."""

from pydantic import BaseModel


class PRAutoFixMetricsSummary(BaseModel):
    """Aggregated summary statistics for PR auto-fix pipeline runs."""

    total_runs: int
    total_comments_processed: int
    total_fixed: int
    total_failed: int
    total_skipped: int
    avg_latency_seconds: float
    fix_rate: float  # fixed / (fixed + failed + skipped), 0.0 when no data


class PRAutoFixDailyBucket(BaseModel):
    """Single day of aggregated PR auto-fix metrics."""

    date: str  # YYYY-MM-DD
    total_runs: int
    fixed: int
    failed: int
    skipped: int
    avg_latency_s: float


class AggressivenessBreakdown(BaseModel):
    """Metrics breakdown for a single aggressiveness level."""

    level: str
    runs: int
    fixed: int
    failed: int
    skipped: int
    fix_rate: float


class PRAutoFixMetricsResponse(BaseModel):
    """Complete response for GET /api/github/pr-autofix/metrics."""

    summary: PRAutoFixMetricsSummary
    daily: list[PRAutoFixDailyBucket]
    by_aggressiveness: list[AggressivenessBreakdown]


class ClassificationRecord(BaseModel):
    """Single classification audit log entry."""

    comment_id: int
    body_snippet: str
    category: str
    confidence: float
    actionable: bool
    aggressiveness_level: str
    prompt_hash: str | None
    created_at: str


class ClassificationsResponse(BaseModel):
    """Paginated response for GET /api/github/pr-autofix/classifications."""

    classifications: list[ClassificationRecord]
    total: int
