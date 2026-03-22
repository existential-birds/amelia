"""PR auto-fix metrics and classification audit routes."""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from amelia.server.database.metrics_repository import MetricsRepository
from amelia.server.dependencies import get_metrics_repository
from amelia.server.models.metrics import (
    ClassificationsResponse,
    PRAutoFixMetricsResponse,
)


router = APIRouter(prefix="/github/pr-autofix", tags=["pr-autofix-metrics"])

# Valid preset values (shared with usage routes)
PRESETS = {"7d": 7, "30d": 30, "90d": 90, "all": 365 * 10}


def _resolve_date_range(
    start: date | None,
    end: date | None,
    preset: str | None,
) -> tuple[date, date]:
    """Resolve start/end dates from query params.

    Args:
        start: Explicit start date.
        end: Explicit end date.
        preset: Preset duration string (7d, 30d, 90d, all).

    Returns:
        Tuple of (start_date, end_date).

    Raises:
        HTTPException: 400 on invalid combinations.
    """
    # Validate mutual exclusivity
    if preset is not None and (start is not None or end is not None):
        raise HTTPException(
            status_code=400,
            detail="Provide either start/end or preset, not both.",
        )

    # Validate date parameters
    if bool(start) != bool(end):
        raise HTTPException(
            status_code=400,
            detail="Both start and end must be provided together.",
        )
    if start and end and start > end:
        raise HTTPException(
            status_code=400,
            detail="Start date must be on or before end date.",
        )

    # Determine date range
    if start and end:
        return start, end

    if preset is not None:
        preset_value = preset.strip()
        if not preset_value:
            raise HTTPException(
                status_code=400,
                detail="Preset cannot be empty.",
            )
        if preset_value not in PRESETS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid preset '{preset_value}'. Valid: {', '.join(PRESETS.keys())}",
            )
        days = PRESETS[preset_value]
        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=days - 1)
        return start_date, end_date

    # Default to 30d
    end_date = datetime.now(UTC).date()
    start_date = end_date - timedelta(days=29)
    return start_date, end_date


@router.get("/metrics", response_model=PRAutoFixMetricsResponse)
async def get_metrics(
    start: date | None = Query(default=None, description="Start date (YYYY-MM-DD)"),
    end: date | None = Query(default=None, description="End date (YYYY-MM-DD)"),
    preset: str | None = Query(default=None, description="Preset: 7d, 30d, 90d, all"),
    profile: str | None = Query(default=None, description="Filter by profile ID"),
    aggressiveness: str | None = Query(
        default=None, description="Filter by aggressiveness level"
    ),
    metrics_repo: MetricsRepository = Depends(get_metrics_repository),
) -> PRAutoFixMetricsResponse:
    """Get aggregated PR auto-fix metrics for a date range.

    Returns summary stats, daily time series, and per-aggressiveness breakdown.
    Either provide start/end dates or a preset (7d, 30d, 90d, all).
    Defaults to preset=30d if no parameters provided.

    Args:
        start: Start date (inclusive).
        end: End date (inclusive).
        preset: Preset duration.
        profile: Optional profile ID filter.
        aggressiveness: Optional aggressiveness level filter.
        metrics_repo: Repository dependency.

    Returns:
        PRAutoFixMetricsResponse with summary, daily, and by_aggressiveness.

    Raises:
        HTTPException: 400 if invalid preset or date combination.
    """
    start_date, end_date = _resolve_date_range(start, end, preset)

    return await metrics_repo.get_metrics_summary(
        start=start_date,
        end=end_date,
        profile_id=profile,
        aggressiveness=aggressiveness,
    )


@router.get("/classifications", response_model=ClassificationsResponse)
async def get_classifications(
    start: date | None = Query(default=None, description="Start date (YYYY-MM-DD)"),
    end: date | None = Query(default=None, description="End date (YYYY-MM-DD)"),
    preset: str | None = Query(default=None, description="Preset: 7d, 30d, 90d, all"),
    limit: int = Query(default=50, ge=1, le=500, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
    metrics_repo: MetricsRepository = Depends(get_metrics_repository),
) -> ClassificationsResponse:
    """Get paginated classification audit log.

    Returns classification records with total count for pagination.
    Either provide start/end dates or a preset (7d, 30d, 90d, all).
    Defaults to preset=30d if no parameters provided.

    Args:
        start: Start date (inclusive).
        end: End date (inclusive).
        preset: Preset duration.
        limit: Maximum records per page.
        offset: Number of records to skip.
        metrics_repo: Repository dependency.

    Returns:
        ClassificationsResponse with classifications list and total count.

    Raises:
        HTTPException: 400 if invalid preset or date combination.
    """
    start_date, end_date = _resolve_date_range(start, end, preset)

    return await metrics_repo.get_classifications(
        start=start_date,
        end=end_date,
        limit=limit,
        offset=offset,
    )
