# amelia/server/routes/settings.py
"""API routes for server settings and profiles."""
import json
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from amelia.core.types import AgentConfig, DriverType, Profile, TrackerType
from amelia.server.database import (
    ProfileRepository,
    SettingsRepository,
)
from amelia.server.dependencies import (
    get_profile_repository,
    get_settings_repository,
)


router = APIRouter(prefix="/api", tags=["settings"])


# Response models
class ServerSettingsResponse(BaseModel):
    """Server settings API response."""

    log_retention_days: int
    log_retention_max_events: int
    trace_retention_days: int
    checkpoint_retention_days: int
    checkpoint_path: str
    websocket_idle_timeout_seconds: float
    workflow_start_timeout_seconds: float
    max_concurrent: int
    stream_tool_results: bool


class ServerSettingsUpdate(BaseModel):
    """Server settings update request."""

    log_retention_days: int | None = None
    log_retention_max_events: int | None = None
    trace_retention_days: int | None = None
    checkpoint_retention_days: int | None = None
    checkpoint_path: str | None = None
    websocket_idle_timeout_seconds: float | None = None
    workflow_start_timeout_seconds: float | None = None
    max_concurrent: int | None = None
    stream_tool_results: bool | None = None


class AgentConfigResponse(BaseModel):
    """Agent configuration in API response."""

    driver: str
    model: str
    options: dict[str, Any] = {}


class ProfileResponse(BaseModel):
    """Profile API response.

    With per-agent configuration, each agent can have its own driver/model.
    The agents dict maps agent names to their configurations.
    """

    id: str
    tracker: str
    working_dir: str
    plan_output_dir: str
    plan_path_pattern: str
    auto_approve_reviews: bool
    agents: dict[str, AgentConfigResponse]
    is_active: bool = False


class AgentConfigCreate(BaseModel):
    """Agent configuration for profile creation."""

    driver: DriverType
    model: str
    options: dict[str, Any] = {}


class ProfileCreate(BaseModel):
    """Profile creation request.

    Requires agents dict mapping agent names to their driver/model configurations.
    """

    id: str
    tracker: TrackerType = TrackerType.NOOP
    working_dir: str
    plan_output_dir: str = "docs/plans"
    plan_path_pattern: str = "docs/plans/{date}-{issue_key}.md"
    auto_approve_reviews: bool = False
    agents: dict[str, AgentConfigCreate]


class ProfileUpdate(BaseModel):
    """Profile update request.

    All fields are optional. To update agents, provide the full agents dict.
    """

    tracker: TrackerType | None = None
    working_dir: str | None = None
    plan_output_dir: str | None = None
    plan_path_pattern: str | None = None
    auto_approve_reviews: bool | None = None
    agents: dict[str, AgentConfigCreate] | None = None


# Server settings endpoints
@router.get("/settings", response_model=ServerSettingsResponse)
async def get_server_settings(
    repo: SettingsRepository = Depends(get_settings_repository),
) -> ServerSettingsResponse:
    """Get current server settings."""
    settings = await repo.get_server_settings()
    return ServerSettingsResponse(
        log_retention_days=settings.log_retention_days,
        log_retention_max_events=settings.log_retention_max_events,
        trace_retention_days=settings.trace_retention_days,
        checkpoint_retention_days=settings.checkpoint_retention_days,
        checkpoint_path=settings.checkpoint_path,
        websocket_idle_timeout_seconds=settings.websocket_idle_timeout_seconds,
        workflow_start_timeout_seconds=settings.workflow_start_timeout_seconds,
        max_concurrent=settings.max_concurrent,
        stream_tool_results=settings.stream_tool_results,
    )


@router.put("/settings", response_model=ServerSettingsResponse)
async def update_server_settings(
    updates: ServerSettingsUpdate,
    repo: SettingsRepository = Depends(get_settings_repository),
) -> ServerSettingsResponse:
    """Update server settings."""
    update_dict = {k: v for k, v in updates.model_dump().items() if v is not None}
    settings = await repo.update_server_settings(update_dict)
    return ServerSettingsResponse(
        log_retention_days=settings.log_retention_days,
        log_retention_max_events=settings.log_retention_max_events,
        trace_retention_days=settings.trace_retention_days,
        checkpoint_retention_days=settings.checkpoint_retention_days,
        checkpoint_path=settings.checkpoint_path,
        websocket_idle_timeout_seconds=settings.websocket_idle_timeout_seconds,
        workflow_start_timeout_seconds=settings.workflow_start_timeout_seconds,
        max_concurrent=settings.max_concurrent,
        stream_tool_results=settings.stream_tool_results,
    )


