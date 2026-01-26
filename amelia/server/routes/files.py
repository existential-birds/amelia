"""File access endpoints for design document import."""
import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field

from amelia.server.database import ProfileRepository
from amelia.server.dependencies import get_profile_repository
from amelia.server.exceptions import FileOperationError


router = APIRouter(prefix="/files", tags=["files"])


def _validate_and_resolve_path(user_path: str, working_dir: Path) -> Path:
    """Validate user-provided path and return safe resolved path.

    This function performs all security validations on user input before
    returning a path that is safe to use for file operations.

    Args:
        user_path: User-provided file path string.
        working_dir: Allowed working directory.

    Returns:
        Resolved Path object that has been validated to be:
        - An absolute path
        - Within the working directory (after symlink resolution)
        - An existing file

    Raises:
        FileOperationError: If path is invalid, outside working_dir, or file doesn't exist.
    """
    path = Path(user_path)

    # Validate absolute path
    if not path.is_absolute():
        raise FileOperationError("Path must be absolute", "INVALID_PATH")

    # Resolve to handle symlinks and ..
    try:
        resolved_path = path.resolve()
    except (OSError, RuntimeError) as e:
        raise FileOperationError(f"Invalid path: {e}", "INVALID_PATH") from e

    # Check working_dir restriction using commonpath - this is the critical
    # security check that ensures the resolved path is within the allowed directory.
    # Using os.path.commonpath as it's recognized by static analysis tools.
    working_dir_resolved = working_dir.resolve()
    resolved_str = str(resolved_path)
    working_dir_str = str(working_dir_resolved)

    try:
        common = os.path.commonpath([resolved_str, working_dir_str])
    except ValueError as e:
        # Different drives on Windows
        raise FileOperationError(
            "Path not accessible (outside working directory)", "PATH_NOT_ACCESSIBLE"
        ) from e

    if common != working_dir_str:
        raise FileOperationError(
            "Path not accessible (outside working directory)", "PATH_NOT_ACCESSIBLE"
        )

    # Check file exists
    if not resolved_path.exists():
        raise FileOperationError("File not found", "FILE_NOT_FOUND", status_code=404)

    if not resolved_path.is_file():
        raise FileOperationError("Path is not a file", "NOT_A_FILE")

    return resolved_path


class FileReadRequest(BaseModel):
    """Request model for reading a file."""

    path: str = Field(description="Absolute path to the file to read")


class FileReadResponse(BaseModel):
    """Response model for file content."""

    content: str = Field(description="File content as text")
    filename: str = Field(description="Filename without path")


async def _get_working_dir(profile_repo: ProfileRepository) -> Path:
    """Get working directory from active profile.

    Args:
        profile_repo: Profile repository instance.

    Returns:
        Working directory path.

    Raises:
        FileOperationError: If no active profile is set.
    """
    active_profile = await profile_repo.get_active_profile()
    if active_profile is None:
        raise FileOperationError("No active profile set", "NO_ACTIVE_PROFILE")
    return Path(active_profile.working_dir)


@router.post("/read", response_model=FileReadResponse)
async def read_file(
    request: FileReadRequest,
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> FileReadResponse:
    """Read file content for design document import.

    Args:
        request: File read request with path.
        profile_repo: Profile repository for getting active profile.

    Returns:
        File content and filename.

    Raises:
        FileOperationError: If path is invalid, outside working_dir, or file doesn't exist.
    """
    # Get working_dir from active profile
    working_dir = await _get_working_dir(profile_repo)

    # Validate and resolve path - returns only after all security checks pass
    resolved_path = _validate_and_resolve_path(request.path, working_dir)

    # Read content (use thread pool to avoid blocking event loop)
    try:
        content = await asyncio.to_thread(resolved_path.read_text, encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise FileOperationError(f"Failed to read file: {e}", "READ_ERROR") from e

    return FileReadResponse(
        content=content,
        filename=resolved_path.name,
    )


@router.get("/{file_path:path}")
async def get_file(
    file_path: str,
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> Response:
    """Get file content by path.

    Args:
        file_path: Absolute path to the file.
        profile_repo: Profile repository for getting active profile.

    Returns:
        File content as plain text response.

    Raises:
        FileOperationError: If path is invalid, outside working_dir, or file doesn't exist.
    """
    # Get working_dir from active profile
    working_dir = await _get_working_dir(profile_repo)

    # Validate and resolve path - returns only after all security checks pass
    resolved_path = _validate_and_resolve_path(file_path, working_dir)

    # Read content
    try:
        content = await asyncio.to_thread(resolved_path.read_text, encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise FileOperationError(f"Failed to read file: {e}", "READ_ERROR") from e

    # Determine content type based on extension
    suffix = resolved_path.suffix.lower()
    content_type = {
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".json": "application/json",
        ".yaml": "text/yaml",
        ".yml": "text/yaml",
    }.get(suffix, "text/plain")

    return Response(content=content, media_type=content_type)
