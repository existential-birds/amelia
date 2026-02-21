"""Configuration endpoint for dashboard."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from amelia.server.database import ProfileRepository, SettingsRepository
from amelia.server.dependencies import get_profile_repository, get_settings_repository


router = APIRouter(prefix="/config", tags=["config"])


class ProfileInfo(BaseModel):
    """Profile information for display in UI.

    Note: With per-agent configuration, driver/model are extracted from
    the 'developer' agent (or first available agent) for display purposes.
    """

    name: str = Field(description="Profile name")
    driver: str = Field(description="Driver type ('api' or 'cli')")
    model: str = Field(description="Model name")


class ConfigResponse(BaseModel):
    """Response model for server configuration."""

    repo_root: str = Field(
        description="Repository root directory for file access"
    )
    max_concurrent: int = Field(
        description="Maximum concurrent workflows"
    )
    active_profile: str = Field(
        description="Active profile name from database"
    )
    active_profile_info: ProfileInfo | None = Field(
        default=None,
        description="Full profile info for the active profile"
    )


@router.get("", response_model=ConfigResponse)
async def get_server_config(
    profile_repo: ProfileRepository = Depends(get_profile_repository),
    settings_repo: SettingsRepository = Depends(get_settings_repository),
) -> ConfigResponse:
    """Get server configuration for dashboard.

    Returns:
        Server configuration including repo_root, max_concurrent, active_profile,
        and active_profile_info.
    """
    # Get server settings for max_concurrent
    server_settings = await settings_repo.get_server_settings()

    # Get active profile
    active_profile = await profile_repo.get_active_profile()

    # Build response based on whether there's an active profile
    if active_profile is None:
        return ConfigResponse(
            repo_root="",
            max_concurrent=server_settings.max_concurrent,
            active_profile="",
            active_profile_info=None,
        )

    # Extract driver/model from a representative agent for display
    # Prefer 'developer' agent, fall back to first available agent
    display_driver = ""
    display_model = ""
    if active_profile.agents:
        agent_name = "developer" if "developer" in active_profile.agents else next(iter(active_profile.agents))
        agent_config = active_profile.agents[agent_name]
        display_driver = agent_config.driver
        display_model = agent_config.model

    profile_info = ProfileInfo(
        name=active_profile.name,
        driver=display_driver,
        model=display_model,
    )

    return ConfigResponse(
        repo_root=active_profile.repo_root,
        max_concurrent=server_settings.max_concurrent,
        active_profile=active_profile.name,
        active_profile_info=profile_info,
    )
