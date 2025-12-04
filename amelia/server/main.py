"""FastAPI application setup and configuration."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from amelia import __version__
from amelia.logging import log_server_startup
from amelia.server.config import ServerConfig
from amelia.server.database.connection import Database
from amelia.server.dependencies import clear_database, set_database
from amelia.server.routes import health_router, workflows_router
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
    Initializes configuration and connects to database.
    """
    global _config

    # Initialize configuration
    _config = ServerConfig()

    # Connect to database and ensure schema exists
    database = Database(_config.database_path)
    await database.connect()
    await database.ensure_schema()

    # Set the database in dependencies module for DI
    set_database(database)

    # Log server startup with styled banner
    log_server_startup(
        host=_config.host,
        port=_config.port,
        database_path=str(_config.database_path),
        version=__version__,
    )

    app.state.start_time = datetime.now(UTC)
    yield

    # Cleanup
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

    return application


# Create app instance
app = create_app()
