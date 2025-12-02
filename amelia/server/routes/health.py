"""Health check endpoints for liveness and readiness probes."""
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

import psutil
from fastapi import APIRouter, Request
from loguru import logger
from pydantic import BaseModel, Field

from amelia import __version__


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
    mode: str = Field(description="Database mode (e.g., 'wal')")
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


async def check_database_health() -> DatabaseStatus:
    """Verify database read and write capability.

    Performs a lightweight write/read cycle to ensure the database
    is fully operational, not just connected.

    Returns:
        DatabaseStatus with health check results.
    """
    try:
        # Import here to avoid circular import (main.py imports routes)
        from amelia.server.main import get_database  # noqa: PLC0415

        db = get_database()

        # Test write capability
        test_id = str(uuid4())
        await db.execute(
            "INSERT INTO health_check (id, checked_at) VALUES (?, ?)",
            (test_id, datetime.now(UTC)),
        )
        # Cleanup test row
        await db.execute("DELETE FROM health_check WHERE id = ?", (test_id,))
        # Test read capability
        await db.fetch_one("SELECT 1")

        return DatabaseStatus(status="healthy", mode="wal")
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        return DatabaseStatus(status="degraded", mode="wal", error=str(e))


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
async def health(request: Request) -> HealthResponse:
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

    # TODO: Get actual counts when services are implemented
    active_workflows = 0
    websocket_connections = 0

    # Real database health check
    db_status = await check_database_health()

    overall_status: Literal["healthy", "degraded"] = (
        "healthy" if db_status.status == "healthy" else "degraded"
    )

    return HealthResponse(
        status=overall_status,
        version=__version__,
        uptime_seconds=uptime,
        active_workflows=active_workflows,
        websocket_connections=websocket_connections,
        memory_mb=round(process.memory_info().rss / 1024 / 1024, 2),
        cpu_percent=process.cpu_percent(),
        database=db_status,
    )
