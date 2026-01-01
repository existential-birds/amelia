# amelia/server/routes/prompts.py
"""API routes for prompt configuration.

Provides endpoints for listing, viewing, and editing agent prompts.
"""
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from amelia.agents.prompts.defaults import PROMPT_DEFAULTS


if TYPE_CHECKING:
    from amelia.server.database.prompt_repository import PromptRepository


router = APIRouter(prefix="/api/prompts", tags=["prompts"])


# Dependency placeholder - will be overridden by app
def get_prompt_repository() -> "PromptRepository":
    """Get prompt repository dependency.

    This dependency is a placeholder that must be overridden by the
    application. It raises NotImplementedError if called directly.

    Returns:
        PromptRepository instance.

    Raises:
        NotImplementedError: Always, as this must be overridden.
    """
    raise NotImplementedError(
        "Prompt repository dependency not configured. "
        "Ensure the app has overridden this dependency."
    )


# Request/Response models


class PromptSummary(BaseModel):
    """Summary of a prompt for list views.

    Attributes:
        id: Unique prompt identifier.
        agent: Agent name (architect, developer, reviewer).
        name: Human-readable prompt name.
        description: What this prompt controls.
        current_version_id: Active version ID, or None for default.
        current_version_number: Active version number, or None.
    """

    id: str
    agent: str
    name: str
    description: str | None
    current_version_id: str | None
    current_version_number: int | None


class PromptListResponse(BaseModel):
    """Response for list prompts endpoint.

    Attributes:
        prompts: List of prompt summaries.
    """

    prompts: list[PromptSummary]


class VersionSummary(BaseModel):
    """Summary of a prompt version.

    Attributes:
        id: Unique version identifier.
        version_number: Sequential version number.
        created_at: ISO timestamp of when version was created.
        change_note: Optional note describing the change.
    """

    id: str
    version_number: int
    created_at: str
    change_note: str | None


class PromptDetailResponse(BaseModel):
    """Detailed prompt with version history.

    Attributes:
        id: Unique prompt identifier.
        agent: Agent name.
        name: Human-readable prompt name.
        description: What this prompt controls.
        current_version_id: Active version ID, or None for default.
        versions: List of version summaries.
    """

    id: str
    agent: str
    name: str
    description: str | None
    current_version_id: str | None
    versions: list[VersionSummary]


class VersionListResponse(BaseModel):
    """Response for list versions endpoint.

    Attributes:
        versions: List of version summaries.
    """

    versions: list[VersionSummary]


class VersionDetailResponse(BaseModel):
    """Full version details including content.

    Attributes:
        id: Unique version identifier.
        prompt_id: Reference to parent prompt.
        version_number: Sequential version number.
        content: The prompt text content.
        created_at: ISO timestamp of creation.
        change_note: Optional note describing the change.
    """

    id: str
    prompt_id: str
    version_number: int
    content: str
    created_at: str
    change_note: str | None


class CreateVersionRequest(BaseModel):
    """Request to create a new version.

    Attributes:
        content: The new prompt content (cannot be empty).
        change_note: Optional note describing the change.
    """

    content: str
    change_note: str | None = None

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        """Validate content is not empty.

        Args:
            v: The content value to validate.

        Returns:
            The validated content.

        Raises:
            ValueError: If content is empty or whitespace-only.
        """
        if not v.strip():
            raise ValueError("Content cannot be empty")
        return v


class DefaultContentResponse(BaseModel):
    """Response for get default content endpoint.

    Attributes:
        prompt_id: The prompt identifier.
        content: The hardcoded default content.
        name: Human-readable prompt name.
        description: What this prompt controls.
    """

    prompt_id: str
    content: str
    name: str
    description: str


class ResetResponse(BaseModel):
    """Response for reset to default endpoint.

    Attributes:
        message: Confirmation message.
    """

    message: str


# Routes


@router.get("/", response_model=PromptListResponse)
async def list_prompts(
    repository: "PromptRepository" = Depends(get_prompt_repository),
) -> PromptListResponse:
    """List all prompts with current version info.

    Args:
        repository: Prompt repository dependency.

    Returns:
        PromptListResponse with all prompts.
    """
    prompts = await repository.list_prompts()

    # Get version numbers for active versions
    summaries = []
    for prompt in prompts:
        version_number = None
        if prompt.current_version_id:
            version = await repository.get_version(prompt.current_version_id)
            if version:
                version_number = version.version_number

        summaries.append(
            PromptSummary(
                id=prompt.id,
                agent=prompt.agent,
                name=prompt.name,
                description=prompt.description,
                current_version_id=prompt.current_version_id,
                current_version_number=version_number,
            )
        )

    return PromptListResponse(prompts=summaries)


