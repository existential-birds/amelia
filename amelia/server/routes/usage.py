"""Usage metrics routes.

``GET /usage`` is a projection of trajectory files: one SQL fetches the
trajectory index rows for the date range (plus the immediately preceding
window for period-over-period comparison), each file is loaded, and the
aggregation happens in Python via ``aggregate_usage``.
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from harbor.models.trajectories import Trajectory
from loguru import logger

from amelia.server.database import WorkflowRepository
from amelia.server.dependencies import get_repository
from amelia.server.models.usage import UsageResponse
from amelia.trajectory import aggregate_usage, load as load_trajectory


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

    # One SQL over the requested range plus the immediately preceding window
    # of equal length (feeds previous_period_cost_usd in the aggregation).
    period_days = (end_date - start_date).days + 1
    query_start = start_date - timedelta(days=period_days)
    rows = await repository.list_trajectory_paths(query_start, end_date)

    items: list[tuple[Trajectory, date, int | None]] = []
    skipped = 0
    for path_str, completed_on, duration_ms in rows:
        try:
            trajectory = load_trajectory(Path(path_str))
        except (OSError, ValueError) as exc:
            skipped += 1
            logger.warning(
                "Skipping unreadable trajectory file in usage aggregation",
                path=path_str,
                error=str(exc),
            )
            continue
        items.append((trajectory, completed_on, duration_ms))
    if skipped:
        logger.warning(
            "Usage aggregation skipped unreadable trajectory files",
            skipped=skipped,
            total=len(rows),
        )

    return aggregate_usage(items, start_date, end_date)
