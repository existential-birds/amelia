# amelia/server/routes/settings.py
"""API routes for server settings and profiles."""
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
from asyncpg import UniqueViolationError
from loguru import logger
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from amelia.core.types import (
    REQUIRED_AGENTS,
    AgentConfig,
    DriverType,
    PRAutoFixConfig,
    Profile,
    SandboxConfig,
    TrackerType,
)
from amelia.server.database import (
    ModelCacheRepository,
    ProfileRepository,
    SettingsRepository,
)
from amelia.server.dependencies import (
    get_model_cache_repository,
    get_profile_repository,
    get_settings_repository,
)
from amelia.server.models.model_cache import (
    ModelCacheEntry,
    ModelLookupResponse,
    normalize_openrouter_model,
    to_model_lookup_response,
)


router = APIRouter(prefix="/api", tags=["settings"])
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models?supported_parameters=tools"


def _validate_repo_root_absolute(v: str | None) -> str | None:
    """Validate that repo_root is an absolute path when provided.

    Args:
        v: Repository root path or None.

    Returns:
        The validated absolute path or None.
    """
    if v is not None and not Path(v).is_absolute():
        raise ValueError("repo_root must be an absolute path")
    return v


def _validate_required_agents(agents: Mapping[str, object] | None) -> None:
    """Validate that all required agents are present when agents are provided.

    Args:
        agents: Agent configuration dict or None.

    Raises:
        ValueError: If required agents are missing.
    """
    if agents is not None:
        missing = REQUIRED_AGENTS - agents.keys()
        if missing:
            raise ValueError(f"Missing required agents: {', '.join(sorted(missing))}")


# Response models
class ServerSettingsResponse(BaseModel):
    """Server settings API response."""

    log_retention_days: int
    checkpoint_retention_days: int
    websocket_idle_timeout_seconds: float
    workflow_start_timeout_seconds: float
    max_concurrent: int
    pr_polling_enabled: bool


class ServerSettingsUpdate(BaseModel):
    """Server settings update request."""

    log_retention_days: int | None = None
    checkpoint_retention_days: int | None = None
    websocket_idle_timeout_seconds: float | None = None
    workflow_start_timeout_seconds: float | None = None
    max_concurrent: int | None = None
    pr_polling_enabled: bool | None = None


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
    repo_root: str
    plan_output_dir: str
    plan_path_pattern: str
    agents: dict[str, AgentConfigResponse]
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    pr_autofix: PRAutoFixConfig | None = None
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
    repo_root: str
    plan_output_dir: str = "docs/plans"
    plan_path_pattern: str = "docs/plans/{date}-{issue_key}.md"
    agents: dict[str, AgentConfigCreate]
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    pr_autofix: PRAutoFixConfig | None = None

    @field_validator("repo_root", mode="after")
    @classmethod
    def validate_repo_root_absolute(cls, v: str) -> str:
        """Validate that repo_root is an absolute path."""
        return _validate_repo_root_absolute(v)  # type: ignore[return-value]

    @model_validator(mode="after")
    def validate_required_agents(self) -> "ProfileCreate":
        """Validate that all required agents are present."""
        _validate_required_agents(self.agents)
        return self


class ProfileUpdate(BaseModel):
    """Profile update request.

    All fields are optional. To update agents, provide the full agents dict.
    """

    tracker: TrackerType | None = None
    repo_root: str | None = None
    plan_output_dir: str | None = None
    plan_path_pattern: str | None = None
    agents: dict[str, AgentConfigCreate] | None = None
    sandbox: SandboxConfig | None = None
    pr_autofix: PRAutoFixConfig | None = None

    @field_validator("repo_root", mode="after")
    @classmethod
    def validate_repo_root_absolute(cls, v: str | None) -> str | None:
        """Validate that repo_root is an absolute path when provided."""
        return _validate_repo_root_absolute(v)

    @model_validator(mode="after")
    def validate_required_agents(self) -> "ProfileUpdate":
        """Validate that all required agents are present when agents are provided."""
        _validate_required_agents(self.agents)
        return self


