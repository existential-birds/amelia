"""API route modules.

Provide FastAPI router instances for the server's HTTP and WebSocket
endpoints. Include health checks, workflow management, and real-time
event streaming.

Exports:
    config_router: Configuration endpoint for dashboard.
    files_router: File access endpoints for design document import.
    health_router: Health check and readiness endpoints.
    paths_router: Path validation endpoints for worktree verification.
    websocket_router: WebSocket endpoint for event streaming.
    workflows_router: REST endpoints for workflow management.
"""
from amelia.server.routes.config import router as config_router
from amelia.server.routes.files import router as files_router
from amelia.server.routes.health import router as health_router
from amelia.server.routes.paths import router as paths_router
from amelia.server.routes.websocket import router as websocket_router
from amelia.server.routes.workflows import router as workflows_router


__all__ = [
    "config_router",
    "files_router",
    "health_router",
    "paths_router",
    "websocket_router",
    "workflows_router",
]
