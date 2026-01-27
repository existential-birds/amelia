"""Oracle consultation API routes.

Provides the REST endpoint for standalone Oracle consultations.
Events stream via WebSocket in real-time using the same EventBus
pattern as brainstorm sessions.
"""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from loguru import logger
from pydantic import BaseModel

from amelia.agents.oracle import Oracle, OracleConsultResult
from amelia.core.types import AgentConfig, OracleConsultation, Profile
from amelia.server.events.bus import EventBus


router = APIRouter(tags=["oracle"])


# --- Request / Response models ---


class OracleConsultRequest(BaseModel):
    """Request body for Oracle consultation.

    Attributes:
        problem: The problem statement to analyze.
        working_dir: Root directory for codebase access.
        files: Optional glob patterns for files to include.
        model: Optional model override.
        profile_id: Optional profile ID (uses active profile if omitted).
    """

    problem: str
    working_dir: str
    files: list[str] | None = None
    model: str | None = None
    profile_id: str | None = None


class OracleConsultResponse(BaseModel):
    """Response body for Oracle consultation.

    Attributes:
        advice: The Oracle's advice.
        consultation: Full consultation record.
    """

    advice: str
    consultation: OracleConsultation


# --- Dependency stubs (overridden in main.py) ---


async def _get_profile(profile_id: str | None = None) -> Profile:
    """Get profile -- overridden in main.py."""
    raise NotImplementedError("Must be overridden via dependency_overrides")


def _get_event_bus() -> EventBus:
    """Get EventBus -- overridden in main.py."""
    raise NotImplementedError("Must be overridden via dependency_overrides")


def _validate_working_dir(requested: str, profile_root: str) -> None:
    """Validate that requested working_dir is within profile root.

    Args:
        requested: The requested working directory.
        profile_root: The profile's configured working directory.

    Raises:
        HTTPException: If requested path is outside profile root.
    """
    try:
        Path(requested).resolve().relative_to(Path(profile_root).resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"working_dir must be within profile root: {profile_root}",
        ) from exc


# --- Route ---


@router.post(
    "/consult",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=OracleConsultResponse,
)
async def consult(
    request: OracleConsultRequest,
    background_tasks: BackgroundTasks,
) -> OracleConsultResponse:
    """Run an Oracle consultation.

    Accepts a problem statement and optional file patterns. The Oracle
    agent gathers codebase context and uses agentic LLM execution to
    provide expert advice.

    Events stream via WebSocket in real-time.

    Args:
        request: Consultation request with problem and context.
        background_tasks: FastAPI background tasks.

    Returns:
        OracleConsultResponse with advice and consultation record.

    Raises:
        HTTPException: 400 if working_dir invalid or oracle not configured.
    """
    # Resolve profile
    profile = await _get_profile(request.profile_id)

    # Validate working_dir
    _validate_working_dir(request.working_dir, profile.working_dir)

    # Get oracle agent config
    try:
        agent_config = profile.get_agent_config("oracle")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Override model if provided
    if request.model:
        agent_config = AgentConfig(
            driver=agent_config.driver,
            model=request.model,
            options=agent_config.options,
        )

    # Get event bus
    event_bus = _get_event_bus()

    # Run consultation
    oracle = Oracle(config=agent_config, event_bus=event_bus)
    result: OracleConsultResult = await oracle.consult(
        problem=request.problem,
        working_dir=request.working_dir,
        files=request.files,
    )

    logger.info(
        "Oracle consultation API complete",
        session_id=result.consultation.session_id,
        outcome=result.consultation.outcome,
    )

    return OracleConsultResponse(
        advice=result.advice,
        consultation=result.consultation,
    )
