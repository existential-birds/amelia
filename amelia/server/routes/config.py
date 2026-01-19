"""Configuration endpoint for dashboard."""
import os
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from amelia.server.config import ServerConfig
from amelia.server.dependencies import get_config


router = APIRouter(prefix="/config", tags=["config"])


def _get_active_profile() -> str:
    """Get active_profile from settings.amelia.yaml.

    Returns:
        Active profile name, or empty string if not found.
    """
    settings_path = Path("settings.amelia.yaml")
    env_path = os.environ.get("AMELIA_SETTINGS")
    if env_path:
        settings_path = Path(env_path)

    try:
        with settings_path.open() as f:
            data = yaml.safe_load(f)
        active_profile: str = data.get("active_profile", "")
        return active_profile
    except (FileNotFoundError, yaml.YAMLError):
        return ""


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


@router.get("", response_model=ConfigResponse)
async def get_server_config(
    config: ServerConfig = Depends(get_config),
) -> ConfigResponse:
    """Get server configuration for dashboard.

    Returns:
        Server configuration including working_dir, max_concurrent, and active_profile.
    """
    return ConfigResponse(
        working_dir=str(config.working_dir),
        max_concurrent=config.max_concurrent,
        active_profile=_get_active_profile(),
    )
