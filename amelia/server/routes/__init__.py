"""API route modules.

Provide FastAPI router instances for the server's HTTP and WebSocket
endpoints. Include health checks, workflow management, and real-time
event streaming.

Exports:
    config_router: Configuration endpoint for dashboard.
    health_router: Health check and readiness endpoints.
    websocket_router: WebSocket endpoint for event streaming.
    workflows_router: REST endpoints for workflow management.
"""
from amelia.server.routes.config import router as config_router
from amelia.server.routes.health import router as health_router
from amelia.server.routes.websocket import router as websocket_router
from amelia.server.routes.workflows import router as workflows_router


__all__ = ["config_router", "health_router", "websocket_router", "workflows_router"]
