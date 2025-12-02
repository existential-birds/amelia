"""Health check endpoints for liveness and readiness probes."""
from datetime import UTC, datetime
from typing import Any

import psutil
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from amelia import __version__


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness() -> dict[str, str]:
    """Minimal liveness check - is the server responding?

    Returns:
        Simple alive status.
    """
    return {"status": "alive"}


@router.get("/ready")
async def readiness() -> Response:
    """Readiness check - is the server ready to accept requests?

    Returns:
        Ready status or 503 if shutting down.
    """
    # TODO: Check lifecycle.is_shutting_down when implemented
    return JSONResponse(content={"status": "ready"})


@router.get("")
async def health(request: Request) -> dict[str, Any]:
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

    # TODO: Implement actual database health check
    db_status = {"status": "healthy", "mode": "wal"}

    overall_status = "healthy" if db_status["status"] == "healthy" else "degraded"

    return {
        "status": overall_status,
        "version": __version__,
        "uptime_seconds": uptime,
        "active_workflows": active_workflows,
        "websocket_connections": websocket_connections,
        "memory_mb": round(process.memory_info().rss / 1024 / 1024, 2),
        "cpu_percent": process.cpu_percent(),
        "database": db_status,
    }
