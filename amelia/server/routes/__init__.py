"""API route modules."""
from amelia.server.routes.health import router as health_router
from amelia.server.routes.websocket import router as websocket_router
from amelia.server.routes.workflows import router as workflows_router


__all__ = ["health_router", "websocket_router", "workflows_router"]
