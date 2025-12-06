"""FastAPI application setup and configuration."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from amelia import __version__
from amelia.config import load_settings
from amelia.logging import log_server_startup
from amelia.server.config import ServerConfig
from amelia.server.database import WorkflowRepository
from amelia.server.database.connection import Database
from amelia.server.dependencies import (
    clear_database,
    clear_orchestrator,
    set_database,
    set_orchestrator,
)
from amelia.server.events.bus import EventBus
from amelia.server.lifecycle.health_checker import WorktreeHealthChecker
from amelia.server.lifecycle.retention import LogRetentionService
from amelia.server.lifecycle.server import ServerLifecycle
from amelia.server.orchestrator.service import OrchestratorService
from amelia.server.routes import health_router, websocket_router, workflows_router
from amelia.server.routes.websocket import connection_manager
from amelia.server.routes.workflows import configure_exception_handlers


# Module-level config storage for DI
_config: ServerConfig | None = None


def get_config() -> ServerConfig:
    """FastAPI dependency that provides the server configuration.

    Returns:
        The current ServerConfig instance.

    Raises:
        RuntimeError: If config is not initialized (server not started).
    """
    if _config is None:
        raise RuntimeError("Server config not initialized. Is the server running?")
    return _config


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifespan events.

    Sets start_time on startup for uptime calculation.
    Initializes configuration, database, orchestrator, and lifecycle components.
    """
    global _config

    # Initialize configuration
    _config = ServerConfig()

    # Load Amelia settings for profile management
    settings = load_settings()

    # Connect to database and ensure schema exists
    database = Database(_config.database_path)
    await database.connect()
    await database.ensure_schema()

    # Set the database in dependencies module for DI
    set_database(database)

    # Create repository for orchestrator
    repository = WorkflowRepository(database)

    # Create event bus
    event_bus = EventBus()
    # Wire WebSocket broadcasting
    event_bus.set_connection_manager(connection_manager)

    # Create and register orchestrator
    orchestrator = OrchestratorService(
        event_bus=event_bus,
        repository=repository,
        settings=settings,
        max_concurrent=_config.max_concurrent,
    )
    set_orchestrator(orchestrator)

    # Create lifecycle components
    log_retention = LogRetentionService(db=database, config=_config)
    lifecycle = ServerLifecycle(
        orchestrator=orchestrator,
        log_retention=log_retention,
    )
    health_checker = WorktreeHealthChecker(orchestrator=orchestrator)

    # Start lifecycle components
    await lifecycle.startup()
    await health_checker.start()

    # Log server startup with styled banner
    log_server_startup(
        host=_config.host,
        port=_config.port,
        database_path=str(_config.database_path),
        version=__version__,
    )

    app.state.start_time = datetime.now(UTC)
    yield

    # Shutdown - stop components in reverse order
    # Close WebSocket connections first
    await connection_manager.close_all(code=1001, reason="Server shutting down")

    await health_checker.stop()
    await lifecycle.shutdown()
    clear_orchestrator()
    await database.close()
    clear_database()
    _config = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    application = FastAPI(
        title="Amelia API",
        description="Agentic coding orchestrator REST API",
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Configure exception handlers
    configure_exception_handlers(application)

    # Mount routes
    application.include_router(health_router, prefix="/api")
    application.include_router(workflows_router, prefix="/api")
    application.include_router(websocket_router)  # No prefix - route is /ws/events

    return application


# Create app instance
app = create_app()