@router.get("/{prompt_id}", response_model=PromptDetailResponse)
async def get_prompt(
    prompt_id: str,
    repository: "PromptRepository" = Depends(get_prompt_repository),
) -> PromptDetailResponse:
    """Get prompt with version history.

    Args:
        prompt_id: The unique prompt identifier.
        repository: Prompt repository dependency.

    Returns:
        PromptDetailResponse with prompt details and versions.

    Raises:
        HTTPException: 404 if prompt not found.
    """
    prompt = await repository.get_prompt(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt not found: {prompt_id}")

    versions = await repository.get_versions(prompt_id)
    version_summaries = [
        VersionSummary(
            id=v.id,
            version_number=v.version_number,
            created_at=v.created_at.isoformat(),
            change_note=v.change_note,
        )
        for v in versions
    ]

    return PromptDetailResponse(
        id=prompt.id,
        agent=prompt.agent,
        name=prompt.name,
        description=prompt.description,
        current_version_id=prompt.current_version_id,
        versions=version_summaries,
    )


@router.get("/{prompt_id}/versions", response_model=VersionListResponse)
async def get_versions(
    prompt_id: str,
    repository: "PromptRepository" = Depends(get_prompt_repository),
) -> VersionListResponse:
    """List all versions for a prompt.

    Args:
        prompt_id: The unique prompt identifier.
        repository: Prompt repository dependency.

    Returns:
        VersionListResponse with all versions.

    Raises:
        HTTPException: 404 if prompt not found.
    """
    prompt = await repository.get_prompt(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt not found: {prompt_id}")

    versions = await repository.get_versions(prompt_id)
    return VersionListResponse(
        versions=[
            VersionSummary(
                id=v.id,
                version_number=v.version_number,
                created_at=v.created_at.isoformat(),
                change_note=v.change_note,
            )
            for v in versions
        ]
    )


@router.get("/{prompt_id}/versions/{version_id}", response_model=VersionDetailResponse)
async def get_version(
    prompt_id: str,
    version_id: str,
    repository: "PromptRepository" = Depends(get_prompt_repository),
) -> VersionDetailResponse:
    """Get a specific version with content.

    Args:
        prompt_id: The unique prompt identifier.
        version_id: The unique version identifier.
        repository: Prompt repository dependency.

    Returns:
        VersionDetailResponse with full version details including content.

    Raises:
        HTTPException: 404 if version not found.
    """
    version = await repository.get_version(version_id)
    if not version or version.prompt_id != prompt_id:
        raise HTTPException(status_code=404, detail=f"Version not found: {version_id}")

    return VersionDetailResponse(
        id=version.id,
        prompt_id=version.prompt_id,
        version_number=version.version_number,
        content=version.content,
        created_at=version.created_at.isoformat(),
        change_note=version.change_note,
    )


@router.post(
    "/{prompt_id}/versions",
    status_code=status.HTTP_201_CREATED,
    response_model=VersionDetailResponse,
)
async def create_version(
    prompt_id: str,
    request: CreateVersionRequest,
    repository: "PromptRepository" = Depends(get_prompt_repository),
) -> VersionDetailResponse:
    """Create a new version (becomes active immediately).

    Args:
        prompt_id: The unique prompt identifier.
        request: Request with content and optional change note.
        repository: Prompt repository dependency.

    Returns:
        VersionDetailResponse with new version details.

    Raises:
        HTTPException: 404 if prompt not found, 400 if validation fails.
    """
    prompt = await repository.get_prompt(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt not found: {prompt_id}")

    try:
        version = await repository.create_version(
            prompt_id=prompt_id,
            content=request.content,
            change_note=request.change_note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return VersionDetailResponse(
        id=version.id,
        prompt_id=version.prompt_id,
        version_number=version.version_number,
        content=version.content,
        created_at=version.created_at.isoformat(),
        change_note=version.change_note,
    )


@router.post("/{prompt_id}/reset", response_model=ResetResponse)
async def reset_to_default(
    prompt_id: str,
    repository: "PromptRepository" = Depends(get_prompt_repository),
) -> ResetResponse:
    """Reset prompt to use hardcoded default.

    Args:
        prompt_id: The unique prompt identifier.
        repository: Prompt repository dependency.

    Returns:
        ResetResponse with confirmation message.

    Raises:
        HTTPException: 404 if prompt not found.
    """
    prompt = await repository.get_prompt(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt not found: {prompt_id}")

    await repository.reset_to_default(prompt_id)
    return ResetResponse(message=f"Prompt {prompt_id} reset to default")


@router.get("/{prompt_id}/default", response_model=DefaultContentResponse)
async def get_default_content(prompt_id: str) -> DefaultContentResponse:
    """Get the hardcoded default content for a prompt.

    Args:
        prompt_id: The unique prompt identifier.

    Returns:
        DefaultContentResponse with default content.

    Raises:
        HTTPException: 404 if prompt ID not in PROMPT_DEFAULTS.
    """
    default = PROMPT_DEFAULTS.get(prompt_id)
    if not default:
        raise HTTPException(status_code=404, detail=f"Unknown prompt: {prompt_id}")

    return DefaultContentResponse(
        prompt_id=prompt_id,
        content=default.content,
        name=default.name,
        description=default.description,
    )
