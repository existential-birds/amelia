# amelia/server/routes/settings.py
"""API routes for server settings and profiles."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from amelia.server.database import (
    ProfileRecord,
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


class ProfileResponse(BaseModel):
    """Profile API response."""

    id: str
    driver: str
    model: str
    validator_model: str
    tracker: str
    working_dir: str
    plan_output_dir: str
    plan_path_pattern: str
    max_review_iterations: int
    max_task_review_iterations: int
    auto_approve_reviews: bool
    is_active: bool


VALID_DRIVERS = {"cli:claude", "api:openrouter", "cli", "api"}
VALID_TRACKERS = {"jira", "github", "none", "noop"}


class ProfileCreate(BaseModel):
    """Profile creation request."""

    id: str
    driver: str
    model: str
    validator_model: str
    tracker: str = "noop"
    working_dir: str
    plan_output_dir: str = "docs/plans"
    plan_path_pattern: str = "docs/plans/{date}-{issue_key}.md"
    max_review_iterations: int = 3
    max_task_review_iterations: int = 5
    auto_approve_reviews: bool = False

    @field_validator("driver")
    @classmethod
    def validate_driver(cls, v: str) -> str:
        if v not in VALID_DRIVERS:
            raise ValueError(f"Invalid driver '{v}'. Valid options: {sorted(VALID_DRIVERS)}")
        return v

    @field_validator("tracker")
    @classmethod
    def validate_tracker(cls, v: str) -> str:
        if v not in VALID_TRACKERS:
            raise ValueError(f"Invalid tracker '{v}'. Valid options: {sorted(VALID_TRACKERS)}")
        return v


class ProfileUpdate(BaseModel):
    """Profile update request."""

    driver: str | None = None
    model: str | None = None
    validator_model: str | None = None
    tracker: str | None = None
    working_dir: str | None = None
    plan_output_dir: str | None = None
    plan_path_pattern: str | None = None
    max_review_iterations: int | None = None
    max_task_review_iterations: int | None = None
    auto_approve_reviews: bool | None = None

    @field_validator("driver")
    @classmethod
    def validate_driver(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_DRIVERS:
            raise ValueError(f"Invalid driver '{v}'. Valid options: {sorted(VALID_DRIVERS)}")
        return v

    @field_validator("tracker")
    @classmethod
    def validate_tracker(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_TRACKERS:
            raise ValueError(f"Invalid tracker '{v}'. Valid options: {sorted(VALID_TRACKERS)}")
        return v


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
    return [_profile_to_response(p) for p in profiles]


@router.post("/profiles", response_model=ProfileResponse, status_code=201)
async def create_profile(
    profile: ProfileCreate,
    repo: ProfileRepository = Depends(get_profile_repository),
) -> ProfileResponse:
    """Create a new profile."""
    record = ProfileRecord(
        id=profile.id,
        driver=profile.driver,
        model=profile.model,
        validator_model=profile.validator_model,
        tracker=profile.tracker,
        working_dir=profile.working_dir,
        plan_output_dir=profile.plan_output_dir,
        plan_path_pattern=profile.plan_path_pattern,
        max_review_iterations=profile.max_review_iterations,
        max_task_review_iterations=profile.max_task_review_iterations,
        auto_approve_reviews=profile.auto_approve_reviews,
    )
    try:
        created = await repo.create_profile(record)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Profile already exists") from exc
    return _profile_to_response(created)


@router.get("/profiles/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: str,
    repo: ProfileRepository = Depends(get_profile_repository),
) -> ProfileResponse:
    """Get a profile by ID."""
    profile = await repo.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _profile_to_response(profile)


@router.put("/profiles/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: str,
    updates: ProfileUpdate,
    repo: ProfileRepository = Depends(get_profile_repository),
) -> ProfileResponse:
    """Update a profile."""
    update_dict = {k: v for k, v in updates.model_dump().items() if v is not None}
    try:
        updated = await repo.update_profile(profile_id, update_dict)
        return _profile_to_response(updated)
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
        return _profile_to_response(profile)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


def _profile_to_response(profile: ProfileRecord) -> ProfileResponse:
    """Convert ProfileRecord to API response."""
    return ProfileResponse(
        id=profile.id,
        driver=profile.driver,
        model=profile.model,
        validator_model=profile.validator_model,
        tracker=profile.tracker,
        working_dir=profile.working_dir,
        plan_output_dir=profile.plan_output_dir,
        plan_path_pattern=profile.plan_path_pattern,
        max_review_iterations=profile.max_review_iterations,
        max_task_review_iterations=profile.max_task_review_iterations,
        auto_approve_reviews=profile.auto_approve_reviews,
        is_active=profile.is_active,
    )
