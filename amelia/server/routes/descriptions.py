"""Descriptions endpoints — AI-powered condensation of issue bodies."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from amelia.core.types import TrackerType
from amelia.drivers.factory import get_driver
from amelia.server.database import ProfileRepository
from amelia.server.dependencies import get_profile_repository
from amelia.server.models.requests import CondenseDescriptionRequest, CondenseDescriptionResponse


router = APIRouter(prefix="/descriptions", tags=["descriptions"])

CONDENSE_SYSTEM_PROMPT = (
    "Extract the task description from this GitHub issue body. "
    "Keep the problem statement and acceptance criteria. "
    "Remove implementation plans, technical specs, and checklists. "
    "Return plain text under 4000 characters."
)


@router.post("/condense", response_model=CondenseDescriptionResponse)
async def condense_description(
    request: CondenseDescriptionRequest,
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> CondenseDescriptionResponse:
    """Condense a long GitHub issue body using an LLM.

    Args:
        request: Condense request with description and optional profile name.
        profile_repo: Profile repository dependency.

    Returns:
        CondenseDescriptionResponse with the condensed text.

    Raises:
        HTTPException: 400 if profile doesn't use GitHub tracker or no active profile,
            404 if the named profile is not found, 500 if LLM call fails.
    """
    if request.profile is not None:
        profile = await profile_repo.get_profile(request.profile)
        if profile is None:
            raise HTTPException(
                status_code=404,
                detail=f"Profile '{request.profile}' not found",
            )
        if profile.tracker != TrackerType.GITHUB:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Profile '{request.profile}' uses tracker '{profile.tracker}', not github"
                ),
            )
    else:
        profile = await profile_repo.get_active_profile()
        if profile is None:
            raise HTTPException(
                status_code=400,
                detail="No active profile set. Provide a profile name or set an active profile.",
            )

    try:
        agent_cfg = profile.get_agent_config("architect")
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Profile '{profile.name}' has no 'architect' agent configured",
        ) from exc

    driver = get_driver(agent_cfg.driver, model=agent_cfg.model, cwd=".")

    try:
        result, _usage = await driver.generate(
            prompt=request.description,
            system_prompt=CONDENSE_SYSTEM_PROMPT,
        )
    except Exception as exc:
        logger.error("Failed to condense description", error=str(exc), profile=profile.name)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to condense description: {exc}",
        ) from exc

    return CondenseDescriptionResponse(condensed=str(result))
