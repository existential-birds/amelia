"""FastAPI application setup and configuration."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from loguru import logger

from amelia import __version__
from amelia.server.config import ServerConfig
from amelia.server.routes import health_router


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
    Initializes configuration and ensures required directories exist.
    """
    global _config

    # Initialize configuration
    _config = ServerConfig()

    # Ensure database directory exists
    db_dir = _config.database_path.parent
    db_dir.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Ensured database directory exists: {db_dir}")

    # Log effective configuration
    logger.info(
        f"Server starting: host={_config.host}, port={_config.port}, "
        f"debug=False, database={_config.database_path}"
    )

    app.state.start_time = datetime.now(UTC)
    yield

    # Cleanup
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
