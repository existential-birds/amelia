"""Health check endpoints for liveness and readiness probes."""
from datetime import UTC, datetime
from typing import Literal

import psutil
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from amelia import __version__
from amelia.server.database import WorkflowRepository
from amelia.server.dependencies import get_repository
from amelia.server.routes.websocket import connection_manager


router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    """Response model for liveness probe."""

    status: Literal["alive"] = "alive"


class ReadinessResponse(BaseModel):
    """Response model for readiness probe."""

    status: Literal["ready", "not_ready"]


class DatabaseStatus(BaseModel):
    """Database health status."""

    status: Literal["healthy", "degraded", "unhealthy"]
    backend: str = Field(description="Database backend type")
    error: str | None = Field(default=None, description="Error message if degraded")


class HealthResponse(BaseModel):
    """Response model for detailed health check."""

    status: Literal["healthy", "degraded"]
    version: str
    uptime_seconds: float
    active_workflows: int
    websocket_connections: int
    memory_mb: float
    cpu_percent: float
    database: DatabaseStatus


async def get_database_status(repository: WorkflowRepository) -> DatabaseStatus:
    """Check database health by executing a test query.

    Args:
        repository: Workflow repository with database connection.

    Returns:
        DatabaseStatus with actual health check result.
    """
    try:
        is_healthy = await repository.db.is_healthy()
        if is_healthy:
            return DatabaseStatus(status="healthy", backend="postgresql")
        return DatabaseStatus(
            status="unhealthy",
            backend="postgresql",
            error="Health check query failed",
        )
    except Exception as e:
        return DatabaseStatus(
            status="unhealthy",
            backend="postgresql",
            error=str(e),
        )


@router.get("/live", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    """Minimal liveness check - is the server responding?

    Returns:
        Simple alive status.
    """
    return LivenessResponse()


@router.get("/ready", response_model=ReadinessResponse)
async def readiness() -> ReadinessResponse:
    """Readiness check - is the server ready to accept requests?

    Returns:
        Ready status or 503 if shutting down.
    """
    # TODO: Check lifecycle.is_shutting_down when implemented
    return ReadinessResponse(status="ready")


@router.get("", response_model=HealthResponse)
async def health(
    request: Request,
    repository: WorkflowRepository = Depends(get_repository),
) -> HealthResponse:
    """Detailed health check with server metrics.

    Returns:
        Comprehensive health status including:
        - Server status (healthy/degraded)
        - Version info
        - Uptime
        - Active workflow count
        - WebSocket connection count
        - Memory usage
        - Database status
    """
    process = psutil.Process()
    start_time: datetime = request.app.state.start_time
    uptime = (datetime.now(UTC) - start_time).total_seconds()

    active_workflows = await repository.count_active()
    websocket_connections = connection_manager.active_connections

    db_status = await get_database_status(repository)

    overall_status: Literal["healthy", "degraded"] = (
        "healthy" if db_status.status == "healthy" else "degraded"
    )

    # cpu_percent(interval=None) is non-blocking - returns cached value from previous call
    cpu_percent = process.cpu_percent(interval=None)

    return HealthResponse(
        status=overall_status,
        version=__version__,
        uptime_seconds=uptime,
        active_workflows=active_workflows,
        websocket_connections=websocket_connections,
        memory_mb=round(process.memory_info().rss / 1024 / 1024, 2),
        cpu_percent=cpu_percent,
        database=db_status,
    )
