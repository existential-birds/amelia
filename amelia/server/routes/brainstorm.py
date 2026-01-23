"""API routes for brainstorming sessions.

Provides endpoints for session lifecycle management and chat functionality.
"""

import os
from typing import TYPE_CHECKING, Annotated
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from loguru import logger
from pydantic import BaseModel

from amelia.server.database import ProfileRepository
from amelia.server.dependencies import get_orchestrator, get_profile_repository
from amelia.server.models.brainstorm import (
    Artifact,
    BrainstormingSession,
    Message,
    SessionStatus,
)
from amelia.server.orchestrator.service import OrchestratorService
from amelia.server.routes.config import ProfileInfo
from amelia.server.services.brainstorm import BrainstormService


if TYPE_CHECKING:
    from amelia.drivers.base import DriverInterface


router = APIRouter(tags=["brainstorm"])


# Dependency placeholder - will be properly wired in main.py
def get_brainstorm_service() -> BrainstormService:
    """Get BrainstormService dependency.

    Returns:
        BrainstormService instance.

    Raises:
        RuntimeError: If service not initialized.
    """
    raise RuntimeError("BrainstormService not initialized")


def get_driver() -> "DriverInterface":
    """Get driver dependency.

    Returns:
        DriverInterface instance.

    Raises:
        RuntimeError: If driver not initialized.
    """
    raise RuntimeError("Driver not initialized")


def get_cwd() -> str:
    """Get current working directory.

    Returns:
        Current working directory path.
    """
    return os.getcwd()


async def get_profile_info(
    profile_id: str,
    profile_repo: ProfileRepository | None = None,
) -> "ProfileInfo | None":
    """Load profile info from database for display.

    Uses the 'brainstormer' agent config to get driver/model info.

    Args:
        profile_id: Profile ID to look up.
        profile_repo: Optional profile repository. If not provided, creates one.

    Returns:
        ProfileInfo if found and has brainstormer config, None otherwise.
    """
    if profile_repo is None:
        profile_repo = get_profile_repository()

    try:
        profile = await profile_repo.get_profile(profile_id)
        if profile is None:
            return None
        agent_config = profile.get_agent_config("brainstormer")
        return ProfileInfo(
            name=profile.name,
            driver=agent_config.driver,
            model=agent_config.model,
        )
    except Exception as e:
        logger.debug("Failed to load profile info", profile_id=profile_id, error=str(e))
        return None


# Request/Response Models
class CreateSessionRequest(BaseModel):
    """Request to create a new brainstorming session."""

    profile_id: str
    topic: str | None = None


class SessionWithHistoryResponse(BaseModel):
    """Response containing session with messages and artifacts."""

    session: BrainstormingSession
    messages: list[Message]
    artifacts: list[Artifact]
    profile: ProfileInfo | None = None


class CreateSessionResponse(BaseModel):
    """Response from creating a new session."""

    session: BrainstormingSession
    profile: ProfileInfo | None = None


class SendMessageRequest(BaseModel):
    """Request to send a message in a session."""

    content: str


class SendMessageResponse(BaseModel):
    """Response after sending a message."""

    message_id: str


class HandoffRequest(BaseModel):
    """Request to hand off session to implementation."""

    artifact_path: str
    issue_title: str | None = None
    issue_description: str | None = None


class HandoffResponse(BaseModel):
    """Response from handoff request."""

    workflow_id: str
    status: str


# Session Lifecycle Endpoints
@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateSessionResponse,
)
async def create_session(
    request: CreateSessionRequest,
    service: BrainstormService = Depends(get_brainstorm_service),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> CreateSessionResponse:
    """Create a new brainstorming session.

    Args:
        request: Session creation request.
        service: Brainstorm service dependency.
        profile_repo: Profile repository dependency.

    Returns:
        Created session with profile info.
    """
    session = await service.create_session(
        profile_id=request.profile_id,
        topic=request.topic,
    )
    profile_info = await get_profile_info(request.profile_id, profile_repo)
    return CreateSessionResponse(session=session, profile=profile_info)


class PrimeSessionResponse(BaseModel):
    """Response for session priming."""

    message_id: str


@router.post(
    "/sessions/{session_id}/prime",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PrimeSessionResponse,
)
async def prime_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    service: BrainstormService = Depends(get_brainstorm_service),
    driver: "DriverInterface" = Depends(get_driver),
    cwd: str = Depends(get_cwd),
) -> PrimeSessionResponse:
    """Prime a brainstorming session with skill instructions.

    Sends the brainstorming skill as the first message and gets the model's
    greeting response. Should be called immediately after creating a session.

    Triggers async processing - returns immediately with message_id.
    Updates streamed via WebSocket.

    Args:
        session_id: Session to prime.
        background_tasks: FastAPI background tasks for async processing.
        service: Brainstorm service dependency.
        driver: LLM driver dependency.
        cwd: Current working directory.

    Returns:
        Response with message_id for tracking.

    Raises:
        HTTPException: 404 if session not found.
    """
    # Validate session exists before returning 202
    session = await service.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )

    # Generate message ID upfront for tracking
    message_id = str(uuid4())

    async def _process_priming() -> None:
        """Background task to prime the session."""
        try:
            async for _ in service.prime_session(
                session_id=session_id,
                driver=driver,
                cwd=cwd,
                assistant_message_id=message_id,
            ):
                pass
        except Exception as e:
            logger.error(
                "Failed to prime session",
                session_id=session_id,
                error=str(e),
            )

    background_tasks.add_task(_process_priming)

    return PrimeSessionResponse(message_id=message_id)