async def fetch_openrouter_model_entry(model_id: str) -> ModelCacheEntry | None:
    """Fetch and normalize a single OpenRouter model by scanning the model catalog."""
    headers: dict[str, str] = {}
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(OPENROUTER_MODELS_URL, headers=headers)
            response.raise_for_status()
            data = response.json()
    except httpx.ConnectError as e:
        logger.warning("OpenRouter connect failed", error=str(e))
        return None
    except httpx.TimeoutException as e:
        logger.warning("OpenRouter request timed out", error=str(e))
        return None
    except httpx.HTTPStatusError as e:
        logger.warning("OpenRouter returned error", status=e.response.status_code)
        return None

    for model_data in data.get("data", []):
        if not isinstance(model_data, dict) or model_data.get("id") != model_id:
            continue
        return normalize_openrouter_model(model_data)

    return None


# Server settings endpoints
@router.get("/settings", response_model=ServerSettingsResponse)
async def get_server_settings(
    repo: SettingsRepository = Depends(get_settings_repository),
) -> ServerSettingsResponse:
    """Get current server settings."""
    settings = await repo.get_server_settings()
    return ServerSettingsResponse(
        log_retention_days=settings.log_retention_days,
        checkpoint_retention_days=settings.checkpoint_retention_days,
        websocket_idle_timeout_seconds=settings.websocket_idle_timeout_seconds,
        workflow_start_timeout_seconds=settings.workflow_start_timeout_seconds,
        max_concurrent=settings.max_concurrent,
        pr_polling_enabled=settings.pr_polling_enabled,
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
        checkpoint_retention_days=settings.checkpoint_retention_days,
        websocket_idle_timeout_seconds=settings.websocket_idle_timeout_seconds,
        workflow_start_timeout_seconds=settings.workflow_start_timeout_seconds,
        max_concurrent=settings.max_concurrent,
        pr_polling_enabled=settings.pr_polling_enabled,
    )


@router.get("/models/{model_id:path}", response_model=ModelLookupResponse)
async def get_model(
    model_id: str,
    repo: ModelCacheRepository = Depends(get_model_cache_repository),
) -> ModelLookupResponse:
    """Resolve a single OpenRouter model id using cache-first lookup."""
    cached = await repo.get_model(model_id)
    if cached is not None and not await repo.is_stale(model_id):
        return to_model_lookup_response(cached)

    fetched = await fetch_openrouter_model_entry(model_id)
    if fetched is None:
        raise HTTPException(status_code=404, detail="Model not found")

    await repo.upsert_model(fetched)
    return to_model_lookup_response(fetched)


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
        repo_root=profile_req.repo_root,
        plan_output_dir=profile_req.plan_output_dir,
        plan_path_pattern=profile_req.plan_path_pattern,
        agents=agents,
        sandbox=profile_req.sandbox,
        pr_autofix=profile_req.pr_autofix,
    )

    try:
        created = await repo.create_profile(profile)
    except UniqueViolationError as exc:
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
    for field in ["tracker", "repo_root", "plan_output_dir", "plan_path_pattern"]:
        value = getattr(updates, field)
        if value is not None:
            update_dict[field] = value

    # Handle agents field - pass dict directly (JSONB codec handles encoding)
    if updates.agents is not None:
        update_dict["agents"] = {
            name: {
                "driver": config.driver,
                "model": config.model,
                "options": config.options,
            }
            for name, config in updates.agents.items()
        }

    # Handle sandbox field - use model_fields_set to distinguish omission from explicit null
    if "sandbox" in updates.model_fields_set:
        update_dict["sandbox"] = (
            updates.sandbox.model_dump() if updates.sandbox is not None else None
        )

    # Handle pr_autofix field - use model_fields_set to distinguish omission from explicit null
    if "pr_autofix" in updates.model_fields_set:
        update_dict["pr_autofix"] = (
            updates.pr_autofix.model_dump() if updates.pr_autofix is not None else None
        )

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
        repo_root=profile.repo_root,
        plan_output_dir=profile.plan_output_dir,
        plan_path_pattern=profile.plan_path_pattern,
        agents={
            name: AgentConfigResponse(
                driver=config.driver,
                model=config.model,
                options=config.options,
            )
            for name, config in profile.agents.items()
        },
        sandbox=profile.sandbox,
        pr_autofix=profile.pr_autofix,
        is_active=is_active,
    )
