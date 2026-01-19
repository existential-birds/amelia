"""Configuration endpoint for dashboard."""
import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from amelia.server.config import ServerConfig
from amelia.server.dependencies import get_config


router = APIRouter(prefix="/config", tags=["config"])


def _load_settings() -> dict[str, Any]:
    """Load settings from settings.amelia.yaml.

    Returns:
        Settings dict, or empty dict if not found.
    """
    settings_path = Path("settings.amelia.yaml")
    env_path = os.environ.get("AMELIA_SETTINGS")
    if env_path:
        settings_path = Path(env_path)

    try:
        with settings_path.open() as f:
            data = yaml.safe_load(f)
        return data or {}
    except (FileNotFoundError, PermissionError, yaml.YAMLError):
        return {}


class ProfileInfo(BaseModel):
    """Profile information for display in UI."""

    name: str = Field(description="Profile name")
    driver: str = Field(description="Driver type (e.g., 'api:openrouter', 'cli:claude')")
    model: str = Field(description="Model name")


class ConfigResponse(BaseModel):
    """Response model for server configuration."""

    working_dir: str = Field(
        description="Working directory for file access"
    )
    max_concurrent: int = Field(
        description="Maximum concurrent workflows"
    )
    active_profile: str = Field(
        description="Active profile name from settings.amelia.yaml"
    )
    active_profile_info: ProfileInfo | None = Field(
        default=None,
        description="Full profile info for the active profile"
    )


@router.get("", response_model=ConfigResponse)
async def get_server_config(
    config: ServerConfig = Depends(get_config),
) -> ConfigResponse:
    """Get server configuration for dashboard.

    Returns:
        Server configuration including working_dir, max_concurrent, active_profile,
        and active_profile_info.
    """
    settings = _load_settings()
    active_profile_name = settings.get("active_profile", "")

    # Get full profile info if available
    profile_info = None
    if active_profile_name:
        profiles = settings.get("profiles", {})
        profile_data = profiles.get(active_profile_name, {})
        if profile_data:
            profile_info = ProfileInfo(
                name=active_profile_name,
                driver=profile_data.get("driver", "unknown"),
                model=profile_data.get("model", "unknown"),
            )

    return ConfigResponse(
        working_dir=str(config.working_dir),
        max_concurrent=config.max_concurrent,
        active_profile=active_profile_name,
        active_profile_info=profile_info,
    )
