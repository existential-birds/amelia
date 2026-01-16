"""File access endpoints for design document import."""
import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from amelia.server.config import ServerConfig
from amelia.server.dependencies import get_config


router = APIRouter(prefix="/files", tags=["files"])


class FileReadRequest(BaseModel):
    """Request model for reading a file."""

    path: str = Field(description="Absolute path to the file to read")


class FileReadResponse(BaseModel):
    """Response model for file content."""

    content: str = Field(description="File content as text")
    filename: str = Field(description="Filename without path")


@router.post("/read", response_model=FileReadResponse)
async def read_file(
    request: FileReadRequest,
    config: ServerConfig = Depends(get_config),
) -> FileReadResponse:
    """Read file content for design document import.

    Args:
        request: File read request with path.
        config: Server configuration.

    Returns:
        File content and filename.

    Raises:
        HTTPException: 400 if path is invalid or outside working_dir.
        HTTPException: 404 if file doesn't exist.
    """
    file_path = Path(request.path)

    # Validate absolute path
    if not file_path.is_absolute():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Path must be absolute", "code": "INVALID_PATH"},
        )

    # Resolve to handle symlinks and ..
    try:
        resolved_path = file_path.resolve()
    except (OSError, RuntimeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": f"Invalid path: {e}", "code": "INVALID_PATH"},
        ) from e

    # Check working_dir restriction
    working_dir_resolved = config.working_dir.resolve()
    try:
        resolved_path.relative_to(working_dir_resolved)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Path not accessible (outside working directory)",
                "code": "PATH_NOT_ACCESSIBLE",
            },
        ) from e

    # Check file exists
    if not resolved_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "File not found", "code": "FILE_NOT_FOUND"},
        )

    if not resolved_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Path is not a file", "code": "NOT_A_FILE"},
        )

    # Read content (use thread pool to avoid blocking event loop)
    try:
        content = await asyncio.to_thread(resolved_path.read_text, encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": f"Failed to read file: {e}", "code": "READ_ERROR"},
        ) from e

    return FileReadResponse(
        content=content,
        filename=resolved_path.name,
    )