# Profile endpoints
@router.get("/profiles", response_model=list[ProfileResponse])
async def list_profiles(
    repo: ProfileRepository = Depends(get_profile_repository),
) -> list[ProfileResponse]:
    """List all profiles."""
    profiles = await repo.list_profiles()
    active = await repo.get_active_profile()
    active_id = active.name if active else None
    return [_profile_to_response(p, is_active=(p.name == active_id)) for p in profiles]


@router.post("/profiles", response_model=ProfileResponse, status_code=201)
async def create_profile(
    profile_req: ProfileCreate,
    repo: ProfileRepository = Depends(get_profile_repository),
) -> ProfileResponse:
    """Create a new profile."""
    # Convert AgentConfigCreate to AgentConfig
    agents = {
        name: AgentConfig(
            driver=config.driver,
            model=config.model,
            options=config.options,
        )
        for name, config in profile_req.agents.items()
    }

    profile = Profile(
        name=profile_req.id,
        tracker=profile_req.tracker,
        working_dir=profile_req.working_dir,
        plan_output_dir=profile_req.plan_output_dir,
        plan_path_pattern=profile_req.plan_path_pattern,
        auto_approve_reviews=profile_req.auto_approve_reviews,
        agents=agents,
    )

    try:
        created = await repo.create_profile(profile)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Profile already exists") from exc
    # Newly created profiles are not active
    return _profile_to_response(created, is_active=False)


@router.get("/profiles/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: str,
    repo: ProfileRepository = Depends(get_profile_repository),
) -> ProfileResponse:
    """Get a profile by ID."""
    profile = await repo.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    active = await repo.get_active_profile()
    return _profile_to_response(profile, is_active=(active is not None and active.name == profile_id))


@router.put("/profiles/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: str,
    updates: ProfileUpdate,
    repo: ProfileRepository = Depends(get_profile_repository),
) -> ProfileResponse:
    """Update a profile."""
    update_dict: dict[str, Any] = {}

    # Handle simple fields
    for field in ["tracker", "working_dir", "plan_output_dir", "plan_path_pattern", "auto_approve_reviews"]:
        value = getattr(updates, field)
        if value is not None:
            update_dict[field] = value

    # Handle agents field - convert to JSON for database storage
    if updates.agents is not None:
        agents_json = json.dumps({
            name: {
                "driver": config.driver,
                "model": config.model,
                "options": config.options,
            }
            for name, config in updates.agents.items()
        })
        update_dict["agents"] = agents_json

    try:
        updated = await repo.update_profile(profile_id, update_dict)
        active = await repo.get_active_profile()
        return _profile_to_response(updated, is_active=(active is not None and active.name == profile_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: str,
    repo: ProfileRepository = Depends(get_profile_repository),
) -> None:
    """Delete a profile."""
    deleted = await repo.delete_profile(profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Profile not found")


@router.post("/profiles/{profile_id}/activate", response_model=ProfileResponse)
async def activate_profile(
    profile_id: str,
    repo: ProfileRepository = Depends(get_profile_repository),
) -> ProfileResponse:
    """Set a profile as active."""
    try:
        await repo.set_active(profile_id)
        profile = await repo.get_profile(profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        # After activation, this profile is definitely active
        return _profile_to_response(profile, is_active=True)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


def _profile_to_response(profile: Profile, is_active: bool = False) -> ProfileResponse:
    """Convert Profile to API response.

    Args:
        profile: Profile instance from database.
        is_active: Whether this profile is the active one (determined externally).

    Returns:
        ProfileResponse for API output.
    """
    return ProfileResponse(
        id=profile.name,
        tracker=profile.tracker,
        working_dir=profile.working_dir,
        plan_output_dir=profile.plan_output_dir,
        plan_path_pattern=profile.plan_path_pattern,
        auto_approve_reviews=profile.auto_approve_reviews,
        agents={
            name: AgentConfigResponse(
                driver=config.driver,
                model=config.model,
                options=config.options,
            )
            for name, config in profile.agents.items()
        },
        is_active=is_active,
    )
