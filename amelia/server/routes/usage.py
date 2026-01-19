"""Usage metrics routes."""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from amelia.server.database import WorkflowRepository
from amelia.server.dependencies import get_repository
from amelia.server.models.usage import (
    UsageByModel,
    UsageResponse,
    UsageSummary,
    UsageTrendPoint,
)


router = APIRouter(prefix="/usage", tags=["usage"])

# Valid preset values
PRESETS = {"7d": 7, "30d": 30, "90d": 90, "all": 365 * 10}  # 'all' = 10 years


@router.get("", response_model=UsageResponse)
async def get_usage(
    start: date | None = Query(default=None, description="Start date (YYYY-MM-DD)"),
    end: date | None = Query(default=None, description="End date (YYYY-MM-DD)"),
    preset: str | None = Query(default=None, description="Preset: 7d, 30d, 90d, all"),
    repository: WorkflowRepository = Depends(get_repository),
) -> UsageResponse:
    """Get usage metrics for a date range.

    Either provide start/end dates or a preset (7d, 30d, 90d, all).
    Defaults to preset=30d if no parameters provided.

    Args:
        start: Start date (inclusive).
        end: End date (inclusive).
        preset: Preset duration.
        repository: Repository dependency.

    Returns:
        UsageResponse with summary, trend, and by_model data.

    Raises:
        HTTPException: 400 if invalid preset or date combination.
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
        start_date = start
        end_date = end
    elif preset is not None:
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
    else:
        # Default to 30d
        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=29)

    # Fetch data in parallel conceptually (SQLite is single-threaded but this is the pattern)
    summary_data = await repository.get_usage_summary(
        start_date=start_date,
        end_date=end_date,
    )
    trend_data = await repository.get_usage_trend(
        start_date=start_date,
        end_date=end_date,
    )
    by_model_data = await repository.get_usage_by_model(
        start_date=start_date,
        end_date=end_date,
    )

    return UsageResponse(
        summary=UsageSummary(**summary_data),
        trend=[UsageTrendPoint(**t) for t in trend_data],
        by_model=[UsageByModel(**m) for m in by_model_data],
    )
