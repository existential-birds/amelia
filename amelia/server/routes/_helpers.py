"""Shared route helper functions."""

from __future__ import annotations

from fastapi import HTTPException

from amelia.core.types import Profile, TrackerType
from amelia.server.database import ProfileRepository


async def resolve_github_profile(
    profile_name: str | None,
    profile_repo: ProfileRepository,
    *,
    require_github: bool = True,
) -> Profile:
    """Resolve a profile, optionally requiring it to be a GitHub-tracked profile.

    Args:
        profile_name: Profile name to look up. If None, falls back to active profile.
        profile_repo: Profile repository for lookup.
        require_github: When True, raises 400 if the profile is not a GitHub tracker.

    Returns:
        Resolved Profile instance.

    Raises:
        HTTPException: 404 if named profile not found, 400 if no active profile or
            profile uses a non-GitHub tracker when require_github is True.
    """
    if profile_name is not None:
        profile = await profile_repo.get_profile(profile_name)
        if profile is None:
            raise HTTPException(
                status_code=404,
                detail=f"Profile '{profile_name}' not found",
            )
    else:
        profile = await profile_repo.get_active_profile()
        if profile is None:
            raise HTTPException(
                status_code=400,
                detail="No active profile set. Provide a profile name or set an active profile.",
            )

    if require_github and profile.tracker != TrackerType.GITHUB:
        raise HTTPException(
            status_code=400,
            detail=f"Profile '{profile.name}' uses tracker '{profile.tracker}', not github",
        )

    return profile
