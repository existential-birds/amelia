"""Configuration endpoint for dashboard."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from amelia.server.config import ServerConfig
from amelia.server.dependencies import get_config


router = APIRouter(prefix="/config", tags=["config"])


class ConfigResponse(BaseModel):
    """Response model for server configuration."""

    working_dir: str = Field(
        description="Working directory for file access"
    )
    max_concurrent: int = Field(
        description="Maximum concurrent workflows"
    )


@router.get("", response_model=ConfigResponse)
async def get_server_config(
    config: ServerConfig = Depends(get_config),
) -> ConfigResponse:
    """Get server configuration for dashboard.

    Returns:
        Server configuration including working_dir and max_concurrent.
    """
    return ConfigResponse(
        working_dir=str(config.working_dir),
        max_concurrent=config.max_concurrent,
    )
