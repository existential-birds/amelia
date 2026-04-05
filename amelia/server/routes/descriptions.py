"""Descriptions endpoints — AI-powered condensation of issue bodies."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from amelia.drivers.factory import get_driver
from amelia.server.database import ProfileRepository
from amelia.server.dependencies import get_profile_repository
from amelia.server.models.requests import CondenseDescriptionRequest, CondenseDescriptionResponse
from amelia.server.routes._helpers import resolve_github_profile
from amelia.services.condenser import condense_description


router = APIRouter(prefix="/descriptions", tags=["descriptions"])


@router.post("/condense", response_model=CondenseDescriptionResponse)
async def condense_description_route(
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
    profile = await resolve_github_profile(
        request.profile, profile_repo, require_github=True
    )

    try:
        agent_cfg = profile.get_agent_config(request.agent_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Profile '{profile.name}' has no '{request.agent_type}' agent configured",
        ) from exc

    driver = get_driver(agent_cfg.driver, model=agent_cfg.model, cwd=profile.repo_root)

    try:
        condensed, _session_id = await condense_description(request.description, driver)
    except Exception as exc:
        logger.error("Failed to condense description", error=str(exc), profile=profile.name)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to condense description: {exc}",
        ) from exc

    logger.debug("Description condensed", profile=profile.name, agent_type=request.agent_type)
    return CondenseDescriptionResponse(condensed=condensed)