@router.get("/sessions", response_model=list[BrainstormingSession])
async def list_sessions(
    profile_id: Annotated[str | None, Query()] = None,
    session_status: Annotated[SessionStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    service: BrainstormService = Depends(get_brainstorm_service),
) -> list[BrainstormingSession]:
    """List brainstorming sessions.

    Args:
        profile_id: Filter by profile.
        session_status: Filter by status.
        limit: Maximum sessions to return.
        service: Brainstorm service dependency.

    Returns:
        List of sessions.
    """
    return await service.list_sessions(
        profile_id=profile_id, status=session_status, limit=limit
    )


@router.get("/sessions/{session_id}", response_model=SessionWithHistoryResponse)
async def get_session(
    session_id: str,
    service: BrainstormService = Depends(get_brainstorm_service),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> SessionWithHistoryResponse:
    """Get session with messages and artifacts.

    Args:
        session_id: Session to retrieve.
        service: Brainstorm service dependency.
        profile_repo: Profile repository dependency.

    Returns:
        Session with history including profile info.

    Raises:
        HTTPException: 404 if session not found.
    """
    result = await service.get_session_with_history(session_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )

    # Load profile info for display
    session = result["session"]
    profile_info = await get_profile_info(session.profile_id, profile_repo)

    return SessionWithHistoryResponse(
        session=session,
        messages=result["messages"],
        artifacts=result["artifacts"],
        profile=profile_info,
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    service: BrainstormService = Depends(get_brainstorm_service),
) -> None:
    """Delete a brainstorming session.

    Args:
        session_id: Session to delete.
        service: Brainstorm service dependency.
    """
    await service.delete_session(session_id)


# Chat Endpoints
@router.post(
    "/sessions/{session_id}/message",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SendMessageResponse,
)
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    background_tasks: BackgroundTasks,
    service: BrainstormService = Depends(get_brainstorm_service),
    driver: "DriverInterface" = Depends(get_driver),
    cwd: str = Depends(get_cwd),
) -> SendMessageResponse:
    """Send a message in a brainstorming session.

    Triggers async processing - returns immediately with message_id.
    Updates streamed via WebSocket.

    Args:
        session_id: Session to send message to.
        request: Message content.
        background_tasks: FastAPI background tasks for async processing.
        service: Brainstorm service dependency.
        driver: LLM driver dependency.
        cwd: Current working directory.

    Returns:
        Response with message_id for tracking.

    Raises:
        HTTPException: 404 if session not found.
    """
    # Validate session exists before returning 202
    session = await service.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )

    # Generate message ID upfront for tracking
    message_id = str(uuid4())

    async def _process_message() -> None:
        """Background task to process the message."""
        async for _ in service.send_message(
            session_id=session_id,
            content=request.content,
            driver=driver,
            cwd=cwd,
            assistant_message_id=message_id,
        ):
            pass

    background_tasks.add_task(_process_message)

    return SendMessageResponse(message_id=message_id)


# Handoff Endpoint
@router.post(
    "/sessions/{session_id}/handoff",
    response_model=HandoffResponse,
)
async def handoff_to_implementation(
    session_id: str,
    request: HandoffRequest,
    service: BrainstormService = Depends(get_brainstorm_service),
    orchestrator: OrchestratorService = Depends(get_orchestrator),
    cwd: str = Depends(get_cwd),
) -> HandoffResponse:
    """Hand off brainstorming session to implementation pipeline.

    Creates an implementation workflow from the design artifact.

    Args:
        session_id: Session to hand off.
        request: Handoff request with artifact path.
        service: Brainstorm service dependency.

    Returns:
        Handoff response with workflow ID.

    Raises:
        HTTPException: 404 if session or artifact not found.
    """
    try:
        result = await service.handoff_to_implementation(
            session_id=session_id,
            artifact_path=request.artifact_path,
            issue_title=request.issue_title,
            issue_description=request.issue_description,
            orchestrator=orchestrator,
            worktree_path=cwd,
        )
        return HandoffResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
