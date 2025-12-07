"""FastAPI application setup and configuration.

Note: Imports are intentionally placed after _check_dependencies() to provide
a user-friendly error message when langgraph-checkpoint-sqlite is missing.
This typically happens when running `amelia server` without `uv run`.
"""
# ruff: noqa: E402, PLC0415
import sys


def _check_dependencies() -> None:
    """Check that required dependencies are available.

    Raises:
        SystemExit: If required dependencies are missing.
    """
    missing = []
    try:
        import langgraph.checkpoint.sqlite.aio  # noqa: F401
    except ModuleNotFoundError:
        missing.append("langgraph-checkpoint-sqlite")

    if missing:
        print(
            f"\n[ERROR] Missing required dependencies: {', '.join(missing)}\n\n"
            "The Amelia server requires dependencies installed in the virtual environment.\n"
            "Please run the server using:\n\n"
            "    uv run amelia server\n\n"
            "Or install dependencies globally:\n\n"
            f"    pip install {' '.join(missing)}\n",
            file=sys.stderr,
        )
        sys.exit(1)


_check_dependencies()

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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

    # Serve dashboard static files (after build)
    dashboard_dir = Path(__file__).parent.parent.parent / "dashboard" / "dist"

    if dashboard_dir.exists():
        # Serve static assets (JS, CSS, images)
        assets_dir = dashboard_dir / "assets"
        if assets_dir.exists():
            application.mount(
                "/assets", StaticFiles(directory=assets_dir), name="assets"
            )

        # SPA fallback: serve index.html for all non-API routes
        @application.api_route("/{full_path:path}", methods=["GET", "HEAD"])
        async def serve_dashboard(full_path: str) -> FileResponse:
            """Serve dashboard index.html for client-side routing."""
            # Skip API and WebSocket routes
            if full_path.startswith("api/") or full_path.startswith("ws/"):
                # Let the 404 handler deal with unknown API routes
                raise HTTPException(status_code=404, detail="Not found")

            index_file = dashboard_dir / "index.html"
            if index_file.exists():
                return FileResponse(index_file)

            raise HTTPException(status_code=404, detail="Dashboard not built")

    else:

        @application.api_route("/", methods=["GET", "HEAD"])
        async def dashboard_not_built() -> dict[str, str]:
            """Inform user that dashboard needs to be built."""
            return {
                "message": "Dashboard not built",
                "instructions": "Run 'cd dashboard && pnpm run build' to build the dashboard",
            }

        # SPA fallback: return instructions for all non-API routes
        @application.api_route("/{full_path:path}", methods=["GET", "HEAD"])
        async def spa_fallback_not_built(full_path: str) -> dict[str, str]:
            """Inform user about missing dashboard for SPA routes."""
            # Skip API and WebSocket routes
            if full_path.startswith("api/") or full_path.startswith("ws/"):
                # Let the 404 handler deal with unknown API routes
                raise HTTPException(status_code=404, detail="Not found")

            return {
                "message": "Dashboard not built",
                "instructions": "Run 'cd dashboard && pnpm run build' to build the dashboard",
            }

    return application


# Create app instance
app = create_app()
