"""FastAPI application setup and configuration."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from amelia import __version__
from amelia.logging import log_server_startup
from amelia.server.config import ServerConfig
from amelia.server.database.connection import Database
from amelia.server.routes import health_router


# Module-level config storage for DI
_config: ServerConfig | None = None
# Global database instance
_database: Database | None = None


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


def get_database() -> Database:
    """Get the database instance.

    Returns:
        The current Database instance.

    Raises:
        RuntimeError: If database not initialized.
    """
    if _database is None:
        raise RuntimeError("Database not initialized. Is the server running?")
    return _database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifespan events.

    Sets start_time on startup for uptime calculation.
    Initializes configuration and connects to database.
    """
    global _config, _database

    # Initialize configuration
    _config = ServerConfig()

    # Connect to database and ensure schema exists
    _database = Database(_config.database_path)
    await _database.connect()
    await _database.ensure_schema()

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
    if _database:
        await _database.close()
        _database = None
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

    # Mount health routes
    application.include_router(health_router, prefix="/api")

    return application


# Create app instance
app = create_app()
